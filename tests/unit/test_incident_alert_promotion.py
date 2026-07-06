"""Unit tests for alert signal promotion service.

Tests cover:
- Firing alert opens incident
- Second same firing alert dedupes/updates existing incident
- Resolved alert attaches to existing incident
- Resolved alert without existing incident is skipped
- Promotion result counts are correct
- Existing Kubernetes incident promotion still passes
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.incident_alert_promotion import (
    alert_signal_to_incident_candidate,
    attach_alert_signal_to_incident,
    open_incident_from_alert_signal,
    promote_alert_signals_to_incidents,
)
from k8s_diag_agent.incident_alert_signal import AlertSignal, AlertSourceType, AlertStatus
from k8s_diag_agent.incident_alert_signal_store import ALERT_SIGNAL_SCHEMA_VERSION


def _make_signal(
    alertname: str = "TestAlert",
    signal_id: str = "sig-123",
    source_instance: str = "http://alertmanager:9093",
    status: str = "firing",
    severity: str = "critical",
    namespace: str = "prod",
    labels: dict | None = None,
) -> AlertSignal:
    """Helper to create a test signal."""
    all_labels = {"alertname": alertname, "namespace": namespace}
    if labels:
        all_labels.update(labels)
    return AlertSignal(
        signal_id=signal_id,
        source_type=AlertSourceType.ALERTMANAGER,
        source_instance=source_instance,
        status=AlertStatus(status),
        alertname=alertname,
        severity=severity,
        labels=tuple((k, v) for k, v in all_labels.items()),
        annotations=(),
        starts_at=datetime.now(UTC),
        ends_at=None,
        received_at=datetime.now(UTC),
        generator_url=None,
        external_url=None,
        raw_payload_artifact_id=None,
        truncation=None,
    )


def _write_signal_artifact(
    signals_dir: Path,
    identity: str,
    signal: AlertSignal,
) -> None:
    """Helper to write a signal artifact to disk."""
    artifact = {
        "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
        "identity": identity,
        "received_at": datetime.now(UTC).isoformat(),
        "signal": signal.to_dict(),
        "correlation_hints": None,
        "raw_payload_artifact_id": None,
    }
    artifact_path = signals_dir / f"alert-signal-{identity}.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")


class TestAlertSignalToIncidentCandidate:
    """Tests for alert_signal_to_incident_candidate function."""

    def test_maps_crash_loop_signal(self):
        """Test that KubePodCrashLooping maps to crash_loop candidate."""
        signal = _make_signal(alertname="KubePodCrashLooping", labels={"pod": "test-pod"})

        result = alert_signal_to_incident_candidate(signal, "test-correlation-key")

        assert result.candidate_id == "test-correlation-key"
        assert result.namespace == "prod"
        assert result.object_kind.value == "Pod"
        assert result.candidate_class.value == "crash_loop"
        assert len(result.signals) == 1

    def test_maps_deployment_signal(self):
        """Test that KubeDeploymentReplicasMismatch maps to deployment_unavailable candidate."""
        signal = _make_signal(
            alertname="KubeDeploymentReplicasMismatch",
            labels={"deployment": "checkout"},
        )

        result = alert_signal_to_incident_candidate(signal, "test-correlation-key")

        assert result.object_kind.value == "Deployment"
        assert result.candidate_class.value == "deployment_unavailable"


class TestOpenIncidentFromAlertSignal:
    """Tests for open_incident_from_alert_signal function."""

    def test_opens_incident_in_open_state(self):
        """Test that incident is opened in OPEN state."""
        signal = _make_signal(alertname="KubePodCrashLooping", labels={"pod": "test-pod"})
        candidate = alert_signal_to_incident_candidate(signal, "test-correlation-key")
        observed_at = datetime.now(UTC)

        result = open_incident_from_alert_signal(
            signal=signal,
            candidate=candidate,
            correlation_key="test-correlation-key",
            observed_at=observed_at,
        )

        assert result.status == IncidentStatus.OPEN
        assert result.incident_id == "test-correlation-key"
        assert result.namespace == "prod"
        assert len(result.signals) == 1
        assert len(result.events) == 1

    def test_includes_signal_fingerprint(self):
        """Test that incident includes signal fingerprint for deduplication."""
        signal = _make_signal(signal_id="unique-sig-123")
        candidate = alert_signal_to_incident_candidate(signal, "test-correlation-key")
        observed_at = datetime.now(UTC)

        result = open_incident_from_alert_signal(
            signal=signal,
            candidate=candidate,
            correlation_key="test-correlation-key",
            observed_at=observed_at,
        )

        assert any(s.fingerprint == "unique-sig-123" for s in result.signals)


class TestAttachAlertSignalToIncident:
    """Tests for attach_alert_signal_to_incident function."""

    def test_attaches_signal(self):
        """Test that signal is attached to existing incident."""
        # Create existing incident
        existing = open_incident_from_alert_signal(
            signal=_make_signal(signal_id="sig-1"),
            candidate=alert_signal_to_incident_candidate(_make_signal(), "test-correlation-key"),
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )

        # Attach new signal
        new_signal = _make_signal(signal_id="sig-2")
        result = attach_alert_signal_to_incident(
            incident=existing,
            signal=new_signal,
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )

        assert len(result.signals) == 2
        assert result.signal_count == 2
        assert any(s.fingerprint == "sig-2" for s in result.signals)

    def test_deduplicates_same_signal(self):
        """Test that duplicate signals are not attached twice."""
        # Create existing incident with a signal
        signal = _make_signal(signal_id="sig-1")
        existing = open_incident_from_alert_signal(
            signal=signal,
            candidate=alert_signal_to_incident_candidate(signal, "test-correlation-key"),
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )

        # Try to attach same signal again
        result = attach_alert_signal_to_incident(
            incident=existing,
            signal=signal,
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )

        # Should not duplicate
        assert len(result.signals) == 1
        assert result.signal_count == 1

    def test_does_not_change_status(self):
        """Test that attachment does not change incident status."""
        existing = open_incident_from_alert_signal(
            signal=_make_signal(signal_id="sig-1"),
            candidate=alert_signal_to_incident_candidate(_make_signal(), "test-correlation-key"),
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )
        original_status = existing.status

        new_signal = _make_signal(signal_id="sig-2")
        result = attach_alert_signal_to_incident(
            incident=existing,
            signal=new_signal,
            correlation_key="test-correlation-key",
            observed_at=datetime.now(UTC),
        )

        assert result.status == original_status


class TestPromoteAlertSignalsToIncidents:
    """Tests for promote_alert_signals_to_incidents function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir)
        self.signals_dir = self.runs_dir / "external-analysis" / "alert-signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.store = IncidentStore()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_firing_alert_opens_incident(self):
        """Test that firing alert opens a new incident."""
        # Write firing alert artifact
        signal = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="firing-sig-1",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "firing-1", signal)

        # Promote
        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        assert result.scanned_signal_count == 1
        assert result.firing_signal_count == 1
        assert result.opened_incident_count == 1
        assert result.error_count == 0

        # Check incident was created
        incidents = self.store.list_incidents()
        assert len(incidents) == 1

    def test_second_firing_alert_dedupes_existing_incident(self):
        """Test that second firing alert updates existing incident."""
        # Write first firing alert
        signal1 = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="firing-sig-1",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "firing-1", signal1)

        # Promote first
        promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        # Write second firing alert (same alertname, different signal_id)
        signal2 = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="firing-sig-2",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "firing-2", signal2)

        # Promote second
        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        # Should have 2 signals total, but only 1 incident opened
        assert result.scanned_signal_count == 2
        assert result.opened_incident_count == 0  # No new incident
        assert result.updated_incident_count == 1  # Updated existing

        # Check incident has 2 signals
        incidents = self.store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].signal_count == 2

    def test_resolved_alert_attaches_to_existing_incident(self):
        """Test that resolved alert attaches to existing incident."""
        # Write firing alert first
        firing_signal = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="firing-sig-1",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "firing-1", firing_signal)

        promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        # Write resolved alert
        resolved_signal = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="resolved-sig-1",
            status="resolved",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "resolved-1", resolved_signal)

        # Promote resolved
        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        assert result.resolved_signal_count == 1
        assert result.skipped_resolved_without_open_incident_count == 0

        # Check incident still in OPEN state
        incidents = self.store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.OPEN
        assert incidents[0].signal_count == 2

    def test_resolved_alert_without_existing_incident_is_skipped(self):
        """Test that resolved alert without matching incident is skipped."""
        # Write only resolved alert (no firing alert first)
        resolved_signal = _make_signal(
            alertname="KubePodCrashLooping",
            signal_id="resolved-sig-1",
            status="resolved",
            labels={"pod": "test-pod"},
        )
        _write_signal_artifact(self.signals_dir, "resolved-1", resolved_signal)

        # Promote
        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        assert result.resolved_signal_count == 1
        assert result.skipped_resolved_without_open_incident_count == 1
        assert result.opened_incident_count == 0

        # No incidents should be created
        incidents = self.store.list_incidents()
        assert len(incidents) == 0

    def test_promotion_result_counts(self):
        """Test that promotion result has correct counts."""
        # Write multiple artifacts
        signals = [
            _make_signal(alertname="KubePodCrashLooping", signal_id="f1", labels={"pod": "pod-1"}),
            _make_signal(alertname="KubePodCrashLooping", signal_id="f2", labels={"pod": "pod-1"}),
            _make_signal(alertname="HighCPU", signal_id="f3"),
            _make_signal(alertname="HighCPU", signal_id="r1", status="resolved"),
        ]

        for i, sig in enumerate(signals):
            _write_signal_artifact(self.signals_dir, f"sig-{i}", sig)

        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        assert result.scanned_signal_count == 4
        assert result.firing_signal_count == 3
        assert result.resolved_signal_count == 1
        assert result.error_count == 0

    def test_empty_directory_returns_empty_result(self):
        """Test that empty directory returns empty result."""
        result = promote_alert_signals_to_incidents(
            incident_store=self.store,
            runs_dir=self.runs_dir,
        )

        assert result.scanned_signal_count == 0
        assert result.firing_signal_count == 0
        assert result.resolved_signal_count == 0


