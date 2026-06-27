#!/usr/bin/env python3
"""Regression tests for crash-loop precedence over transient PVC VolumeBinding conflicts.

These tests verify that the classifier correctly prioritizes crash-loop evidence
over transient VolumeBinding conflicts, as specified in the monitor contract fix.

Tests the fix for the bug where:
- The monitor repeatedly reported "Deployment k9b not found"
- But actual rollout had k9b-backend, k9b-scheduler pods
- Scheduler was in CrashLoopBackOff with restart_count=3
- Transient PVC VolumeBinding conflicts were logged

The fix ensures:
1. Crash-loop takes precedence over transient PVC VolumeBinding conflict
2. Expected deployments are derived from rendered manifests (not hard-coded "k9b")
3. Failure artifacts include crash-loop specific evidence
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_bootstrap import (
    FAILURE_CRASH_LOOP,
    FAILURE_IMAGE_PULL_BACKOFF,
    FAILURE_PVC_PENDING,
    classify_rollout_state,
)


class TestCrashLoopPrecedenceOverTransientVolumeBinding:
    """Tests that crash-loop takes precedence over transient PVC VolumeBinding conflicts.

    This is the core regression test for the monitor contract fix where:
    - Transient PVC VolumeBinding conflicts should be diagnostic context only
    - CrashLoopBackOff pods should dominate the failure classification
    """

    def test_crash_loop_takes_precedence_over_transient_volume_binding(self) -> None:
        """Crash-loop should be classified as fatal even when transient VolumeBinding conflict exists.

        The transient VolumeBinding conflict:
        "Operation cannot be fulfilled on persistentvolumeclaims 'k9b-runs':
         the object has been modified; please apply your changes to the latest version"

        Should NOT override the crash-loop detection when a scheduler pod is in CrashLoopBackOff.
        """
        # Scheduler pod in CrashLoopBackOff - this is the real blocker
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-backend-6b9bdfb6d-wgcjf"},
                    "status": {
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}]
                    }
                },
                {
                    "metadata": {"name": "k9b-scheduler-f7c6ddc79-85wsg"},
                    "status": {
                        "phase": "CrashLoopBackOff",
                        "conditions": [{"type": "Ready", "status": "False"}],
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off 5m0s restarting"
                                    }
                                },
                                "restartCount": 3,
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

        # Transient VolumeBinding conflict in events - MUST have "prebind plugin volumebinding"
        # to trigger the transient detection
        events_json = json.dumps({
            "items": [
                {
                    "reason": "FailedScheduling",
                    "message": "PreBind plugin VolumeBinding: operation cannot be fulfilled on "
                              "persistentvolumeclaims \"k9b-runs\": the object has been modified; "
                              "please apply your changes to the latest version and try again",
                    "involvedObject": {
                        "kind": "Pod",
                        "name": "k9b-scheduler-f7c6ddc79-85wsg"
                    },
                    "lastTimestamp": "2026-06-27T00:29:00Z"
                }
            ]
        })

        deployments_json = json.dumps({"items": []})
        pvc_json = json.dumps({"items": []})

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json,
            "",  # events_text (ignored)
            events_json  # events_json (used for machine-readable check)
        )

        # CRITICAL: crash-loop MUST take precedence
        assert result.fatal is True, "Crash-loop should be fatal"
        assert result.failure_class == FAILURE_CRASH_LOOP, \
            f"Expected {FAILURE_CRASH_LOOP}, got {result.failure_class}"
        assert result.crash_pod_name == "k9b-scheduler-f7c6ddc79-85wsg", \
            "Should identify the crashing scheduler pod"
        assert result.crash_container_name == "scheduler", \
            "Should identify the crashing container"
        assert result.crash_restart_count == 3, \
            "Should record restart count"

    def test_transient_volume_binding_is_diagnostic_only(self) -> None:
        """Transient VolumeBinding conflict should be recorded as diagnostic, not failure class.

        When a crash-loop exists alongside transient VolumeBinding conflict,
        the VolumeBinding should appear in diagnostics but NOT be the failure class.
        """
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-scheduler-abc123"},
                    "status": {
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                "restartCount": 2
                            }
                        ]
                    }
                }
            ]
        })

        # Use the exact message format that triggers transient VolumeBinding detection:
        # "prebind plugin volumebinding" + "object has been modified" + "please apply your changes"
        events_json = json.dumps({
            "items": [
                {
                    "reason": "FailedScheduling",
                    "message": "PreBind plugin VolumeBinding: operation cannot be fulfilled on "
                              "persistentvolumeclaims \"k9b-runs\": the object has been modified; "
                              "please apply your changes to the latest version and try again",
                    "involvedObject": {"kind": "Pod", "name": "k9b-scheduler-abc123"}
                }
            ]
        })

        result = classify_rollout_state(
            pods_json, "{}", "{}", "", events_json
        )

        # Crash-loop is the failure class
        assert result.failure_class == FAILURE_CRASH_LOOP

        # Transient VolumeBinding is in diagnostics (recorded but not a failure)
        assert result.diagnostics.get("transient_volume_binding_conflict") is True, \
            "Transient VolumeBinding should be in diagnostics"
        assert "transient_volume_binding_message" in result.diagnostics, \
            "Should record the VolumeBinding message"

    def test_pvc_pending_detected(self) -> None:
        """Actual PVC pending should be detected as the failure class."""
        # No pods, just a pending PVC
        pods_json = json.dumps({"items": []})
        deployments_json = json.dumps({"items": []})

        # PVC in Pending state
        pvc_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-runs"},
                    "status": {"phase": "Pending"}
                }
            ]
        })

        result = classify_rollout_state(
            pods_json, deployments_json, pvc_json, "", "{}"
        )

        assert result.failure_class == FAILURE_PVC_PENDING, \
            f"PVC pending should be the failure class, got {result.failure_class}"


class TestCrashLoopArtifactCollection:
    """Tests that crash-loop failure artifacts include necessary evidence.

    Artifact requirements from the ACT:
    - rollout snapshot JSON
    - pod status JSON
    - owning ReplicaSet/Deployment metadata
    - current container state
    - lastState.terminated reason, exit_code, started_at, finished_at
    - restart_count
    - current logs
    - previous logs when available
    """

    def test_crash_loop_diagnostics_include_container_state(self) -> None:
        """Crash-loop diagnostics should include container state evidence."""
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {
                        "name": "k9b-scheduler-f7c6ddc79-85wsg",
                        "ownerReferences": [
                            {"kind": "ReplicaSet", "name": "k9b-scheduler-f7c6ddc79"}
                        ]
                    },
                    "status": {
                        "containerStatuses": [
                            {
                                "name": "scheduler",
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff",
                                        "message": "back-off 5m0s restarting"
                                    }
                                },
                                "restartCount": 3,
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

        result = classify_rollout_state(pods_json, "{}", "{}", "", "{}")

        assert result.crash_pod_name == "k9b-scheduler-f7c6ddc79-85wsg"
        assert result.crash_container_name == "scheduler"
        assert result.crash_restart_count == 3

        crash_info = result.diagnostics.get("crash_loop", [])
        assert len(crash_info) > 0
        assert crash_info[0].get("restart_count") == 3


class TestImagePullBeforeCrashLoop:
    """Tests that image pull backoff takes priority over crash-loop."""

    def test_image_pull_before_crash_loop(self) -> None:
        """Image pull backoff should be classified before crash-loop.

        Both issues may coexist, but image pull is more fundamental.
        """
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-backend-abc"},
                    "status": {
                        "containerStatuses": [
                            {
                                "name": "backend",
                                "state": {
                                    "waiting": {
                                        "reason": "ImagePullBackOff",
                                        "message": "back-off pulling image"
                                    }
                                },
                                "restartCount": 0
                            },
                            {
                                "name": "sidecar",
                                "state": {
                                    "waiting": {
                                        "reason": "CrashLoopBackOff"
                                    }
                                },
                                "restartCount": 5
                            }
                        ]
                    }
                }
            ]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "", "{}")

        # ImagePullBackOff should win
        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
