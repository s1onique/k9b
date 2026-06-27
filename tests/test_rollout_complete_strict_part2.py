#!/usr/bin/env python3
"""Strict rollout-complete regression tests (Part 2: Tests 5-8).

Tests that verify the strict deployment rollout-complete semantics:
- A deployment is rollout-complete only when ALL criteria are met:
  - observedGeneration >= metadata.generation
  - updatedReplicas >= desired_replicas
  - availableReplicas >= desired_replicas
  - No old replicas remain
  - unavailableReplicas == 0 (when present)
- "At least one available replica" is NOT success
- Missing status fields are treated conservatively

Required regression tests per contract:
5. Complete rollout is success
6. Default desired replicas (no spec.replicas)
7. Multi-Deployment success requires all complete
8. Crash-loop takes precedence over partial availability
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

from scripts.k9b_cnpg_live_lab_rollout import (  # noqa: E402
    _check_deployment_complete_from_json,
    classify_rollout_state,
)

# =============================================================================
# Test-local JSON fixture builders
# =============================================================================


def make_deployments_json(deployments: list[dict[str, object]]) -> str:
    """Build deployments JSON from list of deployment dicts."""
    return json.dumps({"items": deployments})


def make_pods_json(pods: list[dict[str, object]]) -> str:
    """Build pods JSON from list of pod dicts."""
    return json.dumps({"items": pods})


# =============================================================================
# Test 5: Complete rollout is success
# =============================================================================


class TestCompleteRolloutIsSuccess:
    """Test 5: Complete rollout should be success."""

    def test_complete_rollout_is_success(self) -> None:
        """All criteria met: generation matches, all replicas updated and available.

        This SHOULD be rollout-complete.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 3,
                "updatedReplicas": 3,
                "availableReplicas": 3,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is True, "Complete rollout must be success"
        assert len(states) == 1
        assert states[0].complete is True
        assert states[0].blocked_reason == ""

    def test_complete_rollout_with_unavailable_zero_not_failure(self) -> None:
        """Complete rollout with unavailableReplicas explicitly 0.

        This SHOULD be rollout-complete.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 2},
            "status": {
                "replicas": 2,
                "updatedReplicas": 2,
                "availableReplicas": 2,
                "observedGeneration": 1,
                "unavailableReplicas": 0,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is True, "Complete rollout with unavailableReplicas=0 must be success"


# =============================================================================
# Test 6: Default desired replicas
# =============================================================================


class TestDefaultDesiredReplicas:
    """Test 6: Default desired replicas when spec.replicas is absent."""

    def test_default_desired_replicas_is_one(self) -> None:
        """No spec.replicas means desired=1 (K8s default).

        With 1 available and 1 updated, this SHOULD be rollout-complete.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            # No spec.replicas - defaults to 1
            "status": {
                "replicas": 1,
                "updatedReplicas": 1,
                "availableReplicas": 1,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is True, "Default desired replicas (1) with 1 available must be success"
        assert len(states) == 1
        assert states[0].desired_replicas == 1, "Desired replicas should default to 1"
        assert states[0].complete is True

    def test_default_desired_replicas_insufficient_available(self) -> None:
        """No spec.replicas means desired=1, but no replicas available.

        This should NOT be rollout-complete.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            # No spec.replicas - defaults to 1
            "status": {
                "replicas": 0,
                "updatedReplicas": 0,
                "availableReplicas": 0,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "No available replicas must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        assert states[0].desired_replicas == 1, "Desired replicas should default to 1"


# =============================================================================
# Test 7: Multi-Deployment success requires all complete
# =============================================================================


class TestMultiDeploymentSuccessRequiresAllComplete:
    """Test 7: Multi-deployment success requires ALL deployments complete."""

    def test_one_complete_one_incomplete_not_success(self) -> None:
        """k9b-backend complete, k9b-scheduler partially available.

        Overall rollout should NOT be success.
        """
        deployments_json = make_deployments_json([
            {
                "metadata": {"name": "k9b-backend", "generation": 1},
                "spec": {"replicas": 2},
                "status": {
                    "replicas": 2,
                    "updatedReplicas": 2,
                    "availableReplicas": 2,
                    "observedGeneration": 1,
                },
            },
            {
                "metadata": {"name": "k9b-scheduler", "generation": 1},
                "spec": {"replicas": 2},
                "status": {
                    "replicas": 2,
                    "updatedReplicas": 1,  # Only 1 updated
                    "availableReplicas": 1,
                    "observedGeneration": 1,
                },
            },
        ])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Multi-deployment with one incomplete must not be success"
        assert len(states) == 2

        # Find each deployment's state
        backend = next(s for s in states if s.name == "k9b-backend")
        scheduler = next(s for s in states if s.name == "k9b-scheduler")

        assert backend.complete is True, "k9b-backend should be complete"
        assert scheduler.complete is False, "k9b-scheduler should be incomplete"
        assert "updatedReplicas=1 < desired=2" in scheduler.blocked_reason

    def test_both_complete_is_success(self) -> None:
        """Both k9b-backend and k9b-scheduler are complete.

        Overall rollout SHOULD be success.
        """
        deployments_json = make_deployments_json([
            {
                "metadata": {"name": "k9b-backend", "generation": 1},
                "spec": {"replicas": 2},
                "status": {
                    "replicas": 2,
                    "updatedReplicas": 2,
                    "availableReplicas": 2,
                    "observedGeneration": 1,
                },
            },
            {
                "metadata": {"name": "k9b-scheduler", "generation": 1},
                "spec": {"replicas": 2},
                "status": {
                    "replicas": 2,
                    "updatedReplicas": 2,
                    "availableReplicas": 2,
                    "observedGeneration": 1,
                },
            },
        ])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is True, "Multi-deployment with all complete must be success"
        assert all(s.complete for s in states)


# =============================================================================
# Test 8: Failure precedence - crash-loop beats partial availability
# =============================================================================


class TestCrashLoopTakesPrecedence:
    """Test 8: Crash-loop takes precedence over partial availability."""

    def test_crash_loop_detected_despite_availability(self) -> None:
        """Deployment has some available replicas but pod is in CrashLoopBackOff.

        Crash-loop failure should be returned, not success.
        This ensures the crash-loop precedence from the contract is preserved.
        """
        pods_json = make_pods_json([{
            "metadata": {"name": "k9b-backend-abc123"},
            "status": {
                "phase": "Running",
                "containerStatuses": [{
                    "name": "backend",
                    "restartCount": 5,
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff",
                            "message": "back-off 5m0s restarting",
                        }
                    },
                }],
            },
        }])
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 3,
                "updatedReplicas": 1,
                "availableReplicas": 1,  # Only 1 available
                "observedGeneration": 1,
            },
        }])

        result = classify_rollout_state(pods_json, deployments_json, '{"items": []}', "")

        assert result.fatal is True, "Crash-loop must be fatal"
        assert result.failure_class == "crash_loop", "Failure class must be crash_loop"
        assert "crash_loop" in result.diagnostics, "Crash loop should be in diagnostics"
        # The deployment is NOT rollout-complete, but crash-loop takes precedence
        # in the classifier's priority order

    def test_crash_loop_in_classifier_not_overridden_by_weak_success(self) -> None:
        """Crash-loop is detected BEFORE the weak success check.

        This verifies the priority order: pod/container failures > deployment status.
        """
        pods_json = make_pods_json([{
            "metadata": {"name": "crashing-pod"},
            "status": {
                "phase": "CrashLoopBackOff",
                "containerStatuses": [{
                    "name": "app",
                    "restartCount": 3,
                    "state": {
                        "waiting": {"reason": "CrashLoopBackOff", "message": "crash"},
                    },
                }],
            },
        }])
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 1,
                "availableReplicas": 1,  # Looks healthy in weak check
            },
        }])

        result = classify_rollout_state(pods_json, deployments_json, '{"items": []}', "")

        # Crash-loop is detected first due to priority order
        assert result.fatal is True
        assert result.failure_class == "crash_loop"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
