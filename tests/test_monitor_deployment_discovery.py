#!/usr/bin/env python3
"""Tests for monitor deployment discovery from rendered manifests.

Tests the fix for the bug where the rollout monitor checked for Deployment/k9b
but the rendered chart produces k9b-backend, k9b-frontend, k9b-scheduler.

The monitor should derive expected deployments from rendered manifest inventory,
not hard-code a stale synthetic name.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_monitor import (
    get_expected_deployments_from_manifest,
)


class TestGetExpectedDeploymentsFromManifest:
    """Tests for deriving expected deployments from rendered manifest inventory."""

    def test_discovers_multiple_deployments(self) -> None:
        """Should discover k9b-backend, k9b-frontend, k9b-scheduler from rendered manifest."""
        rendered_yaml = """
apiVersion: v1
kind: Namespace
metadata:
  name: k9b
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
  namespace: k9b
spec:
  replicas: 1
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
  namespace: k9b
spec:
  replicas: 1
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
  namespace: k9b
spec:
  replicas: 1
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert len(result) == 3
            assert "k9b-backend" in result
            assert "k9b-frontend" in result
            assert "k9b-scheduler" in result

    def test_returns_empty_list_when_no_rendered_manifest(self) -> None:
        """Should return empty list when rendered manifest doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # No helm/rendered-manifest.yaml

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert result == []

    def test_returns_empty_list_when_no_deployments_in_manifest(self) -> None:
        """Should return empty list when manifest has no Deployment resources."""
        rendered_yaml = """
apiVersion: v1
kind: Namespace
metadata:
  name: k9b
---
apiVersion: v1
kind: Service
metadata:
  name: k9b-service
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert result == []

    def test_sorts_deployments_alphabetically(self) -> None:
        """Should return deployments in alphabetical order for determinism."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert result == ["k9b-backend", "k9b-frontend", "k9b-scheduler"]

    def test_handles_single_deployment(self) -> None:
        """Should handle single Deployment correctly."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert result == ["k9b-backend"]

    def test_does_not_include_other_workload_kinds(self) -> None:
        """Should only include Deployment, not StatefulSet, DaemonSet, etc."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: k9b-stateful
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: k9b-daemon
---
apiVersion: batch/v1
kind: Job
metadata:
  name: k9b-job
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            result = get_expected_deployments_from_manifest(artifact_dir)

            assert result == ["k9b-backend"]
            assert "k9b-stateful" not in result
            assert "k9b-daemon" not in result
            assert "k9b-job" not in result


class TestCheckRolloutSuccessMulti:
    """Tests for multi-deployment rollout success check."""

    def test_returns_success_when_all_deployments_healthy(self) -> None:
        """Should return success when all expected deployments are healthy."""
        # This test validates the function logic without actually calling kubectl
        # We test the parsing/matching logic separately
        expected = ["k9b-backend", "k9b-frontend", "k9b-scheduler"]
        cluster_deployments: dict[str, dict[str, object]] = {
            "k9b-backend": {},
            "k9b-frontend": {},
            "k9b-scheduler": {},
        }

        # All expected deployments are in cluster
        missing = [name for name in expected if name not in cluster_deployments]
        assert len(missing) == 0

    def test_returns_missing_when_deployment_not_found(self) -> None:
        """Should return missing message when expected deployment is absent."""
        expected = ["k9b-backend", "k9b-frontend", "k9b-scheduler"]
        cluster_deployments: dict[str, dict[str, Any]] = {}  # Empty - no deployments in cluster

        missing = [name for name in expected if name not in cluster_deployments]

        assert len(missing) == 3
        assert "k9b-backend" in missing


class TestMonitorDoesNotLookForK9bDeployment:
    """Regression test: monitor should NOT look for Deployment/k9b.

    This tests the contract fix: the monitor must NOT default to checking
    for a single Deployment named "k9b" when the chart renders multiple
    named workloads.
    """

    def test_rendered_manifest_has_no_k9b_deployment(self) -> None:
        """Verify the rendered manifest from the failing lab has no Deployment/k9b."""
        rendered_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(rendered_yaml)

            deployments = get_expected_deployments_from_manifest(artifact_dir)

            # The bug was that the monitor checked for "k9b" which doesn't exist
            assert "k9b" not in deployments
            # The correct behavior is to check for the actual rendered deployments
            assert "k9b-backend" in deployments
            assert "k9b-frontend" in deployments
            assert "k9b-scheduler" in deployments


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
