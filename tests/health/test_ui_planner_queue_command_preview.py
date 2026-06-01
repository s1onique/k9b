"""Regression tests for kubectl command preview generation.

These tests verify that internal context markers like "in-cluster"
do not leak into operator-facing command proposals.
"""

from k8s_diag_agent.health.ui_planner_queue import _build_command_preview


class TestBuildCommandPreview:
    """Regression tests for _build_command_preview function."""

    def test_in_cluster_context_not_in_preview(self) -> None:
        """Internal 'in-cluster' context must not appear in command preview."""
        preview = _build_command_preview(
            "kubectl get pods -n monitoring",
            target_context="in-cluster"
        )
        assert preview is not None
        assert "--context" not in preview
        assert "in-cluster" not in preview

    def test_in_cluster_underscore_context_not_in_preview(self) -> None:
        """Internal 'in_cluster' context must not appear in command preview."""
        preview = _build_command_preview(
            "kubectl get pods -n monitoring",
            target_context="in_cluster"
        )
        assert preview is not None
        assert "--context" not in preview
        assert "in_cluster" not in preview

    def test_none_context_not_in_preview(self) -> None:
        """None context must not add --context flag."""
        preview = _build_command_preview(
            "kubectl get pods -n monitoring",
            target_context=None
        )
        assert preview is not None
        assert "--context" not in preview

    def test_empty_context_not_in_preview(self) -> None:
        """Empty string context must not add --context flag."""
        preview = _build_command_preview(
            "kubectl get pods -n monitoring",
            target_context=""
        )
        assert preview is not None
        assert "--context" not in preview

    def test_real_context_in_preview(self) -> None:
        """Real kubeconfig context should appear with --context flag."""
        preview = _build_command_preview(
            "kubectl get pods -n monitoring",
            target_context="prod-context"
        )
        assert preview is not None
        assert "--context" in preview
        assert "prod-context" in preview

    def test_in_cluster_logs_command_preview(self) -> None:
        """In-cluster logs command should not include --context."""
        preview = _build_command_preview(
            "kubectl logs -n kube-system -l app=etcd",
            target_context="in-cluster"
        )
        assert preview is not None
        assert "--context" not in preview
        assert "in-cluster" not in preview
        assert "-n kube-system" in preview

    def test_real_context_describe_command_preview(self) -> None:
        """Real context describe command should include --context."""
        preview = _build_command_preview(
            "kubectl describe pod -n monitoring alertmanager-0",
            target_context="admin@prod"
        )
        assert preview is not None
        assert "--context" in preview
        assert "admin@prod" in preview

    def test_description_without_kubectl_prefix(self) -> None:
        """Description without kubectl prefix should still work."""
        preview = _build_command_preview(
            "get pods -n default",
            target_context="prod-cluster"
        )
        assert preview is not None
        assert "--context" in preview
        assert "prod-cluster" in preview

    def test_description_without_kubectl_and_in_cluster(self) -> None:
        """Description without kubectl prefix and in-cluster should not leak context."""
        preview = _build_command_preview(
            "get pods -n default",
            target_context="in-cluster"
        )
        assert preview is not None
        assert "--context" not in preview
        assert "in-cluster" not in preview
