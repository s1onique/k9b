"""Unit tests for Alertmanager CRD discovery strategy.

Tests cover:
- Successful CRD discovery
- Handling empty/no resources
- CRD not installed scenarios
- kubectl not found errors
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    CRDDiscoveryStrategy,
)


class TestCRDDiscovery:
    """Tests for CRD-based discovery."""

    def test_crd_discovery_success(self) -> None:
        """Test CRD discovery successfully finds Alertmanager CRDs.

        PATCH NOTE: The CRD strategy uses subprocess.run directly for kubectl commands.
        We patch subprocess.run at the correct seam where it's looked up.
        See ACT-K9B-KUBECTL-BOUNDARY-REGRESSION01.
        """
        strategy = CRDDiscoveryStrategy()

        # Mock kubectl output
        kubectl_output = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "AlertmanagerList",
            "items": [
                {
                    "metadata": {
                        "name": "main",
                        "namespace": "monitoring",
                    },
                    "spec": {},
                },
                {
                    "metadata": {
                        "name": "long-lasting",
                        "namespace": "observability",
                    },
                    "spec": {},
                },
            ],
        }

        # Patch at the correct seam: where subprocess.run is looked up in the CRD strategy module
        # The CRD strategy imports subprocess inside its discover method
        with patch(
            "k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy.subprocess.run",
            return_value=MagicMock(
                returncode=0,
                stdout=json.dumps(kubectl_output),
                stderr="",
            ),
        ):
            result = strategy.discover()

        assert result.strategy == "alertmanager-crd"
        assert len(result.sources) == 2

        source_ids = {s.source_id for s in result.sources}
        assert "crd:monitoring/main" in source_ids
        assert "crd:observability/long-lasting" in source_ids

        # All sources should have CRD origin
        for source in result.sources:
            assert source.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
            assert source.state == AlertmanagerSourceState.DISCOVERED

    def test_crd_discovery_no_resources(self) -> None:
        """Test CRD discovery handles no resources gracefully."""
        strategy = CRDDiscoveryStrategy()

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "No resources found in alertmanager namespace"

            mock_run.return_value = mock_result

            result = strategy.discover()

        assert result.strategy == "alertmanager-crd"
        assert len(result.sources) == 0
        assert len(result.errors) == 0  # No error, just empty

    def test_crd_discovery_crd_not_installed(self) -> None:
        """Test CRD discovery handles CRD not installed gracefully."""
        strategy = CRDDiscoveryStrategy()

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "the server doesn't have a resource type 'alertmanagers'"

            mock_run.return_value = mock_result

            result = strategy.discover()

        assert result.strategy == "alertmanager-crd"
        assert len(result.sources) == 0
        # CRD not installed generates an error message but still returns empty sources gracefully
        # This is acceptable behavior - the strategy tried but the CRD doesn't exist

    def test_crd_discovery_kubectl_not_found(self) -> None:
        """Test CRD discovery handles kubectl not found."""
        strategy = CRDDiscoveryStrategy()

        with patch("subprocess.run", side_effect=FileNotFoundError("kubectl not found")):
            result = strategy.discover()

        assert result.strategy == "alertmanager-crd"
        assert len(result.sources) == 0
        assert "kubectl not found" in result.errors[0]
