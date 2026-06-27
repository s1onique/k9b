"""Tests for scheduler health gate evaluation logic."""

from __future__ import annotations

from typing import Any

from scripts.scheduler_health_gate.evaluate import (
    check_crash_loop,
    check_terminated_pods,
    check_waiting_pods,
    evaluate_scheduler_health,
)


class TestCheckCrashLoop:
    """Tests for check_crash_loop function."""

    def test_no_crash_loop(self, healthy_pods_response: dict[str, Any]) -> None:
        """No crash loop when pod is running."""
        result = check_crash_loop(healthy_pods_response)
        assert result == []

    def test_crash_loop_backoff(self, crash_loop_pods_response: dict[str, Any]) -> None:
        """Detects CrashLoopBackOff state."""
        result = check_crash_loop(crash_loop_pods_response)
        assert len(result) == 1
        assert result[0]["reason"] == "CrashLoopBackOff"
        assert result[0]["restart_count"] == 5
        assert result[0]["pod"] == "k9b-scheduler-crashing"
        assert result[0]["container"] == "scheduler"

    def test_crash_loop_includes_last_state_evidence(self) -> None:
        """Includes lastState.terminated evidence in crash loop detection."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "k9b-scheduler-crashing"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off 5m0s starting",
                                    }
                                },
                                "restartCount": 2,
                                "lastState": {
                                    "terminated": {
                                        "exitCode": 1,
                                        "reason": "Error",
                                        "message": "ConfigError: missing required env",
                                    }
                                },
                            }
                        ],
                    },
                }
            ]
        }
        result = check_crash_loop(pods_data)
        assert len(result) == 1
        assert result[0]["last_exit_code"] == 1
        assert result[0]["last_exit_reason"] == "Error"
        assert result[0]["last_exit_message"] == "ConfigError: missing required env"

    def test_error_state(self) -> None:
        """Detects Error waiting state."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "scheduler-error"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {"waiting": {"reason": "Error", "message": "exited"}},
                                "restartCount": 1,
                            }
                        ],
                    },
                }
            ]
        }
        result = check_crash_loop(pods_data)
        assert len(result) == 1
        assert result[0]["reason"] == "Error"

    def test_terminated_with_nonzero_exit(self) -> None:
        """Detects terminated containers with non-zero exit code."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "scheduler-crashed"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "terminated": {
                                        "exitCode": 1,
                                        "reason": "",
                                        "startedAt": "2026-01-01T00:00:00Z",
                                        "finishedAt": "2026-01-01T00:01:00Z",
                                    }
                                },
                                "restartCount": 1,
                            }
                        ],
                    },
                }
            ]
        }
        result = check_crash_loop(pods_data)
        assert len(result) == 1
        assert result[0]["reason"] == "exit_code_1"
        assert result[0]["exit_code"] == 1

    def test_terminated_includes_exit_message(self) -> None:
        """Includes exit message in terminated container detection."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "scheduler-crashed"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "terminated": {
                                        "exitCode": 127,
                                        "reason": "Error",
                                        "message": "File not found: /app/scripts/run_scheduler.py",
                                    }
                                },
                                "restartCount": 1,
                            }
                        ],
                    },
                }
            ]
        }
        result = check_crash_loop(pods_data)
        assert len(result) == 1
        assert result[0]["exit_code"] == 127
        assert result[0]["exit_reason"] == "Error"
        assert result[0]["exit_message"] == "File not found: /app/scripts/run_scheduler.py"

    def test_empty_items(self) -> None:
        """Handles empty items list."""
        result = check_crash_loop({"items": []})
        assert result == []


