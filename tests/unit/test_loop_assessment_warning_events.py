"""Tests for loop_assessment_warning_events module."""

from __future__ import annotations

from k8s_diag_agent.collect.cluster_snapshot import WarningEventSummary
from k8s_diag_agent.health.loop_assessment_warning_events import match_warning_event_patterns
from k8s_diag_agent.models import Finding, Hypothesis, Layer, NextCheck, Signal


def _make_warning_event(
    namespace: str,
    reason: str,
    message: str,
    count: int = 1,
) -> WarningEventSummary:
    """Create a WarningEventSummary for testing."""
    return WarningEventSummary(
        namespace=namespace,
        reason=reason,
        message=message,
        count=count,
        last_seen="2026-01-06T00:00:00Z",
    )


def _signal_id_generator() -> callable:
    """Simple signal ID generator for testing."""
    _counter = [0]
    def generator() -> str:
        _counter[0] += 1
        return f"sig-{_counter[0]}"
    return generator


class TestMatchWarningEventPatterns:
    """Tests for match_warning_event_patterns function."""

    def test_probe_warning_events_produce_signal(self) -> None:
        """Probe warning events should produce a signal with WORKLOAD layer."""
        events = [
            _make_warning_event(
                namespace="default",
                reason="Unhealthy",
                message="Readiness probe failed",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 1
        assert signals[0].layer == Layer.WORKLOAD
        assert signals[0].severity == "medium"
        assert "probe" in signals[0].description.lower()
        assert "probe_failure" in pattern_reasons

    def test_scheduling_warning_events_produce_signal(self) -> None:
        """FailedScheduling events should produce a signal."""
        events = [
            _make_warning_event(
                namespace="monitoring",
                reason="FailedScheduling",
                message="0/2 nodes are available: 1 Insufficient memory, 1 node(s) had untolerated taint",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 1
        assert signals[0].layer == Layer.WORKLOAD
        assert "pending" in signals[0].description.lower()
        assert "failed_scheduling" in pattern_reasons

    def test_pvc_warning_events_produce_signal(self) -> None:
        """PVC provisioning failures should produce a STORAGE layer signal."""
        events = [
            _make_warning_event(
                namespace="data",
                reason="ProvisioningFailed",
                message="PersistentVolumeClaim is bound to non-existing PV",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 1
        assert signals[0].layer == Layer.STORAGE
        assert "pvc_pending" in pattern_reasons

    def test_ingress_warning_events_produce_signal(self) -> None:
        """Ingress/backend timeout events should produce a NETWORK layer signal."""
        events = [
            _make_warning_event(
                namespace="ingress",
                reason="BackendTimeout",
                message="backend endpoint timeout connection refused",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 1
        assert signals[0].layer == Layer.NETWORK
        assert "ingress_timeout" in pattern_reasons

    def test_metrics_server_warning_events_produce_signal(self) -> None:
        """Metrics-server related events should produce an OBSERVABILITY signal."""
        events = [
            _make_warning_event(
                namespace="kube-system",
                reason="FailedGetResourceMetric",
                message="metrics-server not responding",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 1
        assert signals[0].layer == Layer.OBSERVABILITY
        assert "missing_metrics" in pattern_reasons

    def test_matched_event_ids_are_marked(self) -> None:
        """Matched events should have their IDs added to matched_event_ids."""
        event1 = _make_warning_event(
            namespace="default",
            reason="Unhealthy",
            message="Readiness probe failed",
        )
        event2 = _make_warning_event(
            namespace="default",
            reason="Unhealthy",
            message="Liveness probe failed",
        )
        events = [event1, event2]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert id(event1) in matched_event_ids
        assert id(event2) in matched_event_ids

    def test_signal_id_generation_is_deterministic(self) -> None:
        """Signal IDs should be generated in deterministic order."""
        events = [
            _make_warning_event(
                namespace="default",
                reason="Unhealthy",
                message="Readiness probe failed",
            ),
        ]
        signals1: list[Signal] = []
        signals2: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen1 = _signal_id_generator()
        gen2 = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals1,
            signal_id_generator=gen1,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        matched_event_ids.clear()
        pattern_reasons.clear()
        pattern_metadata.clear()
        pattern_refs.clear()
        pattern_next_checks.clear()
        pattern_hypotheses.clear()
        findings.clear()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals2,
            signal_id_generator=gen2,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals1) == len(signals2) == 1
        assert signals1[0].id == signals2[0].id

    def test_no_signals_for_unmatched_events(self) -> None:
        """Events that don't match any pattern should not produce signals."""
        events = [
            _make_warning_event(
                namespace="default",
                reason="NormalEvent",
                message="This is a normal informational event",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert len(signals) == 0
        assert len(pattern_reasons) == 0

    def test_return_value_true_when_pattern_matched(self) -> None:
        """Helper should return True when any pattern is matched."""
        events = [
            _make_warning_event(
                namespace="default",
                reason="Unhealthy",
                message="Readiness probe failed",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        result = match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert result is True

    def test_return_value_false_when_no_pattern_matched(self) -> None:
        """Helper should return False when no pattern is matched."""
        events = [
            _make_warning_event(
                namespace="default",
                reason="NormalEvent",
                message="This is a normal informational event",
            ),
        ]
        signals: list[Signal] = []
        findings: list[Finding] = []
        pattern_reasons: list[str] = []
        pattern_metadata: dict[str, tuple[str, ...]] = {}
        pattern_refs: list[str] = []
        pattern_next_checks: list[NextCheck] = []
        pattern_hypotheses: list[Hypothesis] = []
        matched_event_ids: set[int] = set()

        gen = _signal_id_generator()

        result = match_warning_event_patterns(
            warning_events=events,
            signals=signals,
            signal_id_generator=gen,
            matched_event_ids=matched_event_ids,
            findings=findings,
            pattern_reasons=pattern_reasons,
            pattern_metadata=pattern_metadata,
            pattern_refs=pattern_refs,
            pattern_next_checks=pattern_next_checks,
            pattern_hypotheses=pattern_hypotheses,
        )

        assert result is False
