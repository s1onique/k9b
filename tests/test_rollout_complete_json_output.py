#!/usr/bin/env python3
"""Strict rollout-complete JSON output contract tests.

Tests that verify the DeploymentRolloutState JSON output includes all required fields
for human-readable and CI-consumable output.

Required JSON fields:
- desired_replicas
- updated_replicas
- available_replicas
- observedGeneration
- generation
- old replica count or old-replica derivation
- clear reason when deployment is incomplete
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
)


def make_deployments_json(deployments: list[dict[str, object]]) -> str:
    """Build deployments JSON from list of deployment dicts."""
    return json.dumps({"items": deployments})


class TestRolloutCompleteJsonOutput:
    """Tests for JSON output that includes rollout-complete details."""

    def test_rollout_state_includes_all_required_fields(self) -> None:
        """DeploymentRolloutState includes all required fields for JSON output."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "namespace": "default", "generation": 3},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 4,
                "updatedReplicas": 3,
                "availableReplicas": 3,
                "observedGeneration": 3,
                "unavailableReplicas": 0,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        state = states[0]
        # Verify all fields that should be in JSON output
        assert state.name == "k9b-backend"
        assert state.namespace == "default"
        assert state.desired_replicas == 3
        assert state.updated_replicas == 3
        assert state.available_replicas == 3
        assert state.total_replicas == 4
        assert state.observed_generation == 3
        assert state.generation == 3
        assert state.old_replicas == 1  # 4 - 3 = 1
        assert state.unavailable_replicas == 0
        assert state.complete is False  # Because old_replicas > 0
        assert "old replicas remain: 1" in state.blocked_reason

    def test_complete_state_blocked_reason_empty(self) -> None:
        """Complete rollout should have empty blocked_reason."""
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

        assert all_complete is True
        assert states[0].complete is True
        assert states[0].blocked_reason == ""
        assert "rollout-complete" in summary

    def test_summary_includes_incomplete_deployments(self) -> None:
        """Summary should include incomplete deployment names and reasons."""
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
                    "updatedReplicas": 1,
                    "availableReplicas": 1,
                    "observedGeneration": 1,
                },
            },
        ])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False
        assert "k9b-scheduler" in summary
        assert "k9b-backend" not in summary  # backend is complete
        assert "not complete" in summary

    def test_json_output_explains_old_replicas(self) -> None:
        """When old replicas remain, output should explain the derivation."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 2},
            "spec": {"replicas": 3},
            "status": {
                "replicas": 5,  # 3 new + 2 old
                "updatedReplicas": 3,
                "availableReplicas": 3,
                "observedGeneration": 2,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False
        state = states[0]
        assert state.old_replicas == 2  # 5 - 3 = 2
        assert "old replicas remain: 2" in state.blocked_reason
        # Total and updated should be in state for debugging
        assert state.total_replicas == 5
        assert state.updated_replicas == 3

    def test_json_output_explains_generation_mismatch(self) -> None:
        """When observedGeneration doesn't match generation, output should show both."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 5},
            "spec": {"replicas": 2},
            "status": {
                "replicas": 2,
                "updatedReplicas": 2,
                "availableReplicas": 2,
                "observedGeneration": 4,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False
        state = states[0]
        assert state.generation == 5
        assert state.observed_generation == 4
        assert "observedGeneration=4 < generation=5" in state.blocked_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
