"""Tests for loop_assessment_regressions module (detection tests)."""

from __future__ import annotations

from k8s_diag_agent.health.loop_assessment_regressions import check_regression_from_history
from k8s_diag_agent.health.loop_history import HealthHistoryEntry
from k8s_diag_agent.models import Finding, Layer, Signal


def _make_snapshot(
    cluster_id: str = "cluster-test",
    not_ready_nodes: int = 0,
    non_running_pods: int = 0,
    pending_pods: int = 0,
    crash_loop_pods: int = 0,
    image_pull_backoff_pods: int = 0,
    job_failures: int = 0,
    warning_event_count: int = 0,
) -> object:
    """Create a minimal mock snapshot for testing regression detection."""
    node_conditions = type(
        "NodeConditions",
        (),
        {
            "not_ready": not_ready_nodes,
            "memory_pressure": 0,
            "disk_pressure": 0,
            "pid_pressure": 0,
            "network_unavailable": 0,
        },
    )()

    pod_counts = type(
        "PodCounts",
        (),
        {
            "non_running": non_running_pods,
            "pending": pending_pods,
            "crash_loop_backoff": crash_loop_pods,
            "image_pull_backoff": image_pull_backoff_pods,
        },
    )()

    warning_events = [
        type("WarningEvent", (), {"namespace": "default", "reason": "Test", "message": "Test"})()
    ] * warning_event_count

    health_signals = type(
        "HealthSignals",
        (),
        {
            "node_conditions": node_conditions,
            "pod_counts": pod_counts,
            "job_failures": job_failures,
            "warning_events": warning_events,
        },
    )()

    metadata = type(
        "Metadata",
        (),
        {
            "cluster_id": cluster_id,
            "node_count": 1,
            "pod_count": 10,
            "control_plane_version": "v1.28.0",
        },
    )()

    snapshot = type("Snapshot", (), {"metadata": metadata, "health_signals": health_signals})()
    return snapshot


def _make_history(
    cluster_id: str = "cluster-test",
    not_ready_nodes: int = 0,
    non_running_pods: int = 0,
    pending_pods: int = 0,
    crash_loop_pods: int = 0,
    image_pull_backoff_pods: int = 0,
    job_failures: int = 0,
    warning_event_count: int = 0,
) -> HealthHistoryEntry:
    """Create a minimal mock history entry for testing regression detection."""
    return HealthHistoryEntry(
        cluster_id=cluster_id,
        node_count=1,
        pod_count=10,
        control_plane_version="v1.28.0",
        health_rating=type("HealthRating", (), {"value": "healthy"})(),
        missing_evidence=(),
        watched_helm_releases={},
        watched_crd_families={},
        node_conditions={"not_ready": not_ready_nodes},
        pod_counts={
            "non_running": non_running_pods,
            "pending": pending_pods,
            "crash_loop_backoff": crash_loop_pods,
            "image_pull_backoff": image_pull_backoff_pods,
        },
        job_failures=job_failures,
        warning_event_count=warning_event_count,
        cluster_class="test",
        cluster_role="primary",
        baseline_cohort="test",
        baseline_policy_path=None,
    )


def _signal_id_generator() -> callable:
    """Simple signal ID generator for testing."""
    _counter = [0]

    def generator() -> str:
        _counter[0] += 1
        return f"sig-{_counter[0]}"

    return generator


