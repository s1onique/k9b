"""Tests for loop_assessment_counts module - reference tracking.

Verifies that references are correctly collected and returned by assess_count_issues.
"""

from __future__ import annotations

from k8s_diag_agent.collect.cluster_snapshot import (
    NodeConditionCounts,
    PodHealthCounts,
)
from k8s_diag_agent.health.loop_assessment_counts import assess_count_issues


class MockWarningEvent:
    """Mock warning event for testing."""

    def __init__(self, namespace: str, reason: str, message: str = "") -> None:
        self.namespace = namespace
        self.reason = reason
        self.message = message


class TestReferencesReturned:
    """Tests for references returned in CountIssueAssessment."""

    def test_references_collected_in_order(self) -> None:
        """References are returned in the same order as issue detection."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=3, ready=1, not_ready=2, memory_pressure=0,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts(
                non_running=1, pending=2, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=3,
            warning_events=[MockWarningEvent("default", "Reason")],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        # References in order: node health, pod readiness, pod scheduling,
        # job failures, warning events
        # ImagePullBackOff is NOT in the list (handled by caller)
        assert result.references == [
            "node health",
            "pod readiness",
            "pod scheduling",
            "job failures",
            "warning events",
        ]

    def test_references_empty_when_no_issues(self) -> None:
        """References are empty when no issues detected."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert result.references == []

    def test_references_include_crash_loop_backoff(self) -> None:
        """CrashLoopBackOff is included in references."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=0, pending=0, crash_loop_backoff=2,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "CrashLoopBackOff" in result.references

    def test_references_exclude_image_pull_backoff(self) -> None:
        """ImagePullBackOff is NOT in references (caller handles it)."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=0, pending=0, crash_loop_backoff=0,
                image_pull_backoff=3, completed_job_pods=0,
            ),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "ImagePullBackOff" not in result.references

    def test_references_include_node_health(self) -> None:
        """Node health is included in references when nodes have issues."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=3, not_ready=2, memory_pressure=1,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts.empty(),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "node health" in result.references

    def test_references_include_pod_readiness(self) -> None:
        """Pod readiness is included when non_running > 0."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=3, pending=0, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "pod readiness" in result.references

    def test_references_include_pod_scheduling(self) -> None:
        """Pod scheduling is included when pending > 0."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=0, pending=2, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "pod scheduling" in result.references

    def test_references_include_job_failures(self) -> None:
        """Job failures is included when job_failures > 0."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            job_failures=5,
            warning_events=[],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "job failures" in result.references

    def test_references_include_warning_events(self) -> None:
        """Warning events is included when threshold is triggered."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            job_failures=0,
            warning_events=[MockWarningEvent("default", "Reason")],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        assert "warning events" in result.references

    def test_references_order_with_all_issue_types(self) -> None:
        """References follow exact detection order across all issue types."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=4, not_ready=1, memory_pressure=0,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts(
                non_running=1, pending=1, crash_loop_backoff=1,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=1,
            warning_events=[
                MockWarningEvent("default", "Reason1"),
                MockWarningEvent("kube-system", "Reason2"),
            ],
            warning_event_threshold=0,
            issue_recorder=lambda d, s, layer: None,
        )

        # Exact order must match original code:
        # 1. node health (when node_components is non-empty)
        # 2. pod readiness (non_running > 0)
        # 3. pod scheduling (pending > 0)
        # 4. CrashLoopBackOff (crash_loop_backoff > 0)
        # 5. job failures (job_failures > 0)
        # 6. warning events (when threshold triggered)
        # ImagePullBackOff NOT included (caller handles it)
        assert result.references == [
            "node health",
            "pod readiness",
            "pod scheduling",
            "CrashLoopBackOff",
            "job failures",
            "warning events",
        ]

    def test_references_excludes_non_triggered_conditions(self) -> None:
        """References only include conditions that actually triggered."""
        # Only non_running triggers
        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=5, not_ready=0, memory_pressure=0,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts(
                non_running=2, pending=0, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            job_failures=0,
            warning_events=[],
            warning_event_threshold=5,  # 0 < 5, not triggered
            issue_recorder=lambda d, s, layer: None,
        )

        assert result.references == ["pod readiness"]