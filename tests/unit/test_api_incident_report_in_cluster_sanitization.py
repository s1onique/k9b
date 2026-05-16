"""Regression tests for "in-cluster" sanitization in incident report and operator worklist.

These tests verify that internal context markers like "in-cluster" and "in_cluster"
do not leak into operator-facing UI fields including:
- Provider summary in incident report
- Review enrichment next_checks commands
- Operator worklist targetCluster and targetContext
- Deterministic next-check cluster labels
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.security.kubectl_context import (
    display_kube_cluster_label,
    is_internal_kube_marker,
    sanitize_cluster_prose,
    sanitize_kubectl_display_command,
)
from k8s_diag_agent.ui.api_incident_report import (
    _sanitize_target_cluster,
    _sanitize_target_context,
)

# =============================================================================
# Unit Tests for Sanitization Helpers
# =============================================================================


class TestSanitizeTargetCluster(unittest.TestCase):
    """Tests for _sanitize_target_cluster function."""

    def test_in_cluster_returns_cluster_local(self) -> None:
        """Internal 'in-cluster' cluster label returns 'cluster-local'."""
        result = _sanitize_target_cluster("in-cluster")
        self.assertEqual(result, "cluster-local")

    def test_in_cluster_underscore_returns_cluster_local(self) -> None:
        """Internal 'in_cluster' cluster label returns 'cluster-local'."""
        result = _sanitize_target_cluster("in_cluster")
        self.assertEqual(result, "cluster-local")

    def test_in_cluster_with_context_fallback(self) -> None:
        """'in-cluster' with valid context fallback returns context."""
        result = _sanitize_target_cluster("in-cluster", "prod-cluster")
        self.assertEqual(result, "prod-cluster")

    def test_in_cluster_underscore_with_context_fallback(self) -> None:
        """'in_cluster' with valid context fallback returns context."""
        result = _sanitize_target_cluster("in_cluster", "prod-cluster")
        self.assertEqual(result, "prod-cluster")

    def test_in_cluster_with_internal_context_fallback_returns_cluster_local(self) -> None:
        """'in-cluster' with 'in-cluster' context fallback returns 'cluster-local'."""
        result = _sanitize_target_cluster("in-cluster", "in-cluster")
        self.assertEqual(result, "cluster-local")

    def test_real_cluster_preserved(self) -> None:
        """Real cluster labels are preserved."""
        result = _sanitize_target_cluster("prod-eu-1")
        self.assertEqual(result, "prod-eu-1")

    def test_none_input_returns_none(self) -> None:
        """None input returns None."""
        result = _sanitize_target_cluster(None)
        self.assertIsNone(result)


class TestSanitizeTargetContext(unittest.TestCase):
    """Tests for _sanitize_target_context function."""

    def test_in_cluster_returns_cluster_local(self) -> None:
        """Internal 'in-cluster' context returns 'cluster-local'."""
        result = _sanitize_target_context("in-cluster")
        self.assertEqual(result, "cluster-local")

    def test_in_cluster_underscore_returns_cluster_local(self) -> None:
        """Internal 'in_cluster' context returns 'cluster-local'."""
        result = _sanitize_target_context("in_cluster")
        self.assertEqual(result, "cluster-local")

    def test_real_context_preserved(self) -> None:
        """Real contexts are preserved."""
        result = _sanitize_target_context("prod-cluster")
        self.assertEqual(result, "prod-cluster")

    def test_none_input_returns_none(self) -> None:
        """None input returns None."""
        result = _sanitize_target_context(None)
        self.assertIsNone(result)


# =============================================================================
# Tests for Incident Report with "in-cluster" Provider Summary
# =============================================================================


class TestIncidentReportProviderSummarySanitization(unittest.TestCase):
    """Tests that provider summary starting with 'in-cluster' is sanitized."""

    def test_derived_claim_sanitizes_in_cluster_label(self) -> None:
        """Derived claim with 'in-cluster' cluster label uses safe fallback."""
        # Test display_kube_cluster_label directly
        safe_label = display_kube_cluster_label("in-cluster", "in-cluster")
        self.assertIsNone(safe_label)  # Both are internal markers

    def test_derived_claim_with_real_context_fallback(self) -> None:
        """Derived claim uses context as fallback when cluster_label is internal marker."""
        safe_label = display_kube_cluster_label("in-cluster", "real-cluster")
        self.assertEqual(safe_label, "real-cluster")


# =============================================================================
# Tests for Review Enrichment next_checks sanitization
# =============================================================================


class TestReviewEnrichmentNextChecksSanitization(unittest.TestCase):
    """Tests that nextChecks with --context in-cluster are sanitized."""

    def test_sanitize_kubectl_display_command_removes_in_cluster_context(self) -> None:
        """kubectl commands with --context in-cluster are sanitized."""
        cmd = "kubectl get pods --context in-cluster"
        result = sanitize_kubectl_display_command(cmd)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("--context", result)
        self.assertNotIn("in-cluster", result)

    def test_sanitize_kubectl_display_command_removes_in_cluster_equals(self) -> None:
        """kubectl commands with --context=in-cluster are sanitized."""
        cmd = "kubectl get crd --context=in-cluster"
        result = sanitize_kubectl_display_command(cmd)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("--context", result)
        self.assertNotIn("in-cluster", result)

    def test_sanitize_kubectl_display_command_preserves_real_context(self) -> None:
        """kubectl commands with real --context are preserved."""
        cmd = "kubectl get pods --context prod-cluster"
        result = sanitize_kubectl_display_command(cmd)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("--context prod-cluster", result)


# =============================================================================
# Tests for Operator Worklist target sanitization
# =============================================================================


class TestOperatorWorklistTargetSanitization(unittest.TestCase):
    """Tests that worklist targetCluster and targetContext do not show 'in-cluster'."""

    def test_queue_item_with_in_cluster_target_sanitized(self) -> None:
        """Queue item targetCluster 'in-cluster' should return 'cluster-local'."""
        result = _sanitize_target_cluster("in-cluster", "in-cluster")
        self.assertEqual(result, "cluster-local")

    def test_queue_item_with_real_target_preserved(self) -> None:
        """Queue item with real targetCluster is preserved."""
        result = _sanitize_target_cluster("rc-runity-test-msk1-c02", "rc-runity-test-msk1-c02")
        self.assertEqual(result, "rc-runity-test-msk1-c02")

    def test_sanitize_target_context_in_cluster_returns_cluster_local(self) -> None:
        """Worklist targetContext 'in-cluster' should return 'cluster-local'."""
        result = _sanitize_target_context("in-cluster")
        self.assertEqual(result, "cluster-local")

    def test_sanitize_target_context_real_value_preserved(self) -> None:
        """Worklist targetContext with real value is preserved."""
        result = _sanitize_target_context("rc-runity-test-msk1-c02")
        self.assertEqual(result, "rc-runity-test-msk1-c02")


# =============================================================================
# Tests for sanitize_cluster_prose in provider summary
# =============================================================================


class TestSanitizeClusterProse(unittest.TestCase):
    """Tests for sanitize_cluster_prose function."""

    def test_in_cluster_in_prose_returns_cluster_local(self) -> None:
        """'in-cluster' in prose text returns 'cluster-local' presentation label."""
        result = sanitize_cluster_prose("in-cluster is in a degraded state")
        self.assertEqual(result, "cluster-local is in a degraded state")

    def test_in_cluster_underscore_in_prose_returns_cluster_local(self) -> None:
        """'in_cluster' in prose text returns 'cluster-local' presentation label."""
        result = sanitize_cluster_prose("in_cluster needs attention")
        self.assertEqual(result, "cluster-local needs attention")

    def test_real_cluster_in_prose_preserved(self) -> None:
        """Real cluster names in prose are preserved."""
        result = sanitize_cluster_prose("prod-cluster is degraded")
        self.assertEqual(result, "prod-cluster is degraded")

    def test_in_cluster_with_context_fallback_in_prose(self) -> None:
        """'in-cluster' with real context fallback in prose uses context."""
        result = sanitize_cluster_prose("in-cluster has issues", "real-cluster")
        self.assertEqual(result, "real-cluster has issues")


# =============================================================================
# Tests for is_internal_kube_marker
# =============================================================================


class TestIsInternalKubeMarker(unittest.TestCase):
    """Tests for is_internal_kube_marker function."""

    def test_in_cluster_is_internal_marker(self) -> None:
        """'in-cluster' is recognized as internal marker."""
        self.assertTrue(is_internal_kube_marker("in-cluster"))

    def test_in_cluster_underscore_is_internal_marker(self) -> None:
        """'in_cluster' is recognized as internal marker."""
        self.assertTrue(is_internal_kube_marker("in_cluster"))

    def test_real_cluster_not_internal_marker(self) -> None:
        """Real cluster names are not internal markers."""
        self.assertFalse(is_internal_kube_marker("prod-cluster"))
        self.assertFalse(is_internal_kube_marker("prod_eu_1"))
        self.assertFalse(is_internal_kube_marker("rc-runity-test-msk1-c02"))

    def test_none_not_internal_marker(self) -> None:
        """None input is not an internal marker."""
        self.assertFalse(is_internal_kube_marker(None))


# =============================================================================
# Tests for display_kube_cluster_label
# =============================================================================


class TestDisplayKubeClusterLabel(unittest.TestCase):
    """Tests for display_kube_cluster_label function."""

    def test_in_cluster_returns_none(self) -> None:
        """'in-cluster' cluster name returns None."""
        result = display_kube_cluster_label("in-cluster")
        self.assertIsNone(result)

    def test_in_cluster_underscore_returns_none(self) -> None:
        """'in_cluster' cluster name returns None."""
        result = display_kube_cluster_label("in_cluster")
        self.assertIsNone(result)

    def test_in_cluster_with_real_context_returns_context(self) -> None:
        """'in-cluster' with real context returns the context."""
        result = display_kube_cluster_label("in-cluster", "prod-cluster")
        self.assertEqual(result, "prod-cluster")

    def test_real_cluster_preserved(self) -> None:
        """Real cluster names are preserved."""
        result = display_kube_cluster_label("rc-runity-test-msk1-c02")
        self.assertEqual(result, "rc-runity-test-msk1-c02")


if __name__ == "__main__":
    unittest.main()