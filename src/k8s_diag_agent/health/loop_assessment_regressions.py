"""Regression detection helpers for health assessment building."""

from __future__ import annotations

from collections.abc import Callable

from ..collect.cluster_snapshot import ClusterSnapshot
from ..models import Finding, Layer, Signal
from .loop_history import HealthHistoryEntry

__all__ = [
    "RegressionAssessment",
    "check_regression_from_history",
]


class RegressionAssessment:
    """Result of regression assessment."""

    __slots__ = ("has_regression", "workload_regression", "node_regression", "references")

    def __init__(
        self,
        *,
        has_regression: bool,
        workload_regression: bool = False,
        node_regression: bool = False,
        references: list[str] | None = None,
    ) -> None:
        self.has_regression = has_regression
        self.workload_regression = workload_regression
        self.node_regression = node_regression
        self.references: list[str] = references or []


def check_regression_from_history(
    *,
    snapshot: ClusterSnapshot,
    previous: HealthHistoryEntry | None,
    signals: list[Signal],
    signal_id_generator: Callable[[], str],
    findings: list[Finding],
) -> RegressionAssessment:
    """Check for regressions in health metrics compared to previous run.

    This function extracts regression-detection logic from build_health_assessment().
    It detects increases in health-relevant metrics compared to the previous run.

    Returns:
        RegressionAssessment with regression status and affected layers.
    """
    # Skip regression checks when there's no previous history
    # (first run has no baseline to compare against)
    if previous is None:
        return RegressionAssessment(
            has_regression=False,
            workload_regression=False,
            node_regression=False,
            references=[],
        )

    health_signals = snapshot.health_signals
    node_conditions = health_signals.node_conditions
    pod_counts = health_signals.pod_counts
    job_failures = health_signals.job_failures
    warning_events = health_signals.warning_events

    previous_node_conditions = previous.node_conditions if previous else {}
    previous_pod_metrics = previous.pod_counts if previous else {}
    previous_job_failures = previous.job_failures if previous else 0
    previous_warning_count = previous.warning_event_count if previous else 0

    has_regression = False
    workload_regression = False
    node_regression = False
    references: list[str] = []

    def _check_regression(
        current: int,
        previous_value: int,
        description: str,
        layer: Layer,
    ) -> None:
        nonlocal has_regression, workload_regression, node_regression
        if current > previous_value:
            has_regression = True
            if layer == Layer.NODE:
                node_regression = True
            else:
                workload_regression = True
            references.append("regression")
            signal = Signal(
                id=signal_id_generator(),
                description=description,
                layer=layer,
                evidence_id="",
                severity="medium",
            )
            signals.append(signal)
            findings.append(
                Finding(
                    id=signal_id_generator(),
                    description=description,
                    supporting_signals=[signal.id],
                    layer=layer,
                )
            )

    _check_regression(
        node_conditions.not_ready,
        previous_node_conditions.get("not_ready", 0),
        f"NotReady node count increased ({previous_node_conditions.get('not_ready', 0)} -> {node_conditions.not_ready}).",
        Layer.NODE,
    )
    _check_regression(
        pod_counts.non_running,
        previous_pod_metrics.get("non_running", 0),
        f"Non-running pods increased ({previous_pod_metrics.get('non_running', 0)} -> {pod_counts.non_running}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.pending,
        previous_pod_metrics.get("pending", 0),
        f"Pending pod count increased ({previous_pod_metrics.get('pending', 0)} -> {pod_counts.pending}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.crash_loop_backoff,
        previous_pod_metrics.get("crash_loop_backoff", 0),
        f"CrashLoopBackOff pods increased ({previous_pod_metrics.get('crash_loop_backoff', 0)} -> {pod_counts.crash_loop_backoff}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.image_pull_backoff,
        previous_pod_metrics.get("image_pull_backoff", 0),
        f"ImagePullBackOff pods increased ({previous_pod_metrics.get('image_pull_backoff', 0)} -> {pod_counts.image_pull_backoff}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        job_failures,
        previous_job_failures,
        f"Job failure count increased ({previous_job_failures} -> {job_failures}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        len(warning_events),
        previous_warning_count,
        f"Warning events increased ({previous_warning_count} -> {len(warning_events)}).",
        Layer.OBSERVABILITY,
    )

    return RegressionAssessment(
        has_regression=has_regression,
        workload_regression=workload_regression,
        node_regression=node_regression,
        references=references,
    )
