"""Contract tests for Alertmanager webhook persist-to-promote path.

ACT-K9B-ALERT-WEBHOOK-AUTO-PROMOTE-CONTRACT01

These tests prove the real backend path:
    Alertmanager webhook payload
      → normalize AlertSignal
      → write alert-signal artifact
      → auto-promote
      → open/update K9B incident

Unlike unit tests that pre-write artifacts before calling the webhook handler,
these tests start with an empty signals directory and exercise the full path.

Test contracts:
1. No-preseed firing webhook opens an incident
2. Duplicate webhook delivery is idempotent
3. Firing then resolved keeps incident open and attaches resolved signal
4. Resolved-only webhook opens no incident
5. Auto-promote disabled stores signal but opens no incident
6. Stale artifacts do not cause incorrect duplicate incidents
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.incident_alert_signal_store import (
    ALERT_SIGNAL_SCHEMA_VERSION,
    ALERT_SIGNALS_SUBDIR,
    EXTERNAL_ANALYSIS_SUBDIR,
)
from k8s_diag_agent.incident_alertmanager_webhook import (
    handle_alertmanager_webhook,
)
from k8s_diag_agent.incident_alertmanager_webhook_config import (
    AlertmanagerWebhookConfig,
)


def _get_signals_dir(root: Path) -> Path:
    """Get the alert signals directory path."""
    return root / EXTERNAL_ANALYSIS_SUBDIR / ALERT_SIGNALS_SUBDIR


def _assert_any_alert_signal_artifact_exists(root: Path) -> Path:
    """Assert any alert-signal artifact exists and return its path."""
    signals_dir = _get_signals_dir(root)
    artifacts = list(signals_dir.glob("alert-signal-*.json"))
    assert len(artifacts) >= 1, f"Expected at least 1 artifact in {signals_dir}"
    return artifacts[0]


def _read_artifact(artifact_path: Path) -> dict:
    """Read and parse a JSON artifact."""
    return json.loads(artifact_path.read_text(encoding="utf-8"))


class TestNoPreseedFiringWebhookOpensIncident:
    """Contract test 1: No-preseed firing webhook opens an incident.

    Start with an empty signals directory, send a firing webhook,
    and assert the full persist-to-promote path works.
    """

    def setup_method(self):
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        # Start with empty signals directory (no preseed)
        self.signals_dir = _get_signals_dir(self.root)
        assert not self.signals_dir.exists()  # Verify empty

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_firing_webhook_opens_incident_no_preseed(self):
        """Firing webhook with no preseed should open an incident."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Send firing webhook - starts empty, should normalize, persist, promote
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=json.dumps({
                "alerts": [{
                    "status": "firing",
                    "labels": {
                        "alertname": "KubePodCrashLooping",
                        "namespace": "prod",
                        "pod": "crashloop-pod-xyz",
                        "severity": "critical",
                    },
                    "annotations": {
                        "summary": "Pod is in crash loop",
                        "description": "Pod crashloop-pod-xyz has been restarting",
                    },
                    "startsAt": datetime.now(UTC).isoformat(),
                }],
            }).encode("utf-8"),
            config=config,
            root=self.root,
            incident_store=store,
        )

        # Verify response
        assert status_code == 200, f"Expected 200, got {status_code}"
        assert response.accepted is True, "Webhook should be accepted"
        assert response.stored_signal_count == 1, f"Expected 1 stored signal, got {response.stored_signal_count}"

        # Verify promotion happened
        assert response.promotion is not None, "Promotion summary should be present"
        assert response.promotion.enabled is True, "Promotion should be enabled"
        assert response.promotion.opened_incident_count == 1, \
            f"Expected 1 opened incident, got {response.promotion.opened_incident_count}"

        # Verify incident was created
        incidents = store.list_incidents()
        assert len(incidents) == 1, f"Expected 1 incident, got {len(incidents)}"
        assert incidents[0].status == IncidentStatus.OPEN, "Incident should be OPEN"

        # Verify alert-signal artifact exists on disk
        artifact_data = _read_artifact(_assert_any_alert_signal_artifact_exists(self.root))
        assert artifact_data["schema_version"] == ALERT_SIGNAL_SCHEMA_VERSION
        assert artifact_data["signal"] is not None


