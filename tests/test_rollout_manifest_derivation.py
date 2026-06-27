#!/usr/bin/env python3
"""Tests for manifest derivation - expected Deployment names from rendered Helm manifest.

Tests the contract: rendered manifests produce k9b-backend, k9b-scheduler
and the monitor must derive expected Deployment names from these manifests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.k9b_cnpg_live_lab_monitor import (
    get_expected_deployments_from_manifest,
)
from tests.conftest_rollout_monitor import RENDERED_MANIFEST_FIXTURE


class TestRenderedManifestFixtureDerivation:
    """Regression Test 1: Assert expected Deployment derivation returns exactly rendered names.

    A rendered-manifest fixture with Deployments:
    - k9b-backend
    - k9b-scheduler
    - no k9b Deployment

    Must assert expected Deployment derivation returns exactly the rendered Deployment names.
    """

    def test_fixture_has_no_k9b_deployment(self) -> None:
        """Fixture must not contain a Deployment named 'k9b'."""
        docs = list(yaml.safe_load_all(RENDERED_MANIFEST_FIXTURE))
        deployment_names = [
            doc["metadata"]["name"]
            for doc in docs
            if isinstance(doc, dict) and doc.get("kind") == "Deployment"
        ]
        assert "k9b" not in deployment_names, f"Found unexpected Deployment 'k9b' in fixture: {deployment_names}"
        assert "k9b-backend" in deployment_names
        assert "k9b-scheduler" in deployment_names

    def test_fixture_has_expected_deployments(self) -> None:
        """Fixture must contain k9b-backend and k9b-scheduler Deployments."""
        assert "name: k9b-backend" in RENDERED_MANIFEST_FIXTURE
        assert "name: k9b-scheduler" in RENDERED_MANIFEST_FIXTURE
        assert "kind: Deployment" in RENDERED_MANIFEST_FIXTURE

    def test_derives_exactly_rendered_deployment_names(self) -> None:
        """Expected Deployment derivation returns exactly rendered names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(RENDERED_MANIFEST_FIXTURE)

            result = get_expected_deployments_from_manifest(artifact_dir)

            # Must derive exactly the rendered Deployment names
            assert result == ["k9b-backend", "k9b-scheduler"]
            # Must NOT include a non-existent "k9b" Deployment
            assert "k9b" not in result
            # Must be exactly 2 Deployments
            assert len(result) == 2

    def test_manifest_derivation_uses_release_name_fallback(self) -> None:
        """Manifest derivation must use release name as expected_name fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            (helm_dir / "rendered-manifest.yaml").write_text(RENDERED_MANIFEST_FIXTURE)

            result = get_expected_deployments_from_manifest(
                artifact_dir,
                release_name="k9b",
                namespace="k9b-live-lab"
            )

            # Must still derive the actual Deployment names
            assert "k9b-backend" in result
            assert "k9b-scheduler" in result
            # Must NOT include "k9b" as a Deployment name
            assert "k9b" not in result

    def test_cli_artifact_dir_structure_for_manifest(self) -> None:
        """Verify CLI expects rendered-manifest.yaml at helm/ subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            helm_dir = artifact_dir / "helm"
            helm_dir.mkdir(parents=True)
            rendered_path = helm_dir / "rendered-manifest.yaml"

            # CLI expects this path
            assert rendered_path.parent.name == "helm"
            assert rendered_path.name == "rendered-manifest.yaml"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