class TestCheckWaitingPods:
    """Tests for check_waiting_pods function."""

    def test_no_waiting_pods(self, healthy_pods_response: dict[str, Any]) -> None:
        """No waiting pods when running."""
        result = check_waiting_pods(healthy_pods_response)
        assert result == []

    def test_container_creating(self, partial_ready_pods_response: dict[str, Any]) -> None:
        """Detects ContainerCreating waiting state."""
        result = check_waiting_pods(partial_ready_pods_response)
        assert len(result) == 1
        assert result[0]["reason"] == "ContainerCreating"

    def test_excludes_crash_loop(self) -> None:
        """Does not include CrashLoopBackOff in waiting pods."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "test-pod"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off",
                                    }
                                },
                                "restartCount": 5,
                            }
                        ],
                    },
                }
            ]
        }
        result = check_waiting_pods(pods_data)
        assert result == []

    def test_empty_items(self) -> None:
        """Handles empty items list."""
        result = check_waiting_pods({"items": []})
        assert result == []


class TestCheckTerminatedPods:
    """Tests for check_terminated_pods function."""

    def test_no_terminated_pods(self, healthy_pods_response: dict[str, Any]) -> None:
        """No terminated pods when running."""
        result = check_terminated_pods(healthy_pods_response)
        assert result == []

    def test_succeeded_pod(self) -> None:
        """Detects Succeeded pods."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "completed-pod"},
                    "status": {"phase": "Succeeded"},
                }
            ]
        }
        result = check_terminated_pods(pods_data)
        assert len(result) == 1
        assert result[0]["reason"] == "pod_succeeded"
        assert result[0]["phase"] == "Succeeded"

    def test_failed_pod(self) -> None:
        """Detects Failed pods."""
        pods_data = {
            "items": [
                {
                    "metadata": {"name": "failed-pod"},
                    "status": {"phase": "Failed"},
                }
            ]
        }
        result = check_terminated_pods(pods_data)
        assert len(result) == 1
        assert result[0]["reason"] == "pod_failed"
        assert result[0]["phase"] == "Failed"

    def test_empty_items(self) -> None:
        """Handles empty items list."""
        result = check_terminated_pods({"items": []})
        assert result == []


class TestEvaluateSchedulerHealth:
    """Tests for evaluate_scheduler_health function."""

    def test_missing_deployment(self) -> None:
        """Fails when deployment not found."""
        deployment = {"found": False}
        pods: dict[str, list[dict[str, object]]] = {"items": []}
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is False
        assert failure_class == "scheduler_missing"
        assert failure_reason == "scheduler_deployment_not_found"

    def test_crash_loop_takes_precedence(self) -> None:
        """Crash loop is detected even if deployment looks ready."""
        deployment = {"found": True, "ready_replicas": 1, "replicas": 1}
        pods = {
            "items": [
                {
                    "metadata": {"name": "crashing-pod"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                "restartCount": 5,
                            }
                        ],
                    },
                }
            ]
        }
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is False
        assert failure_class == "scheduler_crash_loop"
        assert "CrashLoopBackOff" in failure_details

    def test_no_pods_with_replicas_expected(self) -> None:
        """Fails when deployment expects pods but none exist."""
        deployment = {"found": True, "ready_replicas": 0, "replicas": 1}
        pods: dict[str, list[dict[str, object]]] = {"items": []}
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is False
        assert failure_class == "scheduler_not_ready"
        assert failure_reason == "scheduler_no_pods"

    def test_pods_but_none_ready(self) -> None:
        """Fails when pods exist but none are ready."""
        deployment = {"found": True, "ready_replicas": 0, "replicas": 1}
        pods = {
            "items": [
                {
                    "metadata": {"name": "pending-pod"},
                    "status": {
                        "phase": "Pending",
                        "containerStatuses": [],
                    },
                }
            ]
        }
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is False
        assert failure_class == "scheduler_not_ready"
        assert failure_reason == "scheduler_no_ready_replicas"

    def test_healthy_scheduler(self) -> None:
        """Passes when scheduler is healthy."""
        deployment = {"found": True, "ready_replicas": 1, "replicas": 1}
        pods = {
            "items": [
                {
                    "metadata": {"name": "healthy-pod"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {"running": {}},
                                "restartCount": 0,
                            }
                        ],
                    },
                }
            ]
        }
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is True
        assert failure_class == ""
        assert failure_reason == ""
        assert failure_details == ""

    def test_partial_readiness_passes(self) -> None:
        """Partial readiness passes (warning only)."""
        deployment = {"found": True, "ready_replicas": 1, "replicas": 2}
        pods = {
            "items": [
                {
                    "metadata": {"name": "ready-pod"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {"running": {}},
                                "restartCount": 0,
                            }
                        ],
                    },
                }
            ]
        }
        
        passed, failure_class, failure_reason, failure_details = evaluate_scheduler_health(
            deployment, pods
        )
        
        assert passed is True