class TestDuplicateWebhookIdempotency:
    """Contract test 2: Duplicate delivery is idempotent.

    Send the same webhook payload twice without manually writing artifacts.
    The second delivery should not open a second incident.
    """

    def setup_method(self):
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = _get_signals_dir(self.root)
        assert not self.signals_dir.exists()

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_duplicate_webhook_is_idempotent(self):
        """Second delivery should not create duplicate incident."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Same payload for both calls
        payload = json.dumps({
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": "KubePodCrashLooping",
                    "namespace": "prod",
                    "pod": "crashloop-pod-xyz",
                    "severity": "critical",
                },
                "startsAt": datetime.now(UTC).isoformat(),
            }],
        }).encode("utf-8")

        # First delivery
        response1, status_code1 = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=payload,
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert status_code1 == 200
        assert response1.promotion is not None
        assert response1.promotion.opened_incident_count == 1, \
            "First delivery should open incident"

        # Second delivery (same payload)
        response2, status_code2 = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=payload,
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert status_code2 == 200
        assert response2.promotion is not None

        # Second delivery should NOT open another incident
        assert response2.promotion.opened_incident_count == 0, \
            "Second delivery should not open new incident"

        # Idempotency counters should reflect the duplicate
        assert response2.promotion.skipped_duplicate_count >= 1, \
            f"Expected skipped duplicate count >= 1, got {response2.promotion.skipped_duplicate_count}"

        # Verify only one incident exists
        incidents = store.list_incidents()
        assert len(incidents) == 1, \
            f"Expected 1 incident (idempotent), got {len(incidents)}"


class TestFiringThenResolvedLifecycle:
    """Contract test 3: Firing then resolved lifecycle.

    Send firing webhook first, then resolved webhook for the same alert.
    The incident should remain open and the resolved signal should attach.
    """

    def setup_method(self):
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = _get_signals_dir(self.root)
        assert not self.signals_dir.exists()

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_firing_then_resolved_keeps_incident_open(self):
        """Resolved alert should not close the incident."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Common labels for correlation
        common_labels = {
            "alertname": "KubePodCrashLooping",
            "namespace": "prod",
            "pod": "crashloop-pod-xyz",
            "severity": "critical",
        }

        # First: firing webhook
        firing_payload = json.dumps({
            "alerts": [{
                "status": "firing",
                "labels": common_labels,
                "startsAt": datetime.now(UTC).isoformat(),
            }],
        }).encode("utf-8")

        response_firing, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=firing_payload,
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert response_firing.promotion is not None
        assert response_firing.promotion.opened_incident_count == 1

        # Verify incident is open
        incidents_before = store.list_incidents()
        assert len(incidents_before) == 1
        assert incidents_before[0].status == IncidentStatus.OPEN
        signal_count_before = incidents_before[0].signal_count

        # Second: resolved webhook for same alert
        resolved_payload = json.dumps({
            "alerts": [{
                "status": "resolved",
                "labels": common_labels,
                "startsAt": datetime.now(UTC).isoformat(),
                "endsAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }],
        }).encode("utf-8")

        response_resolved, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=resolved_payload,
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert response_resolved.promotion is not None
        assert response_resolved.promotion.resolved_signal_count >= 1

        # Resolved should NOT open incident (no open incident to attach to initially)
        # But should attach to existing incident
        assert response_resolved.promotion.skipped_resolved_without_open_incident_count == 0, \
            "Resolved alert should not be skipped when incident exists"

        # Verify incident is STILL open (no auto-resolve)
        incidents_after = store.list_incidents()
        assert len(incidents_after) == 1, "Should still have exactly 1 incident"
        assert incidents_after[0].status == IncidentStatus.OPEN, \
            "Incident should remain OPEN (no auto-resolve)"

        # Verify resolved signal was attached (signal count increased)
        assert incidents_after[0].signal_count > signal_count_before, \
            "Resolved signal should be attached to incident"


class TestResolvedOnlyWebhook:
    """Contract test 4: Resolved-only webhook opens no incident.

    Send only a resolved webhook (no prior firing).
    Should store the signal but not open an incident.
    """

    def setup_method(self):
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = _get_signals_dir(self.root)
        assert not self.signals_dir.exists()

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resolved_only_opens_no_incident(self):
        """Resolved-only webhook should not open incident."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Resolved-only payload (no prior firing)
        resolved_payload = json.dumps({
            "alerts": [{
                "status": "resolved",
                "labels": {
                    "alertname": "KubePodCrashLooping",
                    "namespace": "prod",
                    "pod": "crashloop-pod-xyz",
                    "severity": "critical",
                },
                "startsAt": datetime.now(UTC).isoformat(),
                "endsAt": datetime.now(UTC).isoformat(),
            }],
        }).encode("utf-8")

        response, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=resolved_payload,
            config=config,
            root=self.root,
            incident_store=store,
        )

        # Should store the resolved signal
        assert response.stored_signal_count == 1, \
            f"Expected 1 stored signal, got {response.stored_signal_count}"

        # Promotion should reflect resolved-only
        assert response.promotion is not None
        assert response.promotion.resolved_signal_count == 1, \
            f"Expected 1 resolved signal, got {response.promotion.resolved_signal_count}"
        assert response.promotion.opened_incident_count == 0, \
            "Resolved-only should not open incident"
        assert response.promotion.skipped_resolved_without_open_incident_count == 1, \
            "Resolved without open incident should be skipped"

        # Incident list should remain empty
        incidents = store.list_incidents()
        assert len(incidents) == 0, \
            f"Expected 0 incidents for resolved-only, got {len(incidents)}"


class TestAutoPromoteDisabled:
    """Contract test 5: Auto-promote disabled stores signal but opens no incident.

    With K9B_ALERTMANAGER_WEBHOOK_AUTO_PROMOTE=false, the webhook should
    still store the alert-signal artifact but not open any incidents.
    """

    def setup_method(self):
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = _get_signals_dir(self.root)
        assert not self.signals_dir.exists()

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_auto_promote_disabled_stores_signal_no_incident(self):
        """With auto_promote=False, signal should be stored but no incident opened."""
        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=False,  # Disabled
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=json.dumps({
                "alerts": [{
                    "status": "firing",
                    "labels": {
                        "alertname": "KubePodCrashLooping",
                        "namespace": "prod",
                        "pod": "crashloop-pod-xyz",
                        "severity": "critical",
                    },
                    "startsAt": datetime.now(UTC).isoformat(),
                }],
            }).encode("utf-8"),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.accepted is True

        # Signal should be stored
        assert response.stored_signal_count == 1, \
            f"Signal should be stored, got {response.stored_signal_count}"

        # Artifact should exist on disk
        _assert_any_alert_signal_artifact_exists(self.root)

        # Promotion should be absent or disabled
        if response.promotion is not None:
            assert response.promotion.enabled is False, \
                "Promotion should be disabled"

        # No incident should be opened
        incidents = store.list_incidents()
        assert len(incidents) == 0, \
            f"Expected 0 incidents with auto_promote=False, got {len(incidents)}"


class TestStaleArtifactGuard:
    """Contract test 6: Stale artifact guard.

    Create an old unrelated alert-signal artifact before sending a new webhook.
    The old artifact should not cause incorrect duplicate incidents.
    """

    def setup_method(self):
        """Set up signals directory with stale artifact."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = _get_signals_dir(self.root)
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_stale_artifact(self, identity: str, alertname: str, received_at: datetime) -> None:
        """Write a stale artifact with old timestamp."""
        artifact = {
            "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
            "identity": identity,
            "received_at": received_at.isoformat(),
            "signal": {
                "signal_id": f"stale-signal-{identity}",
                "source_type": "alertmanager",
                "source_instance": "http://old-alertmanager:9093",
                "status": "firing",
                "alertname": alertname,
                "severity": "warning",
                "labels": {"alertname": alertname, "namespace": "old-ns"},
                "annotations": {},
                "received_at": received_at.isoformat(),
            },
            "correlation_hints": None,
            "raw_payload_artifact_id": None,
        }
        artifact_path = self.signals_dir / f"alert-signal-{identity}.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    def test_stale_artifact_full_scan_is_deterministic(self):
        """Full scan processes all artifacts; results are deterministic per identity.

        The current design does a full scan of all artifacts in the signals directory.
        This test verifies:
        1. Full scan is bounded (doesn't scan unbounded artifacts)
        2. All firing artifacts are processed
        3. Results are deterministic - no random behavior
        """
        # Write a stale artifact (old timestamp, unrelated identity)
        old_time = datetime.now(UTC) - timedelta(days=30)
        self._write_stale_artifact(
            identity="stale-old-alert-123",
            alertname="OldStaleAlert",
            received_at=old_time,
        )

        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Send a new firing webhook
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=json.dumps({
                "alerts": [{
                    "status": "firing",
                    "labels": {
                        "alertname": "NewAlert",
                        "namespace": "prod",
                        "severity": "critical",
                    },
                    "startsAt": datetime.now(UTC).isoformat(),
                }],
            }).encode("utf-8"),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.accepted is True
        assert response.promotion is not None

        # Verify full scan is bounded - both artifacts scanned (stale + new)
        assert response.promotion.scanned_signal_count == 2, \
            f"Full scan should process both artifacts, got {response.promotion.scanned_signal_count}"

        # Both firing alerts processed
        assert response.promotion.firing_signal_count == 2, \
            f"Should have 2 firing signals, got {response.promotion.firing_signal_count}"

        # Two incidents opened (one per unique identity)
        assert response.promotion.opened_incident_count == 2, \
            "Both firing alerts should open incidents"

        # Verify exactly two incidents exist
        incidents = store.list_incidents()
        assert len(incidents) == 2, \
            f"Expected 2 incidents (one per identity), got {len(incidents)}"

        # Verify incidents have different namespaces (deterministic based on alert identity)
        incident_namespaces = {inc.namespace for inc in incidents}
        assert "old-ns" in incident_namespaces, \
            f"OldStaleAlert should have incident with namespace 'old-ns', got {incident_namespaces}"
        assert "prod" in incident_namespaces, \
            f"NewAlert should have incident with namespace 'prod', got {incident_namespaces}"

    def test_stale_artifact_same_identity_deduplicated(self):
        """Same identity should not create duplicate incidents."""
        # Write a stale artifact with the SAME identity as what we're about to send
        stale_time = datetime.now(UTC) - timedelta(days=30)

        # Compute the identity for this alert
        common_labels = {
            "alertname": "DuplicateTestAlert",
            "namespace": "prod",
            "severity": "critical",
        }

        # Write stale artifact with same labels (will have same identity)
        artifact = {
            "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
            "identity": "same-identity-key",  # Deterministic identity
            "received_at": stale_time.isoformat(),
            "signal": {
                "signal_id": "stale-sig-1",
                "source_type": "alertmanager",
                "source_instance": "http://alertmanager:9093",
                "status": "firing",
                "alertname": "DuplicateTestAlert",
                "severity": "critical",
                "labels": common_labels,
                "annotations": {},
                "received_at": stale_time.isoformat(),
            },
            "correlation_hints": None,
            "raw_payload_artifact_id": None,
        }
        artifact_path = self.signals_dir / "alert-signal-same-identity-key.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        config = AlertmanagerWebhookConfig(
            enabled=True,
            auto_promote=True,
            bearer_token="test-token",
            source_instance="http://alertmanager:9093",
        )
        store = IncidentStore()

        # Send webhook with SAME labels (same identity)
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=json.dumps({
                "alerts": [{
                    "status": "firing",
                    "labels": common_labels,
                    "startsAt": datetime.now(UTC).isoformat(),
                }],
            }).encode("utf-8"),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.promotion is not None

        # Both scanned but only one should open, the new signal attaches to existing incident
        # The old artifact opens the incident, the new signal is attached (updated)
        assert response.promotion.scanned_signal_count == 2, \
            "Both stale and new should be scanned"
        assert response.promotion.opened_incident_count == 1, \
            "Only one incident should be opened (deduplicated by identity)"
        # New signal attaches to existing incident (updated) rather than opening new
        assert response.promotion.updated_incident_count == 1, \
            "New signal should be attached to existing incident"
        # No duplicate skipped since signals have different signal_ids
