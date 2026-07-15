"""Unit tests for alert signal snapshot adapter.

Tests the NormalizedAlert → AlertSignal conversion and artifact persistence.
"""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)
from k8s_diag_agent.incident_alert_signal import AlertSourceType, AlertStatus
from k8s_diag_agent.incident_alert_signal_identity import alert_signal_identity
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    AlertSignalAdapterResult,
    adapt_snapshot_to_alert_signals,
    persist_alert_signals,
)


def _make_snapshot(
    alerts=None,
    status=AlertmanagerStatus.OK,
    captured_at=None,
):
    """Helper to create test snapshots."""
    if alerts is None:
        alerts = []
    return AlertmanagerSnapshot(
        status=status,
        captured_at=captured_at or datetime.now(UTC).isoformat(),
        source="http://alertmanager:9093",
        alert_count=len(alerts),
        alerts=tuple(alerts),
        errors=(),
        truncated=False,
        artifact_id="test-snapshot-id",
    )


def _make_normalized_alert(
    fingerprint="fp123",
    alertname="TestAlert",
    state="active",
    severity="warning",
    namespace="default",
    labels=None,
):
    """Helper to create test normalized alerts."""
    if labels is None:
        labels = [
            ("alertname", alertname),
            ("severity", severity),
        ]
        if namespace:
            labels.append(("namespace", namespace))
    return NormalizedAlert(
        fingerprint=fingerprint,
        alertname=alertname,
        state=state,
        severity=severity,
        namespace=namespace,
        labels=tuple(labels),
    )


class TestAdaptSnapshotToAlertSignals:
    """Tests for adapt_snapshot_to_alert_signals function."""

    def test_empty_snapshot(self) -> None:
        """Empty snapshot returns empty signals."""
        snapshot = _make_snapshot(alerts=[], status=AlertmanagerStatus.EMPTY)
        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )
        assert signals == ()
        assert result.total_alerts == 0
        assert result.firing_signals_count == 0
        assert result.resolved_signals_count == 0

    def test_firing_alert_converts_to_firing_signal(self) -> None:
        """Active/firing alert maps to AlertStatus.FIRING."""
        alert = _make_normalized_alert(state="active", severity="critical")
        snapshot = _make_snapshot(alerts=[alert])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        assert len(signals) == 1
        signal = signals[0]
        assert signal.status == AlertStatus.FIRING
        assert signal.source_type == AlertSourceType.ALERTMANAGER
        assert signal.source_instance == "monitoring/alertmanager-main"
        assert signal.external_fingerprint == "fp123"
        assert signal.alertname == "TestAlert"
        assert signal.severity == "critical"

    def test_fingerprint_used_for_identity(self) -> None:
        """Alertmanager fingerprint is preserved."""
        alert = _make_normalized_alert(fingerprint="unique-fp-456")
        snapshot = _make_snapshot(alerts=[alert])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        assert len(signals) == 1
        assert signals[0].external_fingerprint == "unique-fp-456"

    def test_labels_preserved(self) -> None:
        """Labels are preserved in the signal."""
        alert = _make_normalized_alert(
            labels=[
                ("alertname", "TestAlert"),
                ("severity", "warning"),
                ("namespace", "prod"),
                ("deployment", "api-server"),
            ],
        )
        snapshot = _make_snapshot(alerts=[alert])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        assert len(signals) == 1
        signal = signals[0]
        label_dict = dict(signal.labels)
        assert label_dict.get("alertname") == "TestAlert"
        assert label_dict.get("severity") == "warning"
        assert label_dict.get("namespace") == "prod"
        assert label_dict.get("deployment") == "api-server"

    def test_timestamps_preserved(self) -> None:
        """Timestamps are preserved."""
        alert = NormalizedAlert(
            fingerprint="fp123",
            alertname="TestAlert",
            state="active",
            severity="warning",
            starts_at="2024-01-15T10:30:00Z",
            labels=(("alertname", "TestAlert"),),
        )
        snapshot = _make_snapshot(alerts=[alert])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        assert len(signals) == 1
        assert signals[0].starts_at is not None

    def test_deduplication_within_batch(self) -> None:
        """Duplicate alerts within a snapshot are deduped."""
        alert1 = _make_normalized_alert(fingerprint="dup-fp", alertname="Duplicate")
        alert2 = _make_normalized_alert(fingerprint="dup-fp", alertname="Duplicate")
        snapshot = _make_snapshot(alerts=[alert1, alert2])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        # Should only have one signal due to dedup
        assert len(signals) == 1
        assert result.skipped_count == 1

    def test_multiple_distinct_alerts(self) -> None:
        """Multiple distinct alerts produce multiple signals."""
        alert1 = _make_normalized_alert(fingerprint="fp1", alertname="Alert1")
        alert2 = _make_normalized_alert(fingerprint="fp2", alertname="Alert2")
        alert3 = _make_normalized_alert(fingerprint="fp3", alertname="Alert3")
        snapshot = _make_snapshot(alerts=[alert1, alert2, alert3])

        signals, result = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        assert len(signals) == 3
        assert result.firing_signals_count == 3


