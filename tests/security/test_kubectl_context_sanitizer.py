"""Regression tests for kubectl context sanitization.

These tests verify that internal context markers like "in-cluster"
do not leak into operator-facing display fields like worklist titles.
"""

from k8s_diag_agent.security.kubectl_context import sanitize_kubectl_display_command


class TestSanitizeKubectlDisplayCommand:
    """Regression tests for sanitize_kubectl_display_command function."""

    def test_in_cluster_context_not_in_title(self) -> None:
        """Internal 'in-cluster' context must not appear in title."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods --context in-cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in-cluster" not in result
        assert "kubectl get pods" in result

    def test_in_cluster_equals_format_not_in_title(self) -> None:
        """Internal '--context=in-cluster' format must not appear in title."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods --context=in-cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in-cluster" not in result
        assert "kubectl get pods" in result

    def test_in_cluster_underscore_not_in_title(self) -> None:
        """Internal 'in_cluster' context must not appear in title."""
        result = sanitize_kubectl_display_command(
            "kubectl get deployment metrics-server -n kube-system --context in_cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in_cluster" not in result
        assert "kubectl get deployment metrics-server -n kube-system" in result

    def test_namespace_in_cluster_preserved(self) -> None:
        """Namespace 'in-cluster' must be preserved (only --context flag is removed)."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods -n in-cluster"
        )
        assert result is not None
        assert "-n in-cluster" in result
        assert "--context" not in result

    def test_both_namespace_and_context_in_cluster(self) -> None:
        """Both namespace and context with 'in-cluster' must keep namespace."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods -n in-cluster --context in-cluster"
        )
        assert result is not None
        # Namespace -n in-cluster should be preserved
        assert "-n in-cluster" in result
        # --context flag should be removed (not the namespace)
        assert "--context" not in result

    def test_real_context_preserved_in_title(self) -> None:
        """Real kubeconfig context should be preserved in title."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods --context prod-cluster"
        )
        assert result is not None
        assert "--context prod-cluster" in result

    def test_real_context_equals_format_preserved(self) -> None:
        """Real context in --context=value format should be preserved."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods --context=prod-cluster"
        )
        assert result is not None
        assert "--context=prod-cluster" in result

    def test_short_form_context_real_value(self) -> None:
        """Short form -c with real context should be preserved."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods -c prod-cluster"
        )
        assert result is not None
        # -c short form with real context is kept
        assert "-c" in result or "prod-cluster" in result

    def test_short_form_context_internal_value(self) -> None:
        """Short form -c with internal context should be removed."""
        result = sanitize_kubectl_display_command(
            "kubectl get pods -c in-cluster"
        )
        assert result is not None
        assert "-c" not in result
        assert "in-cluster" not in result

    def test_logs_command_in_cluster_sanitized(self) -> None:
        """Logs command with in-cluster context should be sanitized."""
        result = sanitize_kubectl_display_command(
            "kubectl logs -n kube-system -l app=etcd --context in-cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in-cluster" not in result
        assert "-n kube-system" in result
        assert "-l app=etcd" in result

    def test_describe_command_in_cluster_sanitized(self) -> None:
        """Describe command with in-cluster context should be sanitized."""
        result = sanitize_kubectl_display_command(
            "kubectl describe pod -n monitoring alertmanager-0 --context in-cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in-cluster" not in result
        assert "kubectl describe pod" in result

    def test_no_kubectl_prefix_preserved(self) -> None:
        """Non-kubectl commands should be preserved as-is."""
        result = sanitize_kubectl_display_command(
            "Check network connectivity"
        )
        assert result == "Check network connectivity"

    def test_none_input_returns_none(self) -> None:
        """None input should return None."""
        result = sanitize_kubectl_display_command(None)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string input should return None."""
        result = sanitize_kubectl_display_command("")
        assert result is None

    def test_whitespace_only_returns_none(self) -> None:
        """Whitespace-only input should return None."""
        result = sanitize_kubectl_display_command("   ")
        assert result is None

    def test_deployment_command_with_in_cluster_sanitized(self) -> None:
        """The specific case from the bug report."""
        result = sanitize_kubectl_display_command(
            "kubectl get deployment metrics-server -n kube-system --context in-cluster"
        )
        assert result is not None
        assert "--context" not in result
        assert "in-cluster" not in result
        assert result == "kubectl get deployment metrics-server -n kube-system"
