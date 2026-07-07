"""Contract tests: Alertmanager webhook auto-promotes to open/update incidents.

These tests prove the auto-promote path:
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
4. Stale artifacts do not cause incorrect duplicate incidents
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.incident_alertmanager_webhook import (
    handle_alertmanager_webhook,
)
from tests.contracts.alert_webhook_persist_promote_contract_support import (
    AlertWebhookContractTest,
    assert_any_alert_signal_artifact_exists,
    assert_incident_count,
    assert_incident_open,
    assert_promotion_summary,
    assert_stored_signal_count,
    make_artifact_stale,
    make_firing_payload,
    make_incident_store,
    make_webhook_config,
    read_artifact,
    write_alert_signal_artifact,
    write_stale_artifact,
)


class TestAutoPromoteNoPreseed(AlertWebhookContractTest):
    """Contract: no-preseed firing webhook opens an incident."""

    def test_firing_webhook_opens_incident_no_preseed(self):
        """Firing webhook with no preseed should open an incident."""
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="KubePodCrashLooping",
                namespace="prod",
                pod="crashloop-pod-xyz",
                severity="critical",
                summary="Pod is in crash loop",
                description="Pod crashloop-pod-xyz has been restarting",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200, f"Expected 200, got {status_code}"
        assert response.accepted is True
        assert_stored_signal_count(response, 1)

        # Promotion happened
        assert_promotion_summary(
            response,
            enabled=True,
            opened_incident_count=1,
        )

        # Incident created
        incidents = store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.OPEN

        # Artifact exists
        artifact_data = read_artifact(
            assert_any_alert_signal_artifact_exists(self.root)
        )
        assert artifact_data["schema_version"] is not None
        assert artifact_data["signal"] is not None


class TestAutoPromoteDuplicateIdempotency(AlertWebhookContractTest):
    """Contract: duplicate delivery is idempotent."""

    def test_duplicate_webhook_is_idempotent(self):
        """Second delivery should not create duplicate incident."""
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        # Same payload for both calls
        payload = make_firing_payload(
            alertname="KubePodCrashLooping",
            namespace="prod",
            pod="crashloop-pod-xyz",
            severity="critical",
        )

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
        assert_promotion_summary(response1, opened_incident_count=1)

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
        assert_promotion_summary(
            response2,
            opened_incident_count=0,
            skipped_duplicate_count=1,
        )

        # Verify only one incident exists
        assert_incident_count(store, 1)


class TestAutoPromoteFiringThenResolved(AlertWebhookContractTest):
    """Contract: firing then resolved lifecycle."""

    def test_firing_then_resolved_keeps_incident_open(self):
        """Resolved alert should not close the incident."""
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        # Common labels for correlation
        common_labels = {
            "alertname": "KubePodCrashLooping",
            "namespace": "prod",
            "pod": "crashloop-pod-xyz",
            "severity": "critical",
        }

        # First: firing webhook
        response_firing, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname=common_labels["alertname"],
                namespace=common_labels["namespace"],
                pod=common_labels["pod"],
                severity=common_labels["severity"],
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert_promotion_summary(response_firing, opened_incident_count=1)

        # Verify incident is open
        incident = assert_incident_open(store)
        signal_count_before = incident.signal_count

        # Second: resolved webhook for same alert
        response_resolved, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname=common_labels["alertname"],
                namespace=common_labels["namespace"],
                pod=common_labels["pod"],
                severity=common_labels["severity"],
            ).replace(b'"status": "firing"', b'"status": "resolved"'),
            config=config,
            root=self.root,
            incident_store=store,
        )
        assert response_resolved.promotion is not None
        assert response_resolved.promotion.resolved_signal_count >= 1
        assert response_resolved.promotion.skipped_resolved_without_open_incident_count == 0

        # Incident is STILL open (no auto-resolve)
        incidents_after = store.list_incidents()
        assert len(incidents_after) == 1
        assert incidents_after[0].status == IncidentStatus.OPEN

        # Resolved signal was attached
        assert incidents_after[0].signal_count > signal_count_before


class TestAutoPromoteStaleArtifactGuard(AlertWebhookContractTest):
    """Contract: stale artifact guard - no incorrect duplicate incidents."""

    def test_stale_artifact_full_scan_is_deterministic(self):
        """Full scan processes all artifacts; results are deterministic per identity."""
        # Write a stale artifact (old timestamp, unrelated identity)
        old_time = datetime.now(UTC) - timedelta(days=30)
        write_stale_artifact(
            signals_dir=self.signals_dir,
            identity="stale-old-alert-123",
            alertname="OldStaleAlert",
            received_at=old_time,
        )

        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        # Send a new firing webhook
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="NewAlert",
                namespace="prod",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.accepted is True

        # Full scan is bounded - both artifacts scanned (stale + new)
        assert_promotion_summary(
            response,
            scanned_signal_count=2,
            firing_signal_count=2,
            opened_incident_count=2,
        )

        # Verify exactly two incidents exist
        incidents = store.list_incidents()
        assert len(incidents) == 2

        # Verify incidents have different namespaces (deterministic)
        incident_namespaces = {inc.namespace for inc in incidents}
        assert "old-ns" in incident_namespaces
        assert "prod" in incident_namespaces

    def test_stale_artifact_different_identity(self):
        """Different identity should create separate incidents."""
        stale_time = datetime.now(UTC) - timedelta(days=30)

        common_labels = {
            "alertname": "DuplicateTestAlert",
            "namespace": "prod",
            "severity": "critical",
        }

        # Write stale artifact with different identity (hardcoded vs computed)
        # Note: artifact identity "stale-same-id" differs from webhook computed identity
        write_stale_artifact(
            signals_dir=self.signals_dir,
            identity="stale-same-id",
            alertname="DuplicateTestAlert",
            received_at=stale_time,
            namespace="prod",
        )

        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        # Send webhook - identity computed from labels differs from artifact
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname=common_labels["alertname"],
                namespace=common_labels["namespace"],
                severity=common_labels["severity"],
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.promotion is not None

        # Different identities = 2 incidents opened
        assert_promotion_summary(
            response,
            scanned_signal_count=2,
            opened_incident_count=2,
            updated_incident_count=0,
        )


class TestAutoPromoteSameIdentityArtifactReplacement(AlertWebhookContractTest):
    """Contract: same production identity replaces stale artifact before promotion.

    This test proves that:
    1. A stale artifact with a production-computed identity is replaced by a fresh
       webhook for the same identity.
    2. The artifact identity comes from production output, not a hardcoded fake key.
    3. Promotion results in exactly one incident (not two).

    NOTE: This tests "artifact replacement" semantics, not "two artifacts scanned and
    deduplicated in one pass." The fresh webhook overwrites the stale artifact file
    (same identity-derived path) before promotion scans, so only one artifact is scanned.
    This is the intended identity-keyed storage contract.
    """

    def test_same_production_identity_replaces_stale_artifact_before_promotion(self) -> None:
        payload = make_firing_payload(
            alertname="DuplicateTestAlert",
            namespace="prod",
            pod="duplicate-test-pod",
            severity="critical",
        )

        # Step 1: ask production webhook path to compute and persist identity.
        seed_config = make_webhook_config(auto_promote=False)
        seed_store = make_incident_store()

        seed_response, seed_status = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=payload,
            config=seed_config,
            root=self.root,
            incident_store=seed_store,
        )

        assert seed_status == 200, f"Expected 200, got {seed_status}"
        assert seed_response.accepted is True
        assert_stored_signal_count(seed_response, 1)
        assert_incident_count(seed_store, 0)

        produced_artifact_path = assert_any_alert_signal_artifact_exists(self.root)
        produced_artifact = read_artifact(produced_artifact_path)

        identity = produced_artifact["identity"]
        assert isinstance(identity, str)
        assert identity

        # Step 2: replace production artifact with a stale artifact that keeps
        # the production-computed identity but has a distinct signal_id.
        stale_time = datetime.now(UTC) - timedelta(days=30)

        stale_artifact = make_artifact_stale(
            produced_artifact,
            received_at=stale_time,
            signal_id=f"stale-signal-{identity}",
        )

        produced_artifact_path.unlink()
        write_alert_signal_artifact(
            signals_dir=self.signals_dir,
            artifact=stale_artifact,
            identity=identity,
        )

        # Step 3: send same logical alert through the real webhook path again.
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=payload,
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200, f"Expected 200, got {status_code}"
        assert response.accepted is True

        # Same-identity alert artifacts are keyed by identity path, so the fresh
        # webhook replaces the stale artifact before promotion scans signals.
        assert_promotion_summary(
            response,
            scanned_signal_count=1,
            firing_signal_count=1,
            opened_incident_count=1,
        )

        # Assert exactly one OPEN incident exists
        assert_incident_open(store)
        assert_incident_count(store, 1)
