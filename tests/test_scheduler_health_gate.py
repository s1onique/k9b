"""Tests for scheduler health gate.

Tests the scheduler readiness check that runs before incident discovery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.scheduler_health_gate.main import (
    FAILURE_SCHEDULER_CRASH_LOOP,
    FAILURE_SCHEDULER_MISSING,
    FAILURE_SCHEDULER_NOT_READY,
    SCHEDULER_DEPLOYMENT_NAME,
    SCHEDULER_POD_SELECTOR,
    _check_crash_loop,
    _check_waiting_pods,
    _get_scheduler_deployment_status,
    _get_scheduler_pod_selector,
    _get_scheduler_pods,
    run_scheduler_health_gate,
)
from scripts.scheduler_health_gate.types import SchedulerHealthResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_kubectl(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock kubectl command responses."""
    responses: dict[str, tuple[int, str, str]] = {}

    def mock_run_kubectl(
        kubeconfig: str,
        namespace: str,
        args: list[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        key = " ".join(args)
        if key in responses:
            return responses[key]
        return (1, "", "kubectl failed")

    monkeypatch.setattr(
        "scripts.scheduler_health_gate.main._run_kubectl",
        mock_run_kubectl,
    )
    return responses


@pytest.fixture
def healthy_deployment_response() -> dict[str, Any]:
    """A healthy scheduler deployment (snake_case keys matching helper output)."""
    return {
        "found": True,
        "name": SCHEDULER_DEPLOYMENT_NAME,
        "replicas": 1,
        "ready_replicas": 1,
        "available_replicas": 1,
        "updated_replicas": 1,
    }


@pytest.fixture
def healthy_pods_response() -> dict[str, Any]:
    """A healthy scheduler pod."""
    return {
        "apiVersion": "v1",
        "items": [
            {
                "metadata": {"name": "k9b-scheduler-abc123"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "name": "scheduler",
                            "state": {"running": {"startedAt": "2026-01-01T00:00:00Z"}},
                            "restartCount": 0,
                        }
                    ],
                },
            }
        ],
    }


@pytest.fixture
def crash_loop_pods_response() -> dict[str, Any]:
    """A scheduler pod in CrashLoopBackOff."""
    return {
        "apiVersion": "v1",
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
                            "restartCount": 5,
                        }
                    ],
                },
            }
        ],
    }


@pytest.fixture
def missing_deployment_response() -> dict[str, Any]:
    """Scheduler deployment not found."""
    return {"found": False, "name": SCHEDULER_DEPLOYMENT_NAME, "error": "deployment not found"}


@pytest.fixture
def partial_ready_pods_response() -> dict[str, Any]:
    """Scheduler pods exist but none are ready."""
    return {
        "apiVersion": "v1",
        "items": [
            {
                "metadata": {"name": "k9b-scheduler-xyz789"},
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [
                        {
                            "name": "scheduler",
                            "state": {
                                "waiting": {
                                    "reason": "ContainerCreating",
                                    "message": "creating container",
                                }
                            },
                            "restartCount": 0,
                        }
                    ],
                },
            }
        ],
    }


@pytest.fixture
def temp_artifact_dir(tmp_path: Path) -> Path:
    """Temporary artifact directory."""
    return tmp_path / "artifacts"


# =============================================================================
# Unit tests for helper functions
# =============================================================================


class TestCheckCrashLoop:
    """Tests for _check_crash_loop function."""

    def test_no_crash_loop(self, healthy_pods_response: dict[str, Any]) -> None:
        """No crash loop when pod is running."""
        result = _check_crash_loop(healthy_pods_response)
        assert result == []

    def test_crash_loop_backoff(self, crash_loop_pods_response: dict[str, Any]) -> None:
        """Detects CrashLoopBackOff state."""
        result = _check_crash_loop(crash_loop_pods_response)
        assert len(result) == 1
        assert result[0]["reason"] == "CrashLoopBackOff"
        assert result[0]["restart_count"] == 5
        assert result[0]["pod"] == "k9b-scheduler-crashing"
        assert result[0]["container"] == "scheduler"

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
        result = _check_crash_loop(pods_data)
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
        result = _check_crash_loop(pods_data)
        assert len(result) == 1
        assert result[0]["reason"] == "exit_code_1"
        assert result[0]["exit_code"] == 1


