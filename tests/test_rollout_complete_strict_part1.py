#!/usr/bin/env python3
"""Strict rollout-complete regression tests (Part 1: Tests 1-4).

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
1. Partial availability is not success (1/3 available)
2. Updated but not fully available (3 updated, 2 available)
3. Stale observedGeneration (6 vs generation 7)
4. Old replicas remaining (replicas=4, updated=3)
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
    _check_rollout_success_from_json,
)

# =============================================================================
# Test-local JSON fixture builders
# =============================================================================


def make_deployments_json(deployments: list[dict[str, object]]) -> str:
    """Build deployments JSON from list of deployment dicts."""
    return json.dumps({"items": deployments})


# =============================================================================
# Test 1: Partial availability is not success
# =============================================================================


class TestPartialAvailabilityNotSuccess:
    """Test 1: Partial availability should NOT be success."""

    def test_partial_availability_1_of_3_not_success(self) -> None:
        """Desired replicas 3, available 1, updated 1, observedGeneration matches.

        This should NOT be rollout-complete because availableReplicas < desired_replicas.
        The first failure will be updatedReplicas (checked first in priority order).
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 3,
                "updatedReplicas": 1,
                "availableReplicas": 1,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Partial availability (1/3) must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        # First failure encountered is updatedReplicas check (priority order)
        # Both updated and available are insufficient, but updated is checked first
        assert "updatedReplicas=1 < desired=3" in states[0].blocked_reason

    def test_json_helper_partial_availability_still_weak(self) -> None:
        """The deprecated JSON helper still returns True for partial availability.

        This is the old weak behavior - we keep it for backward compat but
        the new _check_deployment_complete_from_json should be used.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 3,
                "availableReplicas": 1,
            },
        }])

        # Old weak behavior: at least one available = success
        result = _check_rollout_success_from_json('{"items": []}', deployments_json, '{"items": []}')
        assert result is True  # Old weak behavior preserved


# =============================================================================
# Test 2: Updated but not fully available is not success
# =============================================================================


class TestUpdatedNotFullyAvailable:
    """Test 2: Updated but not fully available should NOT be success."""

    def test_updated_not_fully_available_not_success(self) -> None:
        """Desired replicas 3, all updated (3), but only 2 available.

        This should NOT be rollout-complete because availableReplicas < desired_replicas.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 3,
                "updatedReplicas": 3,
                "availableReplicas": 2,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Updated but not fully available must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        assert "availableReplicas=2 < desired=3" in states[0].blocked_reason


# =============================================================================
# Test 3: Stale observedGeneration is not success
# =============================================================================


class TestStaleObservedGeneration:
    """Test 3: Stale observedGeneration should NOT be success."""

    def test_stale_observed_generation_not_success(self) -> None:
        """Generation 7, but observedGeneration only 6.

        This should NOT be rollout-complete because controller hasn't processed update.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 7},
            "spec": {"replicas": 1},
            "status": {
                "replicas": 1,
                "updatedReplicas": 1,
                "availableReplicas": 1,
                "observedGeneration": 6,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Stale observedGeneration must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        assert "observedGeneration=6 < generation=7" in states[0].blocked_reason

    def test_missing_observed_generation_with_generation_present_not_success(self) -> None:
        """Generation present but observedGeneration missing.

        This should NOT be rollout-complete because controller hasn't processed.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 3},
            "spec": {"replicas": 1},
            "status": {
                "replicas": 1,
                "updatedReplicas": 1,
                "availableReplicas": 1,
                # observedGeneration intentionally missing
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Missing observedGeneration with generation present must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        assert "observedGeneration missing" in states[0].blocked_reason


# =============================================================================
# Test 4: Old replicas remaining is not success
# =============================================================================


class TestOldReplicasRemaining:
    """Test 4: Old replicas remaining should NOT be success."""

    def test_old_replicas_remaining_not_success(self) -> None:
        """Total replicas 4, but only 3 updated - 1 old replica remains.

        This should NOT be rollout-complete because old replicas remain.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 2},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 4,  # 3 new + 1 old
                "updatedReplicas": 3,
                "availableReplicas": 3,
                "observedGeneration": 2,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Old replicas remaining must not be success"
        assert len(states) == 1
        assert states[0].complete is False
        assert states[0].old_replicas == 1
        assert "old replicas remain" in states[0].blocked_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
