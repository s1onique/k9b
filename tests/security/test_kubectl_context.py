"""Tests for kubectl_context module - regression tests for internal context leakage."""

import pytest

from k8s_diag_agent.security.kubectl_context import (
    display_kube_cluster_label,
    is_real_kube_context,
    render_kubectl_context_args,
    sanitize_cluster_prose,
)
from k8s_diag_agent.security.path_validation import SecurityError


class TestIsRealKubeContext:
    """Tests for is_real_kube_context function."""

    def test_real_context_returns_true(self) -> None:
        """Real kubeconfig contexts should return True."""
        assert is_real_kube_context("my-prod-cluster") is True
        assert is_real_kube_context("admin@prod") is True
        assert is_real_kube_context("dev-cluster") is True
        assert is_real_kube_context("gke_project_us-central1_cluster-1") is True

    def test_in_cluster_returns_false(self) -> None:
        """Internal 'in-cluster' sentinel should return False."""
        assert is_real_kube_context("in-cluster") is False

    def test_in_cluster_underscore_returns_false(self) -> None:
        """Internal 'in_cluster' variant should return False."""
        assert is_real_kube_context("in_cluster") is False

    def test_none_returns_false(self) -> None:
        """None context should return False."""
        assert is_real_kube_context(None) is False

    def test_empty_string_returns_false(self) -> None:
        """Empty string should return False - not a real context."""
        assert is_real_kube_context("") is False

    def test_whitespace_only_returns_false(self) -> None:
        """Whitespace-only string should return False - not a real context."""
        assert is_real_kube_context("   ") is False
        assert is_real_kube_context("\t") is False

    def test_padded_in_cluster_returns_false(self) -> None:
        """Padded 'in-cluster' should return False - normalization before check."""
        assert is_real_kube_context(" in-cluster ") is False
        assert is_real_kube_context("  in_cluster  ") is False
        assert is_real_kube_context("  in-cluster") is False
        assert is_real_kube_context("in-cluster  ") is False


class TestRenderKubectlContextArgs:
    """Tests for render_kubectl_context_args function."""

    def test_real_context_returns_context_args(self) -> None:
        """Real contexts should return --context flag."""
        result = render_kubectl_context_args("my-prod-cluster")
        assert result == ["--context", "my-prod-cluster"]

    def test_in_cluster_returns_empty_list(self) -> None:
        """'in-cluster' should NOT produce --context flag."""
        result = render_kubectl_context_args("in-cluster")
        assert result == []

    def test_in_cluster_underscore_returns_empty_list(self) -> None:
        """'in_cluster' should NOT produce --context flag."""
        result = render_kubectl_context_args("in_cluster")
        assert result == []

    def test_none_returns_empty_list(self) -> None:
        """None should return empty list."""
        result = render_kubectl_context_args(None)
        assert result == []

    def test_context_args_usable_in_command(self) -> None:
        """Context args should be directly usable in command construction."""
        args = render_kubectl_context_args("prod-cluster")
        command = ["kubectl", "get", "pods", *args]
        assert command == ["kubectl", "get", "pods", "--context", "prod-cluster"]

    def test_in_cluster_command_no_context_flag(self) -> None:
        """In-cluster mode should produce commands without --context flag."""
        args = render_kubectl_context_args("in-cluster")
        command = ["kubectl", "get", "pods", *args]
        assert command == ["kubectl", "get", "pods"]
        assert "--context" not in command
        assert "in-cluster" not in command

    def test_padded_in_cluster_returns_empty(self) -> None:
        """Padded 'in-cluster' should return empty list - normalization before check."""
        assert render_kubectl_context_args(" in-cluster ") == []
        assert render_kubectl_context_args("  in_cluster  ") == []
        assert render_kubectl_context_args("  in-cluster") == []
        assert render_kubectl_context_args("in-cluster  ") == []

    def test_invalid_context_rejected(self) -> None:
        """Invalid context names with shell metacharacters should raise SecurityError."""
        with pytest.raises(SecurityError):
            render_kubectl_context_args("bad;context")
        with pytest.raises(SecurityError):
            render_kubectl_context_args("bad context")
        with pytest.raises(SecurityError):
            render_kubectl_context_args("context$(whoami)")
        with pytest.raises(SecurityError):
            render_kubectl_context_args("../etc")


class TestDisplayKubeClusterLabel:
    """Tests for display_kube_cluster_label function."""

    def test_real_cluster_name_returned(self) -> None:
        """Real cluster names should be returned as-is."""
        assert display_kube_cluster_label("rc-runity-test-msk1-c02", "in-cluster") == "rc-runity-test-msk1-c02"
        assert display_kube_cluster_label("prod-cluster", "in-cluster") == "prod-cluster"

    def test_in_cluster_name_with_context_fallback(self) -> None:
        """When cluster_name is internal marker, use context as fallback if real."""
        assert display_kube_cluster_label("in-cluster", "real-context") == "real-context"
        assert display_kube_cluster_label("in_cluster", "admin@prod") == "admin@prod"

    def test_in_cluster_name_both_internal_returns_none(self) -> None:
        """When both cluster_name and context are internal markers, return None."""
        assert display_kube_cluster_label("in-cluster", "in-cluster") is None

    def test_none_cluster_returns_none(self) -> None:
        """None cluster_name returns None."""
        assert display_kube_cluster_label(None, None) is None


class TestSanitizeClusterProse:
    """Tests for sanitize_cluster_prose function."""

    def test_real_cluster_returned(self) -> None:
        """Real cluster names are returned unchanged."""
        assert sanitize_cluster_prose("rc-runity-test-msk1-c02", "in-cluster") == "rc-runity-test-msk1-c02"

    def test_in_cluster_falls_back_to_context(self) -> None:
        """Internal marker falls back to real context."""
        assert sanitize_cluster_prose("in-cluster", "real-context") == "real-context"

    def test_in_cluster_falls_back_to_neutral(self) -> None:
        """Internal marker with no fallback returns neutral fallback."""
        assert sanitize_cluster_prose("in-cluster", "in-cluster") == "the cluster"
        assert sanitize_cluster_prose("in-cluster", None) == "the cluster"