class TestExistingIncidentPromotion:
    """Tests that existing Kubernetes incident promotion still works."""

    def test_kubernetes_candidates_still_work(self):
        """Test that Kubernetes-derived candidates are not affected by alert promotion."""
        from k8s_diag_agent.collect.incident_candidates import CandidateClass, IncidentCandidate, ObjectKind, Severity

        # Create a Kubernetes-derived candidate
        k8s_candidate = IncidentCandidate(
            candidate_id="k8s-crash-loop-test-pod",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=("pod_logs",),
        )

        # Promote via store
        store = IncidentStore()
        now = datetime.now(UTC)
        updated = store.promote_candidates([k8s_candidate], observed_at=now)

        assert len(updated) == 1
        assert updated[0].incident_id == "default-pod-test-pod-crash_loop"
        assert updated[0].status == IncidentStatus.OPEN

    def test_kubernetes_and_alert_incidents_coexist(self):
        """Test that Kubernetes and alert incidents can coexist in same store."""
        # Create Kubernetes incident
        from k8s_diag_agent.collect.incident_candidates import CandidateClass, IncidentCandidate, ObjectKind, Severity

        k8s_candidate = IncidentCandidate(
            candidate_id="k8s-crash-loop-pod-a",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="pod-a",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=(),
        )

        store = IncidentStore()
        store.promote_candidates([k8s_candidate], observed_at=datetime.now(UTC))

        # Create alert incident
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir)
        self.signals_dir = self.runs_dir / "external-analysis" / "alert-signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)

        signal = _make_signal(alertname="KubePodCrashLooping", labels={"pod": "pod-b"})
        _write_signal_artifact(self.signals_dir, "alert-1", signal)

        promote_alert_signals_to_incidents(incident_store=store, runs_dir=self.runs_dir)

        # Both should exist
        incidents = store.list_incidents()
        assert len(incidents) == 2

        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
