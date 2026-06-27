"""Shared fixtures for scheduler health gate tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.scheduler_health_gate.contracts import SCHEDULER_DEPLOYMENT_NAME

# =============================================================================
# kubectl mock fixture
# =============================================================================


@pytest.fixture
def mock_kubectl(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[int, str, str]]:
    """Mock kubectl command responses.
    
    Returns a dictionary that tests can populate with command responses.
    Format: {command_string: (returncode, stdout, stderr)}
    """
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
        "scripts.scheduler_health_gate.collect.run_kubectl",
        mock_run_kubectl,
    )
    return responses


# =============================================================================
# Deployment response fixtures
# =============================================================================


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
def missing_deployment_response() -> dict[str, Any]:
    """Scheduler deployment not found."""
    return {"found": False, "name": SCHEDULER_DEPLOYMENT_NAME, "error": "deployment not found"}


# =============================================================================
# Pod response fixtures
# =============================================================================


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
    """A scheduler pod in CrashLoopBackOff with lastState for evidence."""
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
                            "lastState": {
                                "terminated": {
                                    "exitCode": 1,
                                    "reason": "Error",
                                    "message": "Exception in thread main: ConfigError: missing required env K9B_KUBERNETES_AUTH_MODE",
                                    "startedAt": "2026-06-27T10:00:00Z",
                                    "finishedAt": "2026-06-27T10:00:01Z",
                                }
                            },
                        }
                    ],
                },
            }
        ],
    }


@pytest.fixture
def crash_loop_pods_with_logs_response() -> dict[str, Any]:
    """A scheduler pod in CrashLoopBackOff with logs for full evidence testing."""
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
                            "lastState": {
                                "terminated": {
                                    "exitCode": 1,
                                    "reason": "Error",
                                    "message": "ConfigError: missing required env K9B_KUBERNETES_AUTH_MODE",
                                    "startedAt": "2026-06-27T10:00:00Z",
                                    "finishedAt": "2026-06-27T10:00:01Z",
                                }
                            },
                        }
                    ],
                },
            }
        ],
    }


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


# =============================================================================
# Artifact directory fixture
# =============================================================================


@pytest.fixture
def temp_artifact_dir(tmp_path: Path) -> Path:
    """Temporary artifact directory."""
    return tmp_path / "artifacts"
