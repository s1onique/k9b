#!/usr/bin/env python3
"""Edge case tests for rollout-complete classifier.

Tests missing field handling and boundary conditions.
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


class TestMissingFieldHandling:
    """Missing fields should be treated conservatively."""

    def test_missing_status_replicas_treated_as_unknown(self) -> None:
        """Missing status.replicas means old-replica state is unknown.

        With other criteria met and no old-replicas computable, this may still
        pass if all explicit criteria are satisfied.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 1},
            "status": {
                # No replicas field
                "updatedReplicas": 1,
                "availableReplicas": 1,
                "observedGeneration": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        # With updated=1 and available=1 for desired=1, this should pass
        # even though total_replicas is 0 (defaulted)
        assert all_complete is True, "Complete rollout should succeed even with missing replicas field"
        assert states[0].total_replicas == 0, "Missing replicas defaults to 0"
        assert states[0].old_replicas == 0, "Old replicas should be 0 when updated=1, total=0"

    def test_unavailable_replicas_present_and_nonzero_not_success(self) -> None:
        """When unavailableReplicas is present and non-zero, should not be success."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 2},
            "status": {
                "replicas": 2,
                "updatedReplicas": 2,
                "availableReplicas": 1,
                "observedGeneration": 1,
                "unavailableReplicas": 1,
            },
        }])

        all_complete, states, summary = _check_deployment_complete_from_json(deployments_json)

        assert all_complete is False, "Unavailable replicas present should not be success"
        assert "availableReplicas=1 < desired=2" in states[0].blocked_reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