class TestCheckWaitingPods:
    """Tests for _check_waiting_pods function."""

    def test_no_waiting_pods(self, healthy_pods_response: dict[str, Any]) -> None:
        """No waiting pods when running."""
        result = _check_waiting_pods(healthy_pods_response)
        assert result == []

    def test_container_creating(self, partial_ready_pods_response: dict[str, Any]) -> None:
        """Detects ContainerCreating waiting state."""
        result = _check_waiting_pods(partial_ready_pods_response)
        assert len(result) == 1
        assert result[0]["reason"] == "ContainerCreating"


class TestGetSchedulerDeploymentStatus:
    """Tests for _get_scheduler_deployment_status function."""

    def test_deployment_found(
        self,
        mock_kubectl: dict[str, Any],
        healthy_deployment_response: dict[str, Any],
    ) -> None:
        """Returns found=True when deployment exists."""
        mock_kubectl["get deployment k9b-scheduler -o json"] = (
            0,
            json.dumps(
                {
                    "status": {
                        "readyReplicas": 1,
                        "availableReplicas": 1,
                    },
                    "spec": {"replicas": 1},
                }
            ),
            "",
        )

        result = _get_scheduler_deployment_status("/fake/kubeconfig", "test-ns")
        assert result["found"] is True
        assert result["ready_replicas"] == 1

    def test_deployment_not_found(self, mock_kubectl: dict[str, Any]) -> None:
        """Returns found=False when deployment doesn't exist."""
        mock_kubectl["get deployment k9b-scheduler -o json"] = (
            1,
            "",
            "not found",
        )

        result = _get_scheduler_deployment_status("/fake/kubeconfig", "test-ns")
        assert result["found"] is False


class TestGetSchedulerPods:
    """Tests for _get_scheduler_pods function."""

    def test_returns_pods_json(self, mock_kubectl: dict[str, Any], healthy_pods_response: dict[str, Any]) -> None:
        """Returns parsed pods JSON."""
        mock_kubectl["get pods -l app.kubernetes.io/name=k9b-scheduler -o json"] = (
            0,
            json.dumps(healthy_pods_response),
            "",
        )

        result = _get_scheduler_pods("/fake/kubeconfig", "test-ns", "app.kubernetes.io/name=k9b-scheduler")
        assert "items" in result
        assert len(result["items"]) == 1

    def test_returns_empty_on_error(self, mock_kubectl: dict[str, Any]) -> None:
        """Returns empty items on kubectl failure."""
        mock_kubectl["get pods -l app.kubernetes.io/name=k9b-scheduler -o json"] = (1, "", "error")

        result = _get_scheduler_pods("/fake/kubeconfig", "test-ns", "app.kubernetes.io/name=k9b-scheduler")
        assert result.get("items", []) == []


# =============================================================================
# Integration tests for run_scheduler_health_gate
# =============================================================================


class TestRunSchedulerHealthGate:
    """Integration tests for run_scheduler_health_gate."""

    def test_healthy_scheduler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        healthy_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Returns passed=True when scheduler is healthy."""
        # Mock deployment status
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        # Mock pod status
        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return healthy_pods_response

        # Mock events
        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_namespace_events",
            mock_get_events,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is True
        assert result.failure_class == ""
        assert result.deployment_found is True

    def test_crash_loop_fails_fast(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        crash_loop_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Fails immediately with scheduler_crash_loop when detected."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return crash_loop_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_namespace_events",
            mock_get_events,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_CRASH_LOOP
        assert "CrashLoopBackOff" in result.failure_details
        assert result.crash_loop_pods[0]["restart_count"] == 5

    def test_missing_deployment_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_deployment_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Fails immediately with scheduler_missing when deployment not found."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return missing_deployment_response

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_deployment_status",
            mock_get_deployment,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_MISSING

    def test_no_ready_replicas_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        partial_ready_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Fails with scheduler_not_ready when no replicas are ready."""
        deployment_response = {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "replicas": 1,
            "readyReplicas": 0,  # Not ready
            "availableReplicas": 0,
        }

        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return partial_ready_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_namespace_events",
            mock_get_events,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_NOT_READY



