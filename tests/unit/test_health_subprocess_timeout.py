"""Tests for subprocess timeout behavior in health module command runners.

These tests verify that KubectlExecutionError (from run_kubectl) is properly
converted to RuntimeError with safe error messages.

Architecture note:
    After ACT-K9B-K8S-CLIENT-TEST-HARNESS-UPDATE01:
    - image_pull_secret uses Kubernetes Python client (no _run_command)
    - drilldown uses run_kubectl which returns KubectlExecutionError
    - KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS is 30 (not 60)
"""
from __future__ import annotations

from unittest import mock

import pytest

from k8s_diag_agent.health import drilldown, image_pull_secret
from k8s_diag_agent.security.kubectl_errors import KubectlExecutionError


class TestDrilldownRunCommandTimeout:
    """Tests for _run_command timeout handling in drilldown module.

    These tests patch drilldown.run_kubectl since drilldown._run_command
    delegates to run_kubectl for bounded execution.
    """

    def test_run_command_timeout_raises_runtime_error(self) -> None:
        """Verify KubectlExecutionError (timeout) is converted to RuntimeError with safe message."""
        with mock.patch(
            "k8s_diag_agent.health.drilldown.run_kubectl",
            side_effect=KubectlExecutionError(
                "`kubectl` timed out after 30s. Cluster may be unresponsive or under load.",
                command=["kubectl", "get", "pods", "--all-namespaces"],
                elapsed_seconds=30.0,
            ),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                drilldown._run_command(["kubectl", "get", "pods", "--all-namespaces"])
            # Message should include command family but not full args
            assert "kubectl" in str(exc_info.value)
            assert "timed out" in str(exc_info.value)
            assert "30s" in str(exc_info.value)

    def test_run_command_timeout_message_safe(self) -> None:
        """Verify timeout message does not leak sensitive args."""
        with mock.patch(
            "k8s_diag_agent.health.drilldown.run_kubectl",
            side_effect=KubectlExecutionError(
                "`kubectl` timed out after 30s. Cluster may be unresponsive or under load.",
                command=["kubectl", "describe", "pods", "--token=secret-bearer", "--context=staging"],
                elapsed_seconds=30.0,
            ),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                drilldown._run_command(["kubectl", "describe", "pods"])
            error_msg = str(exc_info.value)
            assert "kubectl" in error_msg
            assert "timed out" in error_msg
            assert "secret-bearer" not in error_msg


class TestTimeoutConstants:
    """Tests for timeout constant values."""

    def test_kubectl_health_command_timeout_value(self) -> None:
        """Verify KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS is 30."""
        assert image_pull_secret.KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS == 30

    def test_drilldown_imports_timeout_constant(self) -> None:
        """Verify drilldown module imports the constant correctly."""
        # This is an integration check - if import works, the constant is accessible
        from k8s_diag_agent.health.drilldown import KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS
        assert KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS == 30

    def test_timeout_constant_exported(self) -> None:
        """Verify constants are accessible from the module."""
        from k8s_diag_agent.health.image_pull_secret import (
            KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS,
        )
        assert isinstance(KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS, int)
        assert KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS > 0
