"""Unit tests for AlertSignal identity helpers.

Tests cover:
- alert_signal_identity computation
- alert_signal_correlation_hints generation
- dedupe_signals_by_identity
- group_signals_by_identity
- signals_are_same_alert
- signals_can_correlate
- select_latest_signal
- select_signals_for_incident
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
)
from k8s_diag_agent.incident_alert_signal_identity import (
    alert_signal_correlation_hints,
    alert_signal_identity,
    dedupe_signals_by_identity,
    group_signals_by_identity,
    select_latest_signal,
    select_signals_for_incident,
    signals_are_same_alert,
    signals_can_correlate,
)


def make_test_signal(
    *,
    signal_id: str = "sig-test",
    source_type: AlertSourceType = AlertSourceType.ALERTMANAGER,
    source_instance: str = "http://alertmanager:9093",
    status: AlertStatus = AlertStatus.FIRING,
    alertname: str = "TestAlert",
    severity: str | None = "warning",
    fingerprint: str | None = "fp-123",
    starts_at: datetime | None = None,
    labels: tuple[tuple[str, str], ...] = (("alertname", "TestAlert"), ("severity", "warning")),
) -> AlertSignal:
    """Helper to create test signals."""
    if starts_at is None:
        starts_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    return AlertSignal(
        signal_id=signal_id,
        source_type=source_type,
        source_instance=source_instance,
        status=status,
        alertname=alertname,
        severity=severity,
        external_fingerprint=fingerprint,
        labels=labels,
        starts_at=starts_at,
        received_at=datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC),
    )


class TestAlertSignalIdentity:
    """Tests for alert_signal_identity function."""

    def test_same_identity_for_identical_signals(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-same")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-same")

        # Same fingerprint should produce same identity
        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        assert id1 == id2

    def test_different_identity_for_different_fingerprint(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-1")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-2")

        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        assert id1 != id2

    def test_identity_includes_source_instance(self) -> None:
        signal1 = make_test_signal(source_instance="http://am-1:9093")
        signal2 = make_test_signal(source_instance="http://am-2:9093")

        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        assert id1 != id2

    def test_identity_includes_status(self) -> None:
        signal1 = make_test_signal(status=AlertStatus.FIRING)
        signal2 = make_test_signal(status=AlertStatus.RESOLVED)

        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        assert id1 != id2

    def test_identity_includes_alertname(self) -> None:
        signal1 = make_test_signal(alertname="Alert1")
        signal2 = make_test_signal(alertname="Alert2")

        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        assert id1 != id2

    def test_identity_uses_fallback_when_no_fingerprint(self) -> None:
        # Create signals without fingerprint - should use stable labels
        signal1 = make_test_signal(
            signal_id="sig-1",
            fingerprint=None,
            labels=(("alertname", "Test"), ("namespace", "ns1")),
        )
        signal2 = make_test_signal(
            signal_id="sig-2",
            fingerprint=None,
            labels=(("alertname", "Test"), ("namespace", "ns2")),
        )

        id1 = alert_signal_identity(signal1)
        id2 = alert_signal_identity(signal2)
        # Different namespace should produce different identity
        assert id1 != id2

    def test_identity_is_deterministic(self) -> None:
        signal = make_test_signal(signal_id="sig-det", fingerprint="fp-det")
        id1 = alert_signal_identity(signal)
        id2 = alert_signal_identity(signal)
        assert id1 == id2

    def test_identity_is_string(self) -> None:
        signal = make_test_signal()
        identity = alert_signal_identity(signal)
        assert isinstance(identity, str)
        assert len(identity) == 32  # SHA256 truncated to 32 chars


class TestAlertSignalCorrelationHints:
    """Tests for alert_signal_correlation_hints function."""

    def test_includes_core_fields(self) -> None:
        signal = make_test_signal(
            source_instance="http://am:9093",
            alertname="TestAlert",
            severity="critical",
        )
        hints = alert_signal_correlation_hints(signal)

        assert hints.source_instance == "http://am:9093"
        assert hints.alertname == "TestAlert"
        assert hints.severity == "critical"

    def test_includes_stable_labels(self) -> None:
        signal = make_test_signal(
            labels=(
                ("alertname", "Test"),
                ("severity", "warning"),
                ("namespace", "prod"),
                ("pod", "test-pod"),
            ),
        )
        hints = alert_signal_correlation_hints(signal)

        # Should include stable labels
        label_dict = dict(hints.stable_labels)
        assert "alertname" in label_dict
        assert "severity" in label_dict
        assert "namespace" in label_dict
        assert "pod" in label_dict

    def test_includes_external_fingerprint(self) -> None:
        signal = make_test_signal(fingerprint="fp-ext")
        hints = alert_signal_correlation_hints(signal)

        assert hints.external_fingerprint == "fp-ext"

    def test_includes_temporal_fields(self) -> None:
        starts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ends = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        signal = make_test_signal(starts_at=starts)
        # Manually set ends_at
        signal = AlertSignal(
            signal_id=signal.signal_id,
            source_type=signal.source_type,
            source_instance=signal.source_instance,
            status=signal.status,
            alertname=signal.alertname,
            severity=signal.severity,
            external_fingerprint=signal.external_fingerprint,
            labels=signal.labels,
            annotations=signal.annotations,
            starts_at=starts,
            ends_at=ends,
            received_at=signal.received_at,
            generator_url=signal.generator_url,
            external_url=signal.external_url,
        )

        hints = alert_signal_correlation_hints(signal)
        assert hints.starts_at == starts
        assert hints.ends_at == ends


class TestDedupeSignalsByIdentity:
    """Tests for dedupe_signals_by_identity function."""

    def test_removes_duplicates(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-dup")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-dup")
        signal3 = make_test_signal(signal_id="sig-3", fingerprint="fp-dup")

        result = dedupe_signals_by_identity([signal1, signal2, signal3])
        assert len(result) == 1
        # Should keep first occurrence
        assert result[0].signal_id == "sig-1"

    def test_keeps_unique_signals(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-1")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-2")
        signal3 = make_test_signal(signal_id="sig-3", fingerprint="fp-3")

        result = dedupe_signals_by_identity([signal1, signal2, signal3])
        assert len(result) == 3

    def test_empty_list(self) -> None:
        result = dedupe_signals_by_identity([])
        assert result == []

    def test_mixed_duplicates_and_unique(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-1")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-1")  # duplicate
        signal3 = make_test_signal(signal_id="sig-3", fingerprint="fp-3")

        result = dedupe_signals_by_identity([signal1, signal2, signal3])
        assert len(result) == 2
        ids = [s.signal_id for s in result]
        assert "sig-1" in ids
        assert "sig-3" in ids


class TestGroupSignalsByIdentity:
    """Tests for group_signals_by_identity function."""

    def test_groups_by_identity(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-1")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-1")
        signal3 = make_test_signal(signal_id="sig-3", fingerprint="fp-2")

        groups = group_signals_by_identity([signal1, signal2, signal3])
        assert len(groups) == 2

        # Find groups by fingerprint
        for identity, signals in groups.items():
            if len(signals) == 2:
                assert signal1.signal_id in [s.signal_id for s in signals]
                assert signal2.signal_id in [s.signal_id for s in signals]
            elif len(signals) == 1:
                assert signal3.signal_id in [s.signal_id for s in signals]

    def test_empty_list(self) -> None:
        groups = group_signals_by_identity([])
        assert groups == {}


class TestSignalsAreSameAlert:
    """Tests for signals_are_same_alert function."""

    def test_same_alert(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-same")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-same")

        assert signals_are_same_alert(signal1, signal2) is True

    def test_different_alert(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp-1")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp-2")

        assert signals_are_same_alert(signal1, signal2) is False

    def test_symmetric(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1", fingerprint="fp")
        signal2 = make_test_signal(signal_id="sig-2", fingerprint="fp")

        assert signals_are_same_alert(signal1, signal2) == signals_are_same_alert(signal2, signal1)


class TestSignalsCanCorrelate:
    """Tests for signals_can_correlate function."""

    def test_same_source_and_alertname(self) -> None:
        signal1 = make_test_signal(source_instance="am-1", alertname="Alert")
        signal2 = make_test_signal(source_instance="am-1", alertname="Alert")

        assert signals_can_correlate(signal1, signal2) is True

    def test_different_source(self) -> None:
        signal1 = make_test_signal(source_instance="am-1")
        signal2 = make_test_signal(source_instance="am-2")

        assert signals_can_correlate(signal1, signal2) is False

    def test_different_alertname(self) -> None:
        signal1 = make_test_signal(alertname="Alert1")
        signal2 = make_test_signal(alertname="Alert2")

        assert signals_can_correlate(signal1, signal2) is False

    def test_time_overlap(self) -> None:
        starts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ends1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        starts2 = datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)
        ends2 = datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC)

        signal1 = make_test_signal(starts_at=starts1)
        signal1 = AlertSignal(
            **{**signal1.__dict__, "ends_at": ends1}
        )
        signal2 = make_test_signal(signal_id="sig-2", starts_at=starts2)
        signal2 = AlertSignal(
            **{**signal2.__dict__, "ends_at": ends2}
        )

        # They overlap in time
        assert signals_can_correlate(signal1, signal2) is True

    def test_no_time_overlap(self) -> None:
        starts1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ends1 = datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)
        starts2 = datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)
        ends2 = datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC)

        signal1 = make_test_signal(starts_at=starts1)
        signal1 = AlertSignal(
            **{**signal1.__dict__, "ends_at": ends1}
        )
        signal2 = make_test_signal(signal_id="sig-2", starts_at=starts2)
        signal2 = AlertSignal(
            **{**signal2.__dict__, "ends_at": ends2}
        )

        # No overlap
        assert signals_can_correlate(signal1, signal2) is False

    def test_both_none_start_time(self) -> None:
        signal1 = make_test_signal(starts_at=None)
        signal2 = make_test_signal(signal_id="sig-2", starts_at=None)

        # Both have no start time - can correlate
        assert signals_can_correlate(signal1, signal2) is True


class TestSelectLatestSignal:
    """Tests for select_latest_signal function."""

    def test_selects_most_recent(self) -> None:
        signal1 = make_test_signal(signal_id="sig-1")
        signal1 = AlertSignal(
            **{**signal1.__dict__, "received_at": datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)}
        )
        signal2 = make_test_signal(signal_id="sig-2")
        signal2 = AlertSignal(
            **{**signal2.__dict__, "received_at": datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC)}
        )
        signal3 = make_test_signal(signal_id="sig-3")
        signal3 = AlertSignal(
            **{**signal3.__dict__, "received_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)}
        )

        result = select_latest_signal([signal1, signal2, signal3])
        assert result is not None
        assert result.signal_id == "sig-2"

    def test_empty_list(self) -> None:
        result = select_latest_signal([])
        assert result is None

    def test_single_signal(self) -> None:
        signal = make_test_signal()
        result = select_latest_signal([signal])
        assert result is signal


class TestSelectSignalsForIncident:
    """Tests for select_signals_for_incident function."""

    def test_firing_first(self) -> None:
        firing = make_test_signal(signal_id="firing", status=AlertStatus.FIRING)
        resolved = make_test_signal(signal_id="resolved", status=AlertStatus.RESOLVED)

        result = select_signals_for_incident([resolved, firing])
        # Firing should come first
        assert result[0].signal_id == "firing"

    def test_respects_max_count(self) -> None:
        signals = [make_test_signal(signal_id=f"sig-{i}") for i in range(20)]
        result = select_signals_for_incident(signals, max_count=5)
        assert len(result) == 5

    def test_empty_list(self) -> None:
        result = select_signals_for_incident([])
        assert result == []

    def test_sorts_by_recent(self) -> None:
        # Create signals with different times
        signals = []
        for i in range(3):
            signal = make_test_signal(signal_id=f"sig-{i}")
            signal = AlertSignal(
                **{**signal.__dict__, "received_at": datetime(2024, 1, 15, 10 + i, 0, 0, tzinfo=UTC)}
            )
            signals.append(signal)

        result = select_signals_for_incident(signals)
        # Most recent (sig-2) should come first
        assert result[0].signal_id == "sig-2"