class TestZeroPodEdgeCase:
    """Tests for deployment exists but zero pods edge case."""

    def test_deployment_exists_but_no_pods_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        temp_artifact_dir: Path,
    ) -> None:
        """Fails with scheduler_not_ready when deployment expects pods but none exist."""
        deployment_response = {
            "found": True,
            "name": SCHEDULER_DEPLOYMENT_NAME,
            "replicas": 1,
            "ready_replicas": 0,  # Deployment expects 1 but none ready
            "available_replicas": 0,
        }

        # No pods exist
        pods_response = {"items": []}

        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._get_namespace_events",
            mock_get_events,
        )

        result = run_scheduler_health_gate(
            kubeconfig="/fake/kubeconfig",
            namespace="test-ns",
            artifact_dir=temp_artifact_dir,
        )

        assert result.passed is False
        assert result.failure_class == FAILURE_SCHEDULER_NOT_READY
        assert result.failure_reason == "scheduler_no_pods"




class TestGetSchedulerPodSelector:
    """Tests for pod selector derivation from deployment."""

    def test_derives_single_label_selector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Derives selector from Deployment.spec.selector.matchLabels with single label."""
        deployment_response = {
            "spec": {
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "k9b-scheduler"
                    }
                }
            }
        }

        def mock_kubectl(key: str) -> tuple[int, str, str]:
            if "deployment" in key:
                return (0, json.dumps(deployment_response), "")
            return (1, "", "error")

        def mock_run_kubectl(
            kubeconfig: str,
            namespace: str,
            args: list[str],
            timeout: int = 30,
        ) -> tuple[int, str, str]:
            cmd_str = " ".join(args)
            return mock_kubectl(cmd_str)

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._run_kubectl",
            mock_run_kubectl,
        )

        selector = _get_scheduler_pod_selector("/fake/kubeconfig", "test-ns", "k9b-scheduler")
        assert selector == "app.kubernetes.io/name=k9b-scheduler"

    def test_derives_multiple_labels_selector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Derives selector from Deployment.spec.selector.matchLabels with multiple labels."""
        deployment_response = {
            "spec": {
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "k9b-scheduler",
                        "app.kubernetes.io/instance": "k9b"
                    }
                }
            }
        }

        def mock_kubectl(key: str) -> tuple[int, str, str]:
            if "deployment" in key:
                return (0, json.dumps(deployment_response), "")
            return (1, "", "error")

        def mock_run_kubectl(
            kubeconfig: str,
            namespace: str,
            args: list[str],
            timeout: int = 30,
        ) -> tuple[int, str, str]:
            cmd_str = " ".join(args)
            return mock_kubectl(cmd_str)

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._run_kubectl",
            mock_run_kubectl,
        )

        selector = _get_scheduler_pod_selector("/fake/kubeconfig", "test-ns", "k9b-scheduler")
        # Should contain both labels in sorted order
        assert "app.kubernetes.io/name=k9b-scheduler" in selector
        assert "app.kubernetes.io/instance=k9b" in selector

    def test_falls_back_to_default_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Falls back to default selector on kubectl error."""
        def mock_run_kubectl(
            kubeconfig: str,
            namespace: str,
            args: list[str],
            timeout: int = 30,
        ) -> tuple[int, str, str]:
            return (1, "", "error")

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.main._run_kubectl",
            mock_run_kubectl,
        )

        selector = _get_scheduler_pod_selector("/fake/kubeconfig", "test-ns", "k9b-scheduler")
        assert selector == SCHEDULER_POD_SELECTOR



class TestSchedulerHealthResult:
    """Tests for SchedulerHealthResult type."""

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