class TestCheckRegressionFromHistory:
    """Tests for check_regression_from_history function."""

    def test_no_previous_history_with_zeros(self) -> None:
        """Without history and all zeros, no regressions should be detected."""
        snapshot = _make_snapshot(
            not_ready_nodes=0,
            non_running_pods=0,
            warning_event_count=0,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=None,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is False
        assert len(signals) == 0
        assert len(findings) == 0

    def test_equal_values_no_regression(self) -> None:
        """When values are equal, no regression should be detected."""
        snapshot = _make_snapshot(
            not_ready_nodes=2,
            non_running_pods=3,
        )
        history = _make_history(
            not_ready_nodes=2,
            non_running_pods=3,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is False
        assert len(signals) == 0

    def test_increased_not_ready_nodes_detected(self) -> None:
        """Increased NotReady nodes should be detected as regression."""
        snapshot = _make_snapshot(not_ready_nodes=3)
        history = _make_history(not_ready_nodes=1)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert result.node_regression is True
        assert len(signals) == 1
        assert signals[0].layer == Layer.NODE
        assert "NotReady" in signals[0].description
        assert len(findings) == 1

    def test_increased_non_running_pods_detected(self) -> None:
        """Increased non-running pods should be detected as workload regression."""
        snapshot = _make_snapshot(non_running_pods=5)
        history = _make_history(non_running_pods=2)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert result.workload_regression is True
        assert len(signals) == 1
        assert signals[0].layer == Layer.WORKLOAD
        assert "Non-running pods" in signals[0].description

    def test_increased_crash_loop_detected(self) -> None:
        """Increased CrashLoopBackOff pods should be detected."""
        snapshot = _make_snapshot(crash_loop_pods=4)
        history = _make_history(crash_loop_pods=1)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert len(signals) == 1
        assert "CrashLoopBackOff" in signals[0].description

    def test_increased_image_pull_backoff_detected(self) -> None:
        """Increased ImagePullBackOff pods should be detected."""
        snapshot = _make_snapshot(image_pull_backoff_pods=2)
        history = _make_history(image_pull_backoff_pods=0)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert len(signals) == 1
        assert "ImagePullBackOff" in signals[0].description

    def test_increased_job_failures_detected(self) -> None:
        """Increased job failures should be detected."""
        snapshot = _make_snapshot(job_failures=5)
        history = _make_history(job_failures=1)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert len(signals) == 1
        assert "Job failure" in signals[0].description
        assert signals[0].layer == Layer.WORKLOAD

    def test_increased_warning_events_detected(self) -> None:
        """Increased warning events should be detected as observability layer."""
        snapshot = _make_snapshot(warning_event_count=10)
        history = _make_history(warning_event_count=3)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=10,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert len(signals) == 1
        assert "Warning events" in signals[0].description
        assert signals[0].layer == Layer.OBSERVABILITY  # Warning events mapped to OBSERVABILITY

    def test_signals_and_findings_created_on_regression(self) -> None:
        """Signals and findings should be created when regression detected."""
        snapshot = _make_snapshot(
            not_ready_nodes=3,
            non_running_pods=5,
        )
        history = _make_history(
            not_ready_nodes=1,
            non_running_pods=2,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        # Two regressions detected
        assert result.has_regression is True
        assert len(signals) == 2
        assert len(findings) == 2

        # Verify signal structure
        for signal in signals:
            assert signal.id.startswith("sig-")
            assert signal.severity == "medium"
            assert signal.layer in (Layer.NODE, Layer.WORKLOAD)

        # Verify finding structure
        for finding in findings:
            assert finding.id.startswith("sig-")
            assert len(finding.supporting_signals) == 1
            assert finding.layer in (Layer.NODE, Layer.WORKLOAD)

    def test_pending_pods_regression_detected(self) -> None:
        """Increased pending pods should be detected."""
        snapshot = _make_snapshot(pending_pods=3)
        history = _make_history(pending_pods=0)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert len(signals) == 1
        assert "Pending pod" in signals[0].description
        assert signals[0].layer == Layer.WORKLOAD

    def test_multiple_regressions_detected(self) -> None:
        """Multiple regressions should be detected."""
        snapshot = _make_snapshot(
            not_ready_nodes=1,
            non_running_pods=1,
            pending_pods=1,
            crash_loop_pods=1,
            image_pull_backoff_pods=1,
            job_failures=1,
            warning_event_count=1,
        )
        history = _make_history(
            not_ready_nodes=0,
            non_running_pods=0,
            pending_pods=0,
            crash_loop_pods=0,
            image_pull_backoff_pods=0,
            job_failures=0,
            warning_event_count=0,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=1,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        # All 7 regressions detected
        assert result.has_regression is True
        assert len(signals) == 7
        # Warning events don't set workload/node flags
        assert result.workload_regression is True
        assert result.node_regression is True
        assert result.references == ["regression"] * 7
        assert len(findings) == 7

    def test_signal_ids_are_unique_across_signals_and_findings(self) -> None:
        """Signal and finding IDs should not conflict with each other."""
        snapshot = _make_snapshot(
            not_ready_nodes=3,
            non_running_pods=5,
        )
        history = _make_history(
            not_ready_nodes=1,
            non_running_pods=2,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=0,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        # All IDs should be unique
        all_ids = [s.id for s in signals] + [f.id for f in findings]
        assert len(all_ids) == len(set(all_ids))

    def test_warning_event_regression_does_not_set_workload_or_node_flags(self) -> None:
        """Warning event regression should not set workload or node regression flags."""
        snapshot = _make_snapshot(warning_event_count=10)
        history = _make_history(warning_event_count=3)
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=10,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        assert result.has_regression is True
        assert result.workload_regression is False
        assert result.node_regression is False
        assert len(signals) == 1

    def test_references_has_one_per_detected_regression(self) -> None:
        """References should have one 'regression' per detected regression."""
        snapshot = _make_snapshot(
            not_ready_nodes=1,
            non_running_pods=1,
            pending_pods=1,
            crash_loop_pods=1,
            image_pull_backoff_pods=1,
            job_failures=1,
            warning_event_count=1,
        )
        history = _make_history(
            not_ready_nodes=0,
            non_running_pods=0,
            pending_pods=0,
            crash_loop_pods=0,
            image_pull_backoff_pods=0,
            job_failures=0,
            warning_event_count=0,
        )
        signals: list[Signal] = []
        findings: list[Finding] = []
        gen = _signal_id_generator()

        result = check_regression_from_history(
            snapshot=snapshot,
            previous=history,
            warning_event_count=1,
            signals=signals,
            signal_id_generator=gen,
            findings=findings,
        )

        # All 7 regressions detected
        assert result.has_regression is True
        # Warning events don't set workload/node flags
        assert result.workload_regression is True
        assert result.node_regression is True
        assert result.references == ["regression"] * 7
