"""Regression tests for nodeSelector scheduling failures in loop_assessment_warning_events."""

from __future__ import annotations

from collections.abc import Callable

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


def _signal_id_generator() -> Callable[[], str]:
    """Simple signal ID generator for testing."""
    _counter = [0]
    def generator() -> str:
        _counter[0] += 1
        return f"sig-{_counter[0]}"
    return generator


class TestNodeSelectorSchedulingPatterns:
    """Regression tests for nodeSelector scheduling failure detection."""

    def test_node_selector_failure_produces_signal(self) -> None:
        """Regression: FailedScheduling with nodeSelector mismatch produces scheduling signal."""
        events = [
            _make_warning_event(
                namespace="otel-demo",
                reason="FailedScheduling",
                message="0/8 nodes are available: 1 node(s) had untolerated taint, "
                        "[... 7 nodes remaining]: didn't match Pod's node affinity/selector. "
                        "pod has nodeSelector terms which conflict with the node's labels",
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
        assert "failed_scheduling" in pattern_reasons
        # Pin the exact cause label: "didn't match" should take precedence over "affinity"
        assert "node selector mismatch" in signals[0].description

    def test_node_selector_with_didnt_match_pattern(self) -> None:
        """Regression: FailedScheduling with didn't match produces scheduling signal."""
        events = [
            _make_warning_event(
                namespace="otel-demo",
                reason="FailedScheduling",
                message="0/8 nodes are available: ... "
                        "didn't match Pod's node affinity/selector ... "
                        "nodeSelector key 'k9b.dev/otel-lab-node' not found on any node",
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
        assert "failed_scheduling" in pattern_reasons
        # Pin the exact cause label
        assert "node selector mismatch" in signals[0].description

    def test_node_selector_camelcase_pattern(self) -> None:
        """Regression: nodeSelector camelCase with 'nodes are available' produces scheduling signal."""
        events = [
            _make_warning_event(
                namespace="otel-demo",
                reason="FailedScheduling",
                message="0/8 nodes are available: pod has nodeSelector "
                        "k9b.dev/otel-lab-node=missing and no node has matching labels",
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
        assert "failed_scheduling" in pattern_reasons
        # Pin the exact cause label for the "nodeselector" (camelCase) branch
        assert "node selector mismatch" in signals[0].description
