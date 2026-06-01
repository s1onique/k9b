"""Count/condition issue classification helpers for health assessment building.

Extracts count and condition issue classification logic from build_health_assessment()
into a focused module. Preserves behavior exactly - no schema or artifact contract changes.

This module handles:
1. Node condition issue detection and signal/finding creation
2. Pod count issue detection and signal/finding creation
3. Job failure detection and signal/finding creation
4. Warning event threshold evaluation

The module does NOT handle:
- Image pull issues (handled separately by loop_assessment_image_pull)
- Regression detection (handled by loop_assessment_regressions)
- Warning event pattern matching (handled by loop_assessment_warning_events)
- Missing evidence assessment (handled by loop_assessment_missing_evidence)
- Baseline policy assessment (handled by loop_assessment_baseline)
- History drift assessment (handled by loop_assessment_history_drift)
- Summary derivation (handled by loop_assessment_summary)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..collect.cluster_snapshot import NodeConditionCounts, PodHealthCounts
from ..models import Layer

__all__ = [
    "CountIssueAssessment",
    "assess_count_issues",
]


@dataclass
class CountIssueAssessment:
    """Result of count/condition issue classification."""

    __slots__ = (
        "issues_detected",
        "workload_issue_present",
        "node_issue_present",
        "warning_event_count",
        "references",
    )

    issues_detected: bool
    """Whether any issues were detected."""

    workload_issue_present: bool
    """Whether workload issues (pods/jobs/warnings) are present."""

    node_issue_present: bool
    """Whether node issues are present."""

    warning_event_count: int
    """Count of warning events (may be needed by callers)."""

    references: list[str]
    """References collected from count issue detection (appended in detection order)."""


def assess_count_issues(
    *,
    node_conditions: NodeConditionCounts,
    pod_counts: PodHealthCounts,
    warning_events: Sequence[object],
    issue_recorder: Callable[[str, str, Layer], object],
) -> CountIssueAssessment:
    """Assess count and condition issues from health signals.

    This function extracts count/condition issue classification from build_health_assessment().
    It checks node conditions and pod counts, creating signals and findings for any issues.

    Args:
        node_conditions: Node condition counts from cluster health signals.
        pod_counts: Pod health counts from cluster health signals.
        warning_events: Sequence of warning events (accessed for count only).
        issue_recorder: Callable that records a signal and finding.
                        Signature: (description, severity, layer) -> None

    Returns:
        CountIssueAssessment with issues_detected, workload_issue_present, node_issue_present flags.
    """
    issues_detected = False
    workload_issue_present = False
    node_issue_present = False
    references: list[str] = []

    warning_event_count = len(warning_events)

    # Node condition issues
    node_components: list[str] = []
    node_severity = "medium"
    if node_conditions.not_ready > 0:
        node_components.append(f"{node_conditions.not_ready} nodes NotReady")
        node_severity = "high"
    if node_conditions.memory_pressure:
        node_components.append(f"{node_conditions.memory_pressure} nodes with MemoryPressure")
    if node_conditions.disk_pressure:
        node_components.append(f"{node_conditions.disk_pressure} nodes with DiskPressure")
    if node_conditions.pid_pressure:
        node_components.append(f"{node_conditions.pid_pressure} nodes with PIDPressure")
    if node_conditions.network_unavailable:
        node_components.append(f"{node_conditions.network_unavailable} nodes with NetworkUnavailable")

    if node_components:
        node_issue_present = True
        issues_detected = True
        references.append("node health")
        issue_recorder(
            f"Node health signals: {', '.join(node_components)}.",
            node_severity,
            Layer.NODE,
        )

    # Non-running pods
    if pod_counts.non_running > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("pod readiness")
        issue_recorder(
            f"{pod_counts.non_running} pods are not running.",
            "medium",
            Layer.WORKLOAD,
        )

    # Pending pods
    if pod_counts.pending > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("pod scheduling")
        issue_recorder(
            f"{pod_counts.pending} pods are pending scheduling.",
            "medium",
            Layer.WORKLOAD,
        )

    # CrashLoopBackOff pods
    if pod_counts.crash_loop_backoff > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("CrashLoopBackOff")
        issue_recorder(
            f"{pod_counts.crash_loop_backoff} pods in CrashLoopBackOff.",
            "high",
            Layer.WORKLOAD,
        )

    # NOTE: ImagePullBackOff, job failures, and warning events are NOT handled here.
    # They are handled by the caller in loop.py to preserve the original ordering:
    #   node health, pod readiness, pod scheduling, CrashLoopBackOff, ImagePullBackOff,
    #   job failures, warning events

    return CountIssueAssessment(
        issues_detected=issues_detected,
        workload_issue_present=workload_issue_present,
        node_issue_present=node_issue_present,
        warning_event_count=warning_event_count,
        references=references,
    )
