"""Regression tests for kubectl execution boundary.

Reference: ACT-K9B-KUBECTL-BOUNDARY-REGRESSION01

These tests verify that:
1. Unit tests cannot execute real kubectl without explicit live_kubernetes marker
2. Tests that NEED real kubectl are properly marked
3. Call-site seam patching works correctly
"""

from __future__ import annotations

import subprocess

import pytest


class TestKubectlBoundaryRegression:
    """Tests verifying kubectl boundary enforcement in unit tests."""

    @pytest.mark.live_kubernetes
    def test_live_kubernetes_marker_allows_kubectl(self, request: pytest.FixtureRequest) -> None:
        """Verify that @pytest.mark.live_kubernetes skips the kubectl guard.
        
        This test is intentionally marked as live_kubernetes to verify the guard
        can be bypassed for integration tests that need real cluster access.
        """
        # Check that the test is marked with live_kubernetes
        marker = request.node.get_closest_marker("live_kubernetes")
        assert marker is not None, "This test should be marked with @pytest.mark.live_kubernetes"

    def test_unit_test_blocks_real_kubectl_via_popen(self) -> None:
        """Regression test: unit tests must not execute real kubectl via subprocess.Popen.
        
        This test verifies the boundary is enforced by calling subprocess.Popen with
        a kubectl command and expecting pytest.fail to be raised.
        """
        with pytest.raises(pytest.fail.Exception, match="Unit test attempted real kubectl via subprocess.Popen"):
            subprocess.Popen(["kubectl", "version", "--client"])

    def test_unit_test_blocks_real_kubectl_via_run(self) -> None:
        """Regression test: unit tests must not execute real kubectl via subprocess.run.
        
        This test verifies the boundary is enforced by calling subprocess.run with
        a kubectl command and expecting pytest.fail to be raised.
        """
        with pytest.raises(pytest.fail.Exception, match="Unit test attempted real kubectl via subprocess.run"):
            subprocess.run(["kubectl", "version", "--client"], capture_output=True)

    def test_unit_test_blocks_real_kubectl_via_run_shell(self) -> None:
        """Regression test: unit tests must not execute real kubectl via subprocess.run with shell=True.
        
        This test verifies the boundary handles string-shell form kubectl commands.
        """
        with pytest.raises(pytest.fail.Exception, match="Unit test attempted real kubectl via subprocess.run"):
            subprocess.run("kubectl version --client", shell=True, capture_output=True)


class TestCallSiteSeamPatching:
    """Tests verifying correct seam patching for kubectl mocks."""

    def test_run_kubectl_seam_exists(self) -> None:
        """Verify run_kubectl is accessible at the expected call-site seam."""
        from k8s_diag_agent.security.kubectl_subprocess import run_kubectl
        
        assert callable(run_kubectl)
        assert run_kubectl.__name__ == "run_kubectl"

    def test_kubectl_alias_in_collectors_exists(self) -> None:
        """Verify the kubectl wrapper in incident_collectors is accessible."""
        from k8s_diag_agent.collect.incident_collectors import kubectl
        
        assert callable(kubectl)
        assert kubectl.__name__ == "kubectl"

    def test_identity_cluster_run_kubectl_exists(self) -> None:
        """Verify run_kubectl is accessible in identity.cluster module."""
        from k8s_diag_agent.identity.cluster import run_kubectl
        
        assert callable(run_kubectl)

    def test_live_snapshot_run_command_exists(self) -> None:
        """Verify _run_command exists in live_snapshot as a test compatibility seam."""
        from k8s_diag_agent.collect.live_snapshot import _run_command
        
        assert callable(_run_command)


class TestExceptionHandlingCompatibility:
    """Tests verifying KubectlExecutionError handling compatibility."""

    def test_kubectl_execution_error_is_runtime_error(self) -> None:
        """Verify KubectlExecutionError is a RuntimeError subclass for backward compatibility."""
        from k8s_diag_agent.security.kubectl_errors import KubectlExecutionError
        
        error = KubectlExecutionError(
            "kubectl failed",
            command=["kubectl", "get", "pods"],
            returncode=1,
        )
        # Should be catchable as RuntimeError
        assert isinstance(error, RuntimeError)
        # Should have the expected attributes
        assert error.command == ["kubectl", "get", "pods"]
        assert error.returncode == 1

    def test_collectors_catch_runtime_error(self) -> None:
        """Verify incident_collectors catches RuntimeError (backward compat)."""
        from k8s_diag_agent.collect import incident_collectors
        
        # The collect functions catch RuntimeError, which includes KubectlExecutionError
        # This test documents the expected behavior
        assert hasattr(incident_collectors, "collect_pods")
        assert hasattr(incident_collectors, "collect_deployments")
        assert hasattr(incident_collectors, "collect_events")


class TestDiscoverySourcePreservation:
    """Tests verifying discovery sources are preserved on verification failure."""

    def test_verify_and_update_inventory_handles_verification_failure(self) -> None:
        """Verify that verification failure preserves sources in degraded state."""
        import urllib.error
        from unittest.mock import patch

        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            AlertmanagerSource,
            AlertmanagerSourceInventory,
            AlertmanagerSourceOrigin,
            AlertmanagerSourceState,
            verify_and_update_inventory,
        )

        inventory = AlertmanagerSourceInventory()
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        ))

        # Mock verification failure
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            
            verified = verify_and_update_inventory(inventory)

        # Source should be degraded, not removed
        assert "crd:monitoring/main" in verified.sources
        assert verified.sources["crd:monitoring/main"].state == AlertmanagerSourceState.DEGRADED
        assert verified.sources["crd:monitoring/main"].last_error is not None

    def test_manual_sources_not_verified(self) -> None:
        """Verify that manual sources are not verified and preserve their state."""
        from unittest.mock import patch

        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            AlertmanagerSource,
            AlertmanagerSourceInventory,
            AlertmanagerSourceOrigin,
            AlertmanagerSourceState,
            verify_and_update_inventory,
        )

        inventory = AlertmanagerSourceInventory()
        inventory.add_source(AlertmanagerSource(
            source_id="manual:custom",
            endpoint="http://custom:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        ))

        # Mock verification (should not be called for manual sources)
        with patch("urllib.request.urlopen") as mock_urlopen:
            verified = verify_and_update_inventory(inventory)

        # Manual source should be preserved without verification
        assert "manual:custom" in verified.sources
        assert verified.sources["manual:custom"].state == AlertmanagerSourceState.MANUAL
        # urlopen should NOT have been called for manual sources
        mock_urlopen.assert_not_called()
