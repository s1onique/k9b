"""Tests for scheduler health gate contracts."""

from __future__ import annotations

from scripts.scheduler_health_gate.contracts import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
    SCHEDULER_POD_SELECTOR,
    SchedulerHealthResult,
)


class TestSchedulerHealthResult:
    """Tests for SchedulerHealthResult type."""

    def test_default_values(self) -> None:
        """SchedulerHealthResult has correct defaults."""
        result = SchedulerHealthResult()
        assert result.passed is False
        assert result.failure_class == ""
        assert result.failure_reason == ""
        assert result.failure_details == ""
        assert result.deployment_found is False
        assert result.deployment_name == ""
        assert result.pod_count == 0
        assert result.ready_replicas == 0
        assert result.available_replicas == 0
        assert result.crash_loop_pods == []
        assert result.waiting_pods == []
        assert result.terminated_pods == []
        assert result.namespace_events == []
        assert result.scheduler_pods_json == ""
        assert result.scheduler_diagnosis == {}

    def test_to_dict(self) -> None:
        """Serializes to dict correctly."""
        result = SchedulerHealthResult()
        result.passed = False
        result.failure_class = FAILURE_SCHEDULER_CRASH_LOOP
        result.deployment_name = "k9b-scheduler"
        result.crash_loop_pods = [
            {"pod": "test-pod", "container": "test", "reason": "CrashLoopBackOff", "restart_count": 3}
        ]

        data = result.to_dict()
        assert data["passed"] is False
        assert data["failure_class"] == FAILURE_SCHEDULER_CRASH_LOOP
        assert len(data["crash_loop_pods"]) == 1
        assert data["crash_loop_pods"][0]["restart_count"] == 3

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict includes all fields."""
        result = SchedulerHealthResult()
        result.passed = True
        result.failure_class = ""
        result.deployment_found = True
        result.deployment_name = SCHEDULER_DEPLOYMENT_NAME
        result.pod_count = 1
        result.ready_replicas = 1
        result.available_replicas = 1
        result.crash_loop_pods = [{"pod": "p1", "container": "c1", "reason": "Test", "restart_count": 0}]
        result.waiting_pods = [{"pod": "p2", "container": "c1", "reason": "Pending", "message": "", "phase": "Pending"}]
        result.terminated_pods = []
        result.namespace_events = [{"reason": "Started"}]
        result.scheduler_pods_json = '{"items": []}'
        result.scheduler_diagnosis = {"timestamp": "2026-01-01"}

        data = result.to_dict()
        assert data["passed"] is True
        assert data["failure_class"] == ""
        assert data["deployment_found"] is True
        assert data["deployment_name"] == SCHEDULER_DEPLOYMENT_NAME
        assert data["pod_count"] == 1
        assert data["ready_replicas"] == 1
        assert data["available_replicas"] == 1
        assert len(data["crash_loop_pods"]) == 1
        assert len(data["waiting_pods"]) == 1
        assert len(data["terminated_pods"]) == 0
        assert len(data["namespace_events"]) == 1
        assert data["scheduler_pods_json"] == '{"items": []}'
        assert data["scheduler_diagnosis"] == {"timestamp": "2026-01-01"}


class TestConstants:
    """Tests for contract constants."""

    def test_failure_class_constants(self) -> None:
        """Failure class constants are non-empty strings."""
        assert FAILURE_SCHEDULER_NOT_READY == "scheduler_not_ready"
        assert FAILURE_SCHEDULER_CRASH_LOOP == "scheduler_crash_loop"
        assert FAILURE_SCHEDULER_MISSING == "scheduler_missing"

    def test_deployment_name_constant(self) -> None:
        """SCHEDULER_DEPLOYMENT_NAME is set."""
        assert SCHEDULER_DEPLOYMENT_NAME == "k9b-scheduler"

    def test_pod_selector_constant(self) -> None:
        """SCHEDULER_POD_SELECTOR is set."""
        assert SCHEDULER_POD_SELECTOR == "app.kubernetes.io/name=k9b-scheduler"
