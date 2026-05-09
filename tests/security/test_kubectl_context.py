"""Tests for kubectl_context module - regression tests for internal context leakage."""

from k8s_diag_agent.security.kubectl_context import (
    is_real_kube_context,
    render_kubectl_context_args,
)


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
