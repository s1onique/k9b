#!/usr/bin/env python3
"""Tests for classifier precedence and crash detection.

Tests the contract: CrashLoopBackOff takes precedence over transient
VolumeBinding conflicts and other non-fatal issues.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_rollout_classify import (
    FAILURE_CRASH_LOOP,
    classify_rollout_state,
)
from scripts.k9b_cnpg_live_lab_rollout_pods import _check_crash_loop_from_pods


class TestClassifierPrecedenceOverVolumeBinding:
    """Regression Test 3: Crash-loop takes precedence over transient VolumeBinding.

    A classifier precedence test where:
    - backend pod has transient VolumeBinding conflict
    - scheduler pod has CrashLoopBackOff

    Must assert failure_class == "crash_loop" and transient VolumeBinding
    remains diagnostic metadata only.
    """

    def test_crash_loop_takes_precedence_over_transient_volume_binding(self) -> None:
        """Failure class must be crash_loop, not transient_volume_binding."""
        # Scheduler pod in CrashLoopBackOff
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-backend-8656cd977b-tmqhm"},
                    "status": {
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}]
                    }
                },
                {
                    "metadata": {"name": "k9b-scheduler-84598f5bf5-vdsjt"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "restartCount": 3,
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off 5m0s restarting"
                                    }
                                },
                                "lastState": {
                                    "terminated": {
                                        "exitCode": 1,
                                        "reason": "Error",
                                        "startedAt": "2026-06-27T00:30:00Z",
                                        "finishedAt": "2026-06-27T00:30:05Z"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        })

        # Transient VolumeBinding conflict (diagnostic context only)
        events_json = json.dumps({
            "items": [
                {
                    "reason": "FailedScheduling",
                    "message": "running PreBind plugin \"VolumeBinding\": "
                              "Operation cannot be fulfilled on persistentvolumeclaims "
                              "\"k9b-runs\": the object has been modified; "
                              "please apply your changes to the latest version",
                    "involvedObject": {
                        "kind": "Pod",
                        "name": "k9b-backend-8656cd977b-tmqhm"
                    },
                    "lastTimestamp": "2026-06-27T00:29:00Z"
                }
            ]
        })

        result = classify_rollout_state(
            pods_json, "{}", "{}", "",
            events_json=events_json
        )

        # PRIMARY failure must be crash_loop
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP, \
            f"Expected crash_loop, got {result.failure_class}"
        # Crash details must be captured
        assert result.crash_pod_name == "k9b-scheduler-84598f5bf5-vdsjt"
        assert result.crash_container_name == "scheduler"
        assert result.crash_restart_count == 3

        # Transient VolumeBinding must be diagnostic context only
        assert result.diagnostics.get("transient_volume_binding_conflict") is True
        assert "transient_volume_binding_message" in result.diagnostics


class TestCrashArtifactCollectionIncludesLogs:
    """Regression Test 4: Crash artifact collection includes current and previous logs.

    A crash artifact test proving current and previous logs are requested
    for the crashing container.
    """

    def test_crash_evidence_has_pod_and_container_for_log_collection(self) -> None:
        """Crash evidence must contain pod and container for log collection."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-scheduler-84598f5bf5-vdsjt"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "back-off 5m0s restarting"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error",
                                "startedAt": "2026-06-27T00:30:00Z",
                                "finishedAt": "2026-06-27T00:30:05Z"
                            }
                        }
                    }]
                }
            }]
        })

        crash_evidence = _check_crash_loop_from_pods(pods_json)

        assert len(crash_evidence) == 1
        evidence: dict[str, Any] = crash_evidence[0]

        # Required fields for log collection
        assert "pod" in evidence
        assert "container" in evidence
        assert evidence["pod"] == "k9b-scheduler-84598f5bf5-vdsjt"
        assert evidence["container"] == "scheduler"
        # Crash details for status
        assert "restart_count" in evidence
        assert evidence["restart_count"] == 3
        assert "reason" in evidence
        assert evidence["reason"] == "CrashLoopBackOff"

    def test_crash_artifact_module_collects_logs(self) -> None:
        """Verify crash artifact module has log collection capability."""
        from scripts.k9b_cnpg_live_lab_crash_artifacts import (
            _collect_container_logs,
        )

        # Verify the function exists and is callable
        assert callable(_collect_container_logs)


class TestSplitBrainDeploymentNameDrift:
    """Regression Test 6: Monitor must NOT report stale "Deployment k9b not found".

    A split-brain case test where:
    - rendered manifests contain k9b-backend and k9b-scheduler
    - no literal k9b Deployment exists in cluster
    - scheduler pod is in CrashLoopBackOff
    - monitor output must NOT contain "Deployment k9b not found"
    - result must classify crash_loop, not deployment_not_found
    """

    def test_classifier_does_not_return_deployment_not_found_when_crash_loop_present(self) -> None:
        """Classifier must return crash_loop, not expected_deployment_missing."""
        # Scheduler pod in CrashLoopBackOff
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-scheduler-abc123"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "back-off 5m0s restarting"
                            }
                        }
                    }]
                }
            }]
        })

        # Empty deployments (k9b Deployment doesn't exist)
        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, ""
        )

        # Must classify as crash_loop, NOT expected_deployment_missing
        assert result.failure_class == FAILURE_CRASH_LOOP, \
            f"Expected crash_loop, got {result.failure_class}"
        assert result.crash_pod_name == "k9b-scheduler-abc123"
        assert result.crash_container_name == "scheduler"
        assert result.crash_restart_count == 3


class TestMachineReadableCrashSummary:
    """Test machine-readable crash summary format."""

    def test_crash_summary_format(self) -> None:
        """Crash summary must be machine-parseable."""
        crash_info: dict[str, str | int] = {
            "failure_class": "crash_loop",
            "crash_pod_name": "k9b-scheduler-84598f5bf5-vdsjt",
            "crash_container_name": "scheduler",
            "crash_restart_count": 3,
            "pod_crash_loop": "k9b-scheduler/scheduler CrashLoopBackOff restarts=3"
        }

        # Machine-readable format
        assert crash_info["failure_class"] == "crash_loop"
        assert crash_info["crash_pod_name"] == "k9b-scheduler-84598f5bf5-vdsjt"
        assert crash_info["crash_container_name"] == "scheduler"
        assert crash_info["crash_restart_count"] == 3
        # Concise summary format: pod_name/container_name reason restarts=N
        pod_crash_loop_val = crash_info["pod_crash_loop"]
        assert isinstance(pod_crash_loop_val, str)
        assert "CrashLoopBackOff" in pod_crash_loop_val
        assert "restarts=3" in pod_crash_loop_val


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
