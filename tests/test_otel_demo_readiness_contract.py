"""Regression tests: OTel Demo deployment name contract and readiness diagnostics.

This module contains focused regression tests for:
- OTel Demo deployment names matching chart 0.40.9
- Readiness diagnostics classifying 404 as "missing" vs "api_error"

These tests prevent regressions where:
1. REQUIRED_DEPLOYMENTS used legacy *service names (e.g., "recommendationservice")
   instead of chart 0.40.9 names (e.g., "recommendation")
2. Readiness failures were reported as "api_error" instead of "missing",
   obscuring the root cause (wrong deployment name)
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_constants import REQUIRED_DEPLOYMENTS

# =============================================================================
# OTel Demo deployment names for chart 0.40.9
# =============================================================================


class TestOtelDemoDeploymentNames:
    """Regression tests for OTel Demo deployment name contract.

    These tests verify that REQUIRED_DEPLOYMENTS uses chart 0.40.9 names,
    not the legacy *service naming convention.

    The previous failure was caused by waiting for deployment names like
    "recommendationservice" when the chart renders them as "recommendation".
    """

    def test_required_deployments_match_chart_0_40_9_names(self) -> None:
        """REQUIRED_DEPLOYMENTS must use chart 0.40.9 deployment names."""
        expected = {
            "frontend",
            "recommendation",
            "product-catalog",
            "cart",
            "checkout",
            "payment",
            "shipping",
            "currency",
            "email",
            "flagd",
        }

        assert set(REQUIRED_DEPLOYMENTS) == expected

    def test_required_deployments_excludes_legacy_service_names(self) -> None:
        """REQUIRED_DEPLOYMENTS must NOT contain legacy *service names."""
        legacy_names = {
            "recommendationservice",
            "productcatalogservice",
            "cartservice",
            "checkoutservice",
            "paymentservice",
            "shippingservice",
            "currencyservice",
            "emailservice",
        }

        for legacy_name in legacy_names:
            assert legacy_name not in REQUIRED_DEPLOYMENTS, (
                f"Legacy name '{legacy_name}' should not be in REQUIRED_DEPLOYMENTS. "
                f"Use chart 0.40.9 names instead."
            )

    def test_required_deployments_includes_recommendation_not_recommendationservice(
        self,
    ) -> None:
        """Must use 'recommendation' not 'recommendationservice'."""
        assert "recommendation" in REQUIRED_DEPLOYMENTS
        assert "recommendationservice" not in REQUIRED_DEPLOYMENTS

    def test_required_deployments_includes_product_catalog_not_productcatalogservice(
        self,
    ) -> None:
        """Must use 'product-catalog' not 'productcatalogservice'."""
        assert "product-catalog" in REQUIRED_DEPLOYMENTS
        assert "productcatalogservice" not in REQUIRED_DEPLOYMENTS


# =============================================================================
# Readiness diagnostics classify 404 as "missing"
# =============================================================================


class TestReadinessDiagnostics:
    """Regression tests for readiness failure classification.

    These tests verify that kubectl 404 errors are reported as "missing"
    rather than "api_error", making it obvious that a deployment name is wrong.
    """

    def test_classify_deployment_lookup_failure_detects_404(self) -> None:
        """404 must be classified as 'missing', not 'api_error'."""
        from scripts.k9b_lab_common_readiness import _classify_deployment_lookup_failure

        # Mock subprocess to return 404
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = 'error: deployments.apps "recommendationservice" not found'
            mock_run.return_value = mock_result

            result = _classify_deployment_lookup_failure(
                "/fake/kubeconfig", "otel-demo", "recommendationservice"
            )

            assert result == "missing", (
                f"Expected 'missing' for 404, got '{result}'. "
                "404 errors should indicate the deployment name is wrong, not an API error."
            )

    def test_classify_deployment_lookup_failure_detects_403(self) -> None:
        """403 (forbidden) must be classified as 'api_forbidden'."""
        from scripts.k9b_lab_common_readiness import _classify_deployment_lookup_failure

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = (
                "error: deployments.apps is forbidden: User cannot get deployments"
            )
            mock_run.return_value = mock_result

            result = _classify_deployment_lookup_failure(
                "/fake/kubeconfig", "otel-demo", "frontend"
            )

            assert result == "api_forbidden", (
                f"Expected 'api_forbidden' for 403, got '{result}'."
            )

    def test_classify_deployment_lookup_failure_detects_401(self) -> None:
        """401 (unauthorized) must be classified as 'api_unauthorized'."""
        from scripts.k9b_lab_common_readiness import _classify_deployment_lookup_failure

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = (
                'error: You must be logged in to the server (Unauthorized)'
            )
            mock_run.return_value = mock_result

            result = _classify_deployment_lookup_failure(
                "/fake/kubeconfig", "otel-demo", "frontend"
            )

            assert result == "api_unauthorized", (
                f"Expected 'api_unauthorized' for 401, got '{result}'."
            )

    def test_classify_deployment_lookup_failure_detects_timeout(self) -> None:
        """Timeout must be classified as 'api_timeout'."""
        from scripts.k9b_lab_common_readiness import _classify_deployment_lookup_failure

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=15)

            result = _classify_deployment_lookup_failure(
                "/fake/kubeconfig", "otel-demo", "frontend"
            )

            assert result == "api_timeout", (
                f"Expected 'api_timeout' for timeout, got '{result}'."
            )

    def test_classify_deployment_lookup_failure_detects_generic_error(self) -> None:
        """Generic errors must be classified as 'api_error:code'."""
        from scripts.k9b_lab_common_readiness import _classify_deployment_lookup_failure

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 2
            mock_result.stderr = "some other error"
            mock_run.return_value = mock_result

            result = _classify_deployment_lookup_failure(
                "/fake/kubeconfig", "otel-demo", "frontend"
            )

            assert result == "api_error:2", (
                f"Expected 'api_error:2' for generic error, got '{result}'."
            )

    def test_wait_for_deployments_reports_missing_for_nonexistent_deployment(
        self,
    ) -> None:
        """wait_for_deployments_ready must report 'missing' for nonexistent deployments."""
        from scripts.k9b_lab_common_readiness import wait_for_deployments_ready

        # Mock kubectl_json to return failure
        with patch(
            "scripts.k9b_lab_common_readiness.kubectl_json"
        ) as mock_json:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.data = None
            mock_json.return_value = mock_result

            # Mock the classifier to return "missing"
            with patch(
                "scripts.k9b_lab_common_readiness._classify_deployment_lookup_failure"
            ) as mock_classify:
                mock_classify.return_value = "missing"

                # Call with short timeout
                success, status = wait_for_deployments_ready(
                    "/fake/kubeconfig",
                    "test-ns",
                    ["nonexistent-deployment"],
                    timeout_seconds=1,
                    poll_interval=1,
                )

                # Should fail with "missing" status
                assert success is False
                assert "missing" in status
