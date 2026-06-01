"""Tests for loop_assessment_counts module.

Verifies count/condition issue classification behavior in isolation.
The helper handles: node health, pod readiness, pod scheduling, CrashLoopBackOff.
The caller handles: ImagePullBackOff, job failures, warning events.
"""

from __future__ import annotations

from dataclasses import dataclass

from k8s_diag_agent.collect.cluster_snapshot import (
    NodeConditionCounts,
    PodHealthCounts,
)
from k8s_diag_agent.health.loop_assessment_counts import assess_count_issues
from k8s_diag_agent.models import Layer


@dataclass
class MockWarningEvent:
    """Mock warning event for testing."""

    namespace: str
    reason: str
    message: str = ""


@dataclass
class RecordedIssue:
    """Records an issue call for verification."""

    description: str
    severity: str
    layer: Layer


class TestCountIssueAssessment:
    """Tests for CountIssueAssessment dataclass."""

    def test_empty_healthy_cluster(self) -> None:
        """All-zero health signals produce no issues."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )
        assert result.issues_detected is False
        assert result.workload_issue_present is False
        assert result.node_issue_present is False
        assert result.warning_event_count == 0
        assert result.references == []

    def test_warning_event_count_returned(self) -> None:
        """warning_event_count is correctly returned."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[MockWarningEvent('default', 'TestReason')],
            issue_recorder=lambda d, s, layer: None,
        )
        assert result.warning_event_count == 1


class TestNodeConditionIssues:
    """Tests for node condition issue detection."""

    def test_not_ready_nodes_set_node_issue(self) -> None:
        """NotReady nodes set node_issue_present flag."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=3, ready=1, not_ready=2, memory_pressure=0,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert result.node_issue_present is True
        assert result.issues_detected is True
        assert len(issues) == 1
        assert "2 nodes NotReady" in issues[0].description
        assert issues[0].severity == "high"
        assert issues[0].layer == Layer.NODE

    def test_network_unavailable_nodes_set_node_issue(self) -> None:
        """NetworkUnavailable nodes set node_issue_present flag."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=2, ready=1, not_ready=0, memory_pressure=0,
                disk_pressure=1, pid_pressure=0, network_unavailable=1,
            ),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert result.node_issue_present is True
        assert result.issues_detected is True
        assert "1 nodes with NetworkUnavailable" in issues[0].description
        assert "1 nodes with DiskPressure" in issues[0].description
        assert issues[0].severity == "medium"  # Not not_ready, so medium

    def test_all_node_conditions_set_high_severity(self) -> None:
        """NotReady sets high severity for node issues."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=3, not_ready=2, memory_pressure=1,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert issues[0].severity == "high"  # NotReady present


class TestPodCountIssues:
    """Tests for pod count issue detection."""

    def test_non_running_pods_set_workload_issue(self) -> None:
        """Non-running pods set workload_issue_present flag."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=3, pending=0, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert result.workload_issue_present is True
        assert result.issues_detected is True
        assert "3 pods are not running" in issues[0].description
        assert issues[0].severity == "medium"
        assert issues[0].layer == Layer.WORKLOAD

    def test_pending_pods_set_workload_issue(self) -> None:
        """Pending pods set workload_issue_present flag."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=0, pending=2, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert result.workload_issue_present is True
        assert "2 pods are pending scheduling" in issues[0].description
        assert issues[0].severity == "medium"

    def test_crash_loop_backoff_sets_high_severity(self) -> None:
        """CrashLoopBackOff pods set high severity."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=0, pending=0, crash_loop_backoff=4,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert issues[0].severity == "high"
        assert "4 pods in CrashLoopBackOff" in issues[0].description

    def test_multiple_pod_issues_preserve_order(self) -> None:
        """Multiple pod issues are recorded in expected order."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts(
                non_running=1, pending=2, crash_loop_backoff=3,
                image_pull_backoff=4, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=record_issue,
        )

        # Order: non_running, pending, crash_loop (ImagePullBackOff handled by caller)
        assert len(issues) == 3
        assert "1 pods are not running" in issues[0].description
        assert "2 pods are pending scheduling" in issues[1].description
        assert "3 pods in CrashLoopBackOff" in issues[2].description


class TestMultipleIssueTypes:
    """Tests for combined issue detection."""

    def test_node_and_workload_issues_both_present(self) -> None:
        """Both node and workload issues can be present simultaneously."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=3, ready=2, not_ready=1, memory_pressure=0,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts(
                non_running=2, pending=0, crash_loop_backoff=0,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=record_issue,
        )

        assert result.node_issue_present is True
        assert result.workload_issue_present is True
        assert result.issues_detected is True
        assert len(issues) == 2


class TestSignalFindingOrder:
    """Tests for signal/finding creation order."""

    def test_issue_order_is_deterministic(self) -> None:
        """Issues are recorded in deterministic order."""
        issues: list[RecordedIssue] = []

        def record_issue(desc: str, sev: str, layer: Layer) -> None:
            issues.append(RecordedIssue(desc, sev, layer))

        # Multiple issues of different types
        assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=3, not_ready=2, memory_pressure=1,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts(
                non_running=1, pending=1, crash_loop_backoff=1,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[MockWarningEvent("default", "Reason")],  # Not handled by helper
            issue_recorder=record_issue,
        )

        # Order: node, non_running, pending, crash_loop
        # (job failures and warning events are NOT handled by the helper)
        assert len(issues) == 4
        assert issues[0].layer == Layer.NODE  # Node issues first
        assert "2 nodes NotReady" in issues[0].description
        assert "1 nodes with MemoryPressure" in issues[0].description

        assert issues[1].layer == Layer.WORKLOAD
        assert "1 pods are not running" in issues[1].description

        assert issues[2].layer == Layer.WORKLOAD
        assert "1 pods are pending" in issues[2].description

        assert issues[3].layer == Layer.WORKLOAD
        assert "CrashLoopBackOff" in issues[3].description


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
                non_running=1, pending=2, crash_loop_backoff=3,
                image_pull_backoff=0, completed_job_pods=0,
            ),
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )

        # References in order: node health, pod readiness, pod scheduling, CrashLoopBackOff
        assert result.references == [
            "node health",
            "pod readiness",
            "pod scheduling",
            "CrashLoopBackOff",
        ]

    def test_references_empty_when_no_issues(self) -> None:
        """References are empty when no issues detected."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
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
            warning_events=[],
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
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )

        assert "ImagePullBackOff" not in result.references

    def test_references_exclude_job_failures(self) -> None:
        """Job failures is NOT in references (caller handles it)."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )

        assert "job failures" not in result.references

    def test_references_exclude_warning_events(self) -> None:
        """Warning events is NOT in references (caller handles it)."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts.empty(),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )

        assert "warning events" not in result.references

    def test_references_include_node_health(self) -> None:
        """Node health is included in references when nodes have issues."""
        result = assess_count_issues(
            node_conditions=NodeConditionCounts(
                total=5, ready=3, not_ready=2, memory_pressure=1,
                disk_pressure=0, pid_pressure=0, network_unavailable=0,
            ),
            pod_counts=PodHealthCounts.empty(),
            warning_events=[],
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
            warning_events=[],
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
            warning_events=[],
            issue_recorder=lambda d, s, layer: None,
        )

        assert "pod scheduling" in result.references