class TestPersistAlertSignals:
    """Tests for persist_alert_signals function."""

    def test_persist_empty_signals(self) -> None:
        """Empty signals list returns empty result."""
        with TemporaryDirectory() as tmpdir:
            result, written = persist_alert_signals(
                signals=(),
                root=Path(tmpdir),
            )
            assert result.signals_written == 0
            assert written == []

    def test_persist_single_signal(self) -> None:
        """Single signal is persisted."""
        alert = _make_normalized_alert()
        snapshot = _make_snapshot(alerts=[alert])
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        with TemporaryDirectory() as tmpdir:
            result, written = persist_alert_signals(
                signals=signals,
                root=Path(tmpdir),
            )

            assert result.signals_written == 1
            assert len(written) == 1
            assert result.signals_failed == 0

    def test_persist_idempotent(self) -> None:
        """Same signal written twice is idempotent."""
        alert = _make_normalized_alert()
        snapshot = _make_snapshot(alerts=[alert])
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )

        with TemporaryDirectory() as tmpdir:
            # First write
            result1, _ = persist_alert_signals(
                signals=signals,
                root=Path(tmpdir),
            )
            # Second write (same signals)
            result2, _ = persist_alert_signals(
                signals=signals,
                root=Path(tmpdir),
            )

            assert result1.signals_written == 1
            assert result2.signals_written == 0  # Idempotent - no new signals
            assert result2.signals_skipped_duplicates == 1


class TestAlertSignalAdapterResult:
    """Tests for AlertSignalAdapterResult dataclass."""

    def test_has_signals_property(self) -> None:
        """has_signals returns True when signals written."""
        result = AlertSignalAdapterResult(
            total_alerts=5,
            firing_signals_count=3,
            resolved_signals_count=2,
            signals_written=5,
        )
        assert result.has_signals is True

    def test_has_signals_false_when_empty(self) -> None:
        """has_signals returns False when no signals written."""
        result = AlertSignalAdapterResult(
            total_alerts=0,
            firing_signals_count=0,
            resolved_signals_count=0,
            signals_written=0,
        )
        assert result.has_signals is False

    def test_has_errors_property(self) -> None:
        """has_errors returns True when errors present."""
        result = AlertSignalAdapterResult(
            total_alerts=5,
            firing_signals_count=3,
            errors=("Error 1", "Error 2"),
        )
        assert result.has_errors is True

    def test_has_errors_false_when_no_errors(self) -> None:
        """has_errors returns False when no errors."""
        result = AlertSignalAdapterResult(
            total_alerts=5,
            firing_signals_count=3,
            errors=(),
        )
        assert result.has_errors is False


class TestSignalIdentityIntegration:
    """Integration tests for signal identity with adapter."""

    def test_signal_identity_includes_source_instance(self) -> None:
        """Signal identity uses source_instance for dedupe."""
        alert = _make_normalized_alert(fingerprint="shared-fp")
        snapshot = _make_snapshot(alerts=[alert])

        signals1, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-main",
        )
        signals2, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager-other",
        )

        # Same fingerprint but different source should produce different identity
        identity1 = alert_signal_identity(signals1[0])
        identity2 = alert_signal_identity(signals2[0])
        assert identity1 != identity2


def test_legacy_module_path_retains_adapter_public_exports() -> None:
    """The historical facade path re-exports split contract/persistence APIs."""
    import k8s_diag_agent.incident_alert_signal_snapshot_adapter as adapter
    from k8s_diag_agent.incident_alert_signal_persistence import (
        persist_alert_signals as persistence_function,
    )
    from k8s_diag_agent.incident_alert_signal_snapshot_contract import (
        AlertSignalAdapterResult as contract_result,
    )
    from k8s_diag_agent.incident_alert_signal_snapshot_contract import (
        PersistedAlertSignal,
    )

    assert adapter.AlertSignalAdapterResult is contract_result
    assert adapter.PersistedAlertSignal is PersistedAlertSignal
    assert adapter.persist_alert_signals is persistence_function
    assert callable(adapter.adapt_snapshot_to_alert_signals)
