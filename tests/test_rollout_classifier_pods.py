#!/usr/bin/env python3
"""Tests for rollout classifier - pod-based failure classes.

Tests: image_pull_backoff, crash_loop, readiness_probe_failed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib

import scripts.k9b_cnpg_live_lab_bootstrap as bootstrap  # noqa: E402

importlib.reload(bootstrap)

from scripts.k9b_cnpg_live_lab_bootstrap import (  # noqa: E402
    FAILURE_CRASH_LOOP,
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_READINESS_PROBE_FAILED,
    classify_rollout_state,
)


class TestImagePullBackoff:
    """Tests for image_pull_backoff failure class."""

    def test_detects_image_pull_backoff(self) -> None:
        """Should detect ImagePullBackOff in container status."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "test-pod-abc123"},
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [{
                        "name": "main",
                        "state": {
                            "waiting": {
                                "reason": "ImagePullBackOff",
                                "message": "Back-off pulling image \"invalid:latest\""
                            }
                        }
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF
        assert "test-pod-abc123" in result.affected_pods

    def test_detects_err_image_pull(self) -> None:
        """Should detect ErrImagePull in container status."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "test-pod-xyz789"},
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [{
                        "name": "app",
                        "state": {"waiting": {"reason": "ErrImagePull", "message": "manifest unknown"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF

    def test_detects_in_init_container(self) -> None:
        """Should detect image pull backoff in init container."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "test-pod-init"},
                "status": {
                    "phase": "Pending",
                    "initContainerStatuses": [{
                        "name": "init",
                        "state": {"waiting": {"reason": "ImagePullBackOff", "message": "unauthorized"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF

    def test_no_false_positive_for_running_pod(self) -> None:
        """Should NOT detect image pull backoff for running pod."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "healthy-pod"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "main",
                        "state": {"running": {"startedAt": "2024-01-01T00:00:00Z"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is False


class TestCrashLoop:
    """Tests for crash_loop failure class."""

    def test_detects_crash_loop_backoff(self) -> None:
        """Should detect CrashLoopBackOff in container status."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "crashing-pod"},
                "status": {
                    "phase": "CrashLoopBackOff",
                    "containerStatuses": [{
                        "name": "app",
                        "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "back-off"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP
        assert "crashing-pod" in result.affected_pods
        assert result.pod_phase == "CrashLoopBackOff"

    def test_detects_in_init_container(self) -> None:
        """Should detect CrashLoopBackOff in init container."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "init-crashing-pod"},
                "status": {
                    "phase": "Pending",
                    "initContainerStatuses": [{
                        "name": "init-script",
                        "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "exit 1"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP

    def test_no_false_positive_for_terminating_pod(self) -> None:
        """Should NOT detect crash loop for terminating pod."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "terminating-pod"},
                "status": {
                    "phase": "Terminating",
                    "containerStatuses": [{
                        "name": "main",
                        "state": {"terminated": {"exitCode": 0, "reason": "Completed"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is False


class TestReadinessProbeFailed:
    """Tests for readiness_probe_failed failure class."""

    def test_detects_containers_not_ready(self) -> None:
        """Should detect ContainersNotReady waiting reason."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "unready-pod"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "app",
                        "state": {"waiting": {"reason": "ContainersNotReady", "message": "not ready"}}
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_READINESS_PROBE_FAILED
        assert "unready-pod" in result.affected_pods

    def test_detects_ready_condition_false(self) -> None:
        """Should detect Ready=False in Pod status conditions (canonical K8s check)."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "condition-unready-pod"},
                "status": {
                    "phase": "Running",
                    "conditions": [{
                        "type": "Ready",
                        "status": "False",
                        "reason": "ContainersNotReady",
                        "message": "containers not ready"
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_READINESS_PROBE_FAILED

    def test_detects_containers_ready_condition_false(self) -> None:
        """Should detect ContainersReady=False in Pod status conditions."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "containers-not-ready-pod"},
                "status": {
                    "phase": "Running",
                    "conditions": [{
                        "type": "ContainersReady",
                        "status": "False",
                        "reason": "ContainersNotReady",
                        "message": "containers not ready ( readiness probe failed )"
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is True
        assert result.failure_class == FAILURE_READINESS_PROBE_FAILED

    def test_no_false_positive_for_ready_condition_true(self) -> None:
        """Should NOT detect readiness failure when Ready=True."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "ready-pod"},
                "status": {
                    "phase": "Running",
                    "conditions": [{
                        "type": "Ready",
                        "status": "True",
                        "reason": "KubeletReady",
                        "message": "kubelet is ready"
                    }]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.fatal is False


class TestPriorityOrder:
    """Tests that failure classes are checked in correct priority order."""

    def test_image_pull_takes_priority_over_crash_loop(self) -> None:
        """ImagePullBackOff should be detected before CrashLoopBackOff."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "both-issues-pod"},
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [
                        {"name": "main", "state": {"waiting": {"reason": "ImagePullBackOff", "message": "pull fail"}}},
                        {"name": "sidecar", "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "crash"}}}
                    ]
                }
            }]
        })
        result = classify_rollout_state(pods_json, "{}", "{}", "")
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
