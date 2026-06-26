#!/usr/bin/env python3
"""Regression tests for rollout classifier crash-loop precedence.

These tests verify the fix for the live-lab rollout failure where:
1. The monitor was detecting exit_code=1 as readiness_probe_failed instead of pod_crash_loop
2. The classifier precedence was wrong - crash evidence should outrank readiness probe

The contract requires:
- image_pull_error
- pod_crash_loop / container_exit_nonzero  <-- these must be detected FIRST
- oom_killed
- readiness_probe_failed  <-- only true probe failures, not container crashes

Test cases:
1. Scheduler container with exit_code=1 must classify pod_crash_loop (not readiness_probe_failed)
2. Both readiness=False AND container exit_code=1 must classify pod_crash_loop
3. CrashLoopBackOff + readiness=False must classify crash_loop
4. Transient VolumeBinding conflict + crash evidence must classify crash_loop
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
    FAILURE_READINESS_PROBE_FAILED,
    classify_rollout_state,
)


class TestSchedulerCrashLoopRegression:
    """Regression test: scheduler container exit_code=1 must classify pod_crash_loop.

    This is the exact scenario from the failing lab:
    - k9b-scheduler-64c869c58c-wrwqf pod exists
    - scheduler container has exit_code=1, reason=Error
    - This must classify as pod_crash_loop, NOT readiness_probe_failed
    """

    def test_scheduler_container_exit_code_1_classifies_crash_loop(self) -> None:
        """Scheduler container with exit_code=1 must classify as crash_loop, not readiness."""
        # This is the exact pod state from the failing lab
        pods_json = json.dumps({
            "items": [{
                "metadata": {
                    "name": "k9b-scheduler-64c869c58c-wrwqf",
                    "namespace": "k9b-cnpg-lab",
                    "ownerReferences": [{
                        "kind": "ReplicaSet",
                        "name": "k9b-scheduler-64c869c58c"
                    }]
                },
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "state": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error",
                                "startedAt": "2026-06-26T10:00:00Z",
                                "finishedAt": "2026-06-26T10:00:05Z"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error",
                                "startedAt": "2026-06-26T09:59:00Z",
                                "finishedAt": "2026-06-26T09:59:05Z"
                            }
                        },
                        "restartCount": 2
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        # The bug was: this classified as readiness_probe_failed
        # The fix: this must classify as crash_loop
        assert result.fatal is True, "Crash with exit_code=1 must be fatal"
        assert result.failure_class == FAILURE_CRASH_LOOP, (
            f"Scheduler container exit_code=1 must classify as {FAILURE_CRASH_LOOP}, "
            f"not {result.failure_class}"
        )
        assert "k9b-scheduler-64c869c58c-wrwqf" in result.affected_pods

    def test_k9b_backend_and_scheduler_both_present_crash_loop(self) -> None:
        """Both k9b-backend and k9b-scheduler present, scheduler crashing."""
        pods_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "k9b-backend-8665955ddd-wpkbj"},
                    "status": {
                        "phase": "Running",
                        "conditions": [{"type": "Ready", "status": "True"}],
                        "containerStatuses": [{
                            "name": "backend",
                            "restartCount": 0
                        }]
                    }
                },
                {
                    "metadata": {"name": "k9b-scheduler-64c869c58c-wrwqf"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{
                            "name": "scheduler",
                            "restartCount": 2,
                            "state": {
                                "waiting": {
                                    "reason": "CrashLoopBackOff",
                                    "message": "back-off 1m0s restarting"
                                }
                            },
                            "lastState": {
                                "terminated": {
                                    "exitCode": 1,
                                    "reason": "Error"
                                }
                            }
                        }]
                    }
                }
            ]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP
        assert "k9b-scheduler-64c869c58c-wrwqf" in result.affected_pods


class TestReadinessAndCrashTogether:
    """Tests: readiness=False + container crash must classify crash_loop."""

    def test_both_ready_false_and_exit_code_1_classifies_crash_loop(self) -> None:
        """Pod with Ready=False AND container exit_code=1 must classify as crash_loop."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "test-pod-abc123"},
                "status": {
                    "phase": "Running",
                    "conditions": [
                        {"type": "Ready", "status": "False", "reason": "ContainersNotReady", "message": ""}
                    ],
                    "containerStatuses": [{
                        "name": "main",
                        "restartCount": 1,
                        "state": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        # The bug was: readiness_probe_failed took precedence over crash evidence
        # The fix: exit_code=1 is crash evidence, must be detected FIRST
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP, (
            f"exit_code=1 must classify as {FAILURE_CRASH_LOOP}, "
            f"not {result.failure_class} (even with Ready=False)"
        )

    def test_crash_loop_and_containers_not_ready_classifies_crash_loop(self) -> None:
        """CrashLoopBackOff + ContainersNotReady condition must classify crash_loop."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "crashing-pod"},
                "status": {
                    "phase": "Running",
                    "conditions": [
                        {"type": "Ready", "status": "False", "reason": "ContainersNotReady"}
                    ],
                    "containerStatuses": [{
                        "name": "app",
                        "restartCount": 3,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "back-off restarting"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP
        assert result.affected_pods == ["crashing-pod"]


class TestTransientVolumeBindingAndCrash:
    """Tests: transient VolumeBinding conflict must not outrank crash evidence."""

    def test_transient_volume_binding_with_crash_classifies_crash_loop(self) -> None:
        """VolumeBinding conflict + crash evidence must classify crash_loop."""
        # Simulate the events from the failing lab with "object has been modified"
        # This format should match the _detect_transient_volume_binding_conflict pattern
        events_json = json.dumps({
            "items": [
                {
                    "type": "Warning",
                    "reason": "FailedBinding",
                    "involvedObject": {
                        "kind": "PersistentVolumeClaim",
                        "name": "k9b-runs"
                    },
                    "message": "Operation cannot be fulfilled on persistentvolumeclaims \"k9b-runs\": the object has been modified; please apply your changes to the latest version"
                }
            ]
        })

        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "k9b-scheduler-xyz789"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "scheduler",
                        "restartCount": 2,
                        "state": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 1,
                                "reason": "Error"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "", events_json=events_json)

        # Transient VolumeBinding should be recorded but NOT the primary failure
        # Container crash with exit_code=1 must take precedence
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP, (
            f"Container crash must outrank transient VolumeBinding conflict. "
            f"Got {result.failure_class}"
        )


class TestOnlyCrashEvidenceMatters:
    """Tests: only crash evidence exists, correct classification."""

    def test_error_waiting_reason_classifies_crash_loop(self) -> None:
        """Container with Error waiting reason must classify as crash_loop."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "immediate-crash-pod"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "app",
                        "restartCount": 1,
                        "state": {
                            "waiting": {
                                "reason": "Error",
                                "message": "container exited with code 1"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP

    def test_previous_termination_with_restart_count_classifies_crash_loop(self) -> None:
        """Container with lastState.terminated exit_code!=0 must classify as crash_loop."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "restarted-pod"},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [{
                        "name": "app",
                        "restartCount": 1,
                        "state": {
                            "running": {"startedAt": "2026-06-26T10:00:00Z"}
                        },
                        "lastState": {
                            "terminated": {
                                "exitCode": 127,
                                "reason": "Error"
                            }
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        # Previous termination with non-zero exit is crash evidence
        assert result.fatal is True
        assert result.failure_class == FAILURE_CRASH_LOOP


class TestReadinessProbeOnly:
    """Tests: true readiness probe failures (no crash evidence)."""

    def test_only_containers_not_ready_without_crash(self) -> None:
        """Pod with ContainersNotReady but no crash evidence should classify readiness_probe_failed."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "not-ready-pod"},
                "status": {
                    "phase": "Running",
                    "conditions": [
                        {"type": "Ready", "status": "False", "reason": "ContainersNotReady"}
                    ],
                    "containerStatuses": [{
                        "name": "app",
                        "restartCount": 0,
                        "state": {
                            "running": {"startedAt": "2026-06-26T10:00:00Z"}
                        }
                    }]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        # No crash evidence - should be readiness_probe_failed
        assert result.fatal is True
        assert result.failure_class == FAILURE_READINESS_PROBE_FAILED

    def test_image_pull_takes_priority_over_crash(self) -> None:
        """ImagePullBackOff must take priority over CrashLoopBackOff."""
        pods_json = json.dumps({
            "items": [{
                "metadata": {"name": "both-issues-pod"},
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [
                        {
                            "name": "main",
                            "state": {"waiting": {"reason": "ImagePullBackOff"}}
                        },
                        {
                            "name": "sidecar",
                            "restartCount": 1,
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}}
                        }
                    ]
                }
            }]
        })

        result = classify_rollout_state(pods_json, "{}", "{}", "")

        assert result.failure_class == FAILURE_IMAGE_PULL_BACKOFF


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
