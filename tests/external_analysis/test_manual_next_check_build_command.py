"""Regression tests for manual_next_check._build_command.

These tests verify that internal context markers like "in-cluster"
do not leak into executed kubectl commands.
"""

import pytest

from k8s_diag_agent.external_analysis.manual_next_check import ManualNextCheckError, _build_command
from k8s_diag_agent.external_analysis.next_check_planner import CommandFamily


class TestBuildCommandContextFiltering:
    """Regression tests for _build_command context handling."""

    def test_in_cluster_context_not_in_command(self) -> None:
        """Internal 'in-cluster' context must not appear in executed command."""
        command = _build_command(
            description="kubectl get pods -n monitoring",
            target_context="in-cluster",
            family=CommandFamily.KUBECTL_GET
        )
        assert command[0] == "kubectl"
        assert "--context" not in command
        assert "in-cluster" not in command

    def test_in_cluster_underscore_not_in_command(self) -> None:
        """Internal 'in_cluster' context must not appear in executed command."""
        command = _build_command(
            description="kubectl describe pod -n kube-system etcd-0",
            target_context="in_cluster",
            family=CommandFamily.KUBECTL_DESCRIBE
        )
        assert "--context" not in command
        assert "in_cluster" not in command

    def test_none_context_not_in_command(self) -> None:
        """None context must not add --context flag."""
        # Note: This will fail validation at the context level since None is invalid
        with pytest.raises(ManualNextCheckError, match="Invalid kubectl context"):
            _build_command(
                description="kubectl get pods",
                target_context="",  # Empty string triggers validation failure
                family=CommandFamily.KUBECTL_GET
            )

    def test_real_context_in_command(self) -> None:
        """Real kubeconfig context should appear with --context flag."""
        command = _build_command(
            description="kubectl get pods -n monitoring",
            target_context="prod-context",
            family=CommandFamily.KUBECTL_GET
        )
        assert "--context" in command
        assert "prod-context" in command
        # Context should be right after kubectl
        assert command.index("--context") == command.index("prod-context") - 1

    def test_in_cluster_logs_command(self) -> None:
        """In-cluster logs command should not include --context."""
        command = _build_command(
            description="kubectl logs -n kube-system -l app=etcd",
            target_context="in-cluster",
            family=CommandFamily.KUBECTL_LOGS
        )
        assert "--context" not in command
        assert "in-cluster" not in command
        assert "-n" in command
        assert "kube-system" in command

    def test_real_context_with_logs(self) -> None:
        """Real context with logs should include --context."""
        command = _build_command(
            description="kubectl logs -n monitoring alertmanager-0",
            target_context="admin@prod",
            family=CommandFamily.KUBECTL_LOGS
        )
        assert "--context" in command
        assert "admin@prod" in command

    def test_existing_context_in_description_stripped(self) -> None:
        """Existing --context in description should be stripped."""
        command = _build_command(
            description="kubectl get pods --context old-context -n monitoring",
            target_context="prod-context",
            family=CommandFamily.KUBECTL_GET
        )
        assert "old-context" not in command
        assert "--context" in command
        assert "prod-context" in command
        # Only one --context should exist
        assert command.count("--context") == 1


class TestBuildCommandNamespaceValidation:
    """Tests for namespace validation to prevent -n in-cluster leakage."""

    def test_in_cluster_namespace_passes_validation_but_no_context(self) -> None:
        """Namespace 'in-cluster' is valid (DNS label) but must not get --context in-cluster.

        Note: 'in-cluster' is a valid Kubernetes namespace name per DNS label rules.
        The fix ensures '--context in-cluster' is NOT added to commands.
        The namespace in the command description is preserved as-is.
        """
        command = _build_command(
            description="kubectl get pods -n in-cluster",
            target_context="in-cluster",
            family=CommandFamily.KUBECTL_GET
        )
        # Namespace 'in-cluster' passes validation (valid DNS label)
        assert "in-cluster" in command
        # But --context in-cluster must NOT be added
        assert "--context" not in command
        assert command.count("--context") == 0

    def test_in_cluster_underscore_namespace_rejected(self) -> None:
        """Namespace 'in_cluster' should be rejected as invalid."""
        with pytest.raises(ManualNextCheckError, match="invalid namespace"):
            _build_command(
                description="kubectl get pods -n in_cluster",
                target_context="prod-context",
                family=CommandFamily.KUBECTL_GET
            )

    def test_valid_namespace_accepted(self) -> None:
        """Valid namespace should be accepted."""
        command = _build_command(
            description="kubectl get pods -n monitoring",
            target_context="prod-context",
            family=CommandFamily.KUBECTL_GET
        )
        assert "-n" in command
        assert "monitoring" in command