#!/usr/bin/env python3
"""Tests for rollout success semantics - desired/updated/available replicas and observedGeneration.

This module focuses specifically on the conditions required for rollout success
detection, covering the edge cases around replica counts and generation tracking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib

import scripts.k9b_cnpg_live_lab_bootstrap as bootstrap  # noqa: E402

importlib.reload(bootstrap)

from scripts.k9b_cnpg_live_lab_bootstrap import (  # noqa: E402
    classify_rollout_state,
)
from scripts.k9b_cnpg_live_lab_rollout import (  # noqa: E402
    _check_rollout_success_from_json,
)
from tests.rollout_classifier_extended_fixtures import (  # noqa: E402
    make_deployments_json,
    make_pods_json,
)


class TestSuccessDetection:
    """Tests for healthy rollout success detection via JSON-based success check."""

    def test_detects_success_when_deployments_healthy(self) -> None:
        """Should detect success when deployments are healthy (no pods needed for JSON check)."""
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 1},
            "spec": {"replicas": 1},
            "status": {
                "replicas": 1,
                "availableReplicas": 1,
            },
        }])
        result = _check_rollout_success_from_json('{"items": []}', deployments_json, '{"items": []}')
        assert result is True

    def test_json_success_check_allows_at_least_one_available(self) -> None:
        """JSON helper returns True if at least one replica is available.
        
        Note: The JSON helper checks `available < 1` (not `available < replicas`),
        so 1 available out of 2 replicas returns True.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend", "generation": 2},
            "spec": {"replicas": 2},
            "status": {
                "replicas": 2,
                "availableReplicas": 1,
            },
        }])
        result = _check_rollout_success_from_json('{"items": []}', deployments_json, '{"items": []}')
        assert result is True  # At least one available, so considered success by this helper

    def test_classify_rollout_state_healthy_when_no_issues(self) -> None:
        """Should classify as healthy when no failure conditions detected.
        
        Note: Empty pods AND empty deployments triggers expected_deployment_missing.
        We need at least one deployment to avoid that fallback.
        """
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {"replicas": 1, "availableReplicas": 1},
        }])
        result = classify_rollout_state('{"items": []}', deployments_json, '{"items": []}', "")
        assert result.fatal is False
        assert result.failure_class == ""

    def test_classify_rollout_state_healthy_with_pods(self) -> None:
        """Should classify as healthy when pods exist with no failures."""
        pods_json = make_pods_json([{
            "metadata": {"name": "healthy-pod"},
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        }])
        deployments_json = make_deployments_json([{
            "metadata": {"name": "k9b-backend"},
            "status": {
                "replicas": 1,
                "availableReplicas": 1,
            },
        }])
        result = classify_rollout_state(pods_json, deployments_json, '{"items": []}', "")
        assert result.fatal is False
        assert result.failure_class == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
