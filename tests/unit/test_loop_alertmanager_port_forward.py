"""Tests for loop_alertmanager_port_forward.py lifecycle cleanup."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.health.loop_alertmanager_port_forward import (
    stop_alertmanager_port_forward,
)


class TestStopAlertmanagerPortForward:
    """Tests for stop_alertmanager_port_forward lifecycle behavior."""

    @pytest.fixture
    def mock_log_event(self) -> MagicMock:
        """Create a mock log_event callback."""
        return MagicMock()

    def test_process_is_terminated_on_normal_cleanup(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """Process is terminated when it's still running during normal cleanup."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.wait.return_value = None  # Terminates gracefully

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-123",
            run_label="test-label",
            log_event=mock_log_event,
        )

        # Should call terminate first
        mock_process.terminate.assert_called_once()
        # Should NOT call kill
        mock_process.kill.assert_not_called()
        # Should wait for graceful termination
        mock_process.wait.assert_called_once_with(timeout=2)

    def test_process_is_killed_after_grace_timeout_if_terminate_does_not_exit(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """Process is killed if terminate does not exit within grace period."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        # terminate() called, but wait() raises TimeoutExpired
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 2)

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-123",
            run_label="test-label",
            log_event=mock_log_event,
        )

        # Should call terminate first
        mock_process.terminate.assert_called_once()
        # Should call kill after grace timeout
        mock_process.kill.assert_called_once()
        # Should wait after kill
        mock_process.wait.assert_called()

    def test_process_is_cleaned_up_when_already_exited(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """Process is not terminated if it has already exited."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 0  # Already exited

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-123",
            run_label="test-label",
            log_event=mock_log_event,
        )

        # Should NOT call terminate (already dead)
        mock_process.terminate.assert_not_called()
        # Should NOT call kill
        mock_process.kill.assert_not_called()

    def test_cleanup_error_is_logged_not_raised(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """Exceptions during cleanup are logged as warnings, not raised."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.terminate.side_effect = OSError("Broken pipe")
        mock_process.wait.side_effect = OSError("Broken pipe")

        # Should NOT raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-123",
            run_label="test-label",
            log_event=mock_log_event,
        )

        # Should log as warning
        mock_log_event.assert_called()
        # Check that it's logged as WARNING severity
        call_args = mock_log_event.call_args
        assert call_args[0][1] == "WARNING" or call_args[1].get("severity_reason") == "Broken pipe"

    def test_cleanup_logs_success_event(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """Successful cleanup logs a success event."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.wait.return_value = None  # Terminates gracefully

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-123",
            run_label="test-label",
            log_event=mock_log_event,
        )

        # Verify success log event
        mock_log_event.assert_called_once_with(
            "alertmanager-snapshot",
            "INFO",
            "Alertmanager port-forward stopped",
            event="alertmanager-portforward-stopped",
            run_id="test-run-123",
            run_label="test-label",
            local_port=18457,
        )

    def test_kill_required_logs_with_explicit_kill_call(
        self,
        mock_log_event: MagicMock,
    ) -> None:
        """When kill is required, verify it's called after terminate."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 2)

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run-456",
            run_label="test-label-2",
            log_event=mock_log_event,
        )

        # Both terminate and kill should be called
        assert mock_process.terminate.call_count == 1
        assert mock_process.kill.call_count == 1


class TestPortForwardSafeLogging:
    """Tests for safe logging in port-forward operations."""

    def test_safe_command_summary_used_in_failure_logging(self) -> None:
        """Verify _log_subprocess_failure uses safe command summary.

        This is a behavioral test that verifies the _log_subprocess_failure
        helper is called with command_args that will be sanitized.
        """
        from k8s_diag_agent.security.subprocess_helpers import (
            _safe_command_summary,
        )

        # Simulate a port-forward command with potentially sensitive args
        cmd = [
            "kubectl", "port-forward",
            "-n", "monitoring",
            "--context=prod-cluster",
            "svc/alertmanager",
            "18457:9093",
        ]

        summary = _safe_command_summary(cmd)

        # Context value should be redacted (it's a flag value)
        assert "prod-cluster" not in summary
        # But the command structure should be present
        assert "kubectl" in summary
        assert "port-forward" in summary
        # Flag name should be included
        assert "--context" in summary

    def test_port_forward_command_no_sensitive_args_leaked(self) -> None:
        """Port-forward commands should not leak sensitive args in summaries."""
        from k8s_diag_agent.security.subprocess_helpers import (
            _safe_command_summary,
        )

        # Command that might include kubeconfig or token
        cmd = [
            "kubectl", "port-forward",
            "-n", "monitoring",
            "--kubeconfig=/home/user/.kube/config",
            "--token=bearer-token-value",
            "svc/alertmanager",
            "18457:9093",
        ]

        summary = _safe_command_summary(cmd)

        # Sensitive values should be redacted
        assert "/home/user/.kube/config" not in summary
        assert "bearer-token-value" not in summary
        # Should have redacted markers
        assert "[REDACTED]" in summary


class TestPortForwardLifecycleBounded:
    """Tests to verify port-forward lifecycle is bounded."""

    def test_stop_has_graceful_terminate_first(self) -> None:
        """Verify stop uses terminate-first pattern."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.return_value = None

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run",
            run_label="test-label",
            log_event=MagicMock(),
        )

        # terminate must be called before any other termination methods
        assert mock_process.terminate.call_count == 1
        # kill should NOT be called if terminate succeeds
        assert mock_process.kill.call_count == 0

    def test_stop_has_force_kill_after_grace_period(self) -> None:
        """Verify stop escalates to kill if terminate doesn't succeed."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 2)

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run",
            run_label="test-label",
            log_event=MagicMock(),
        )

        # terminate must be called first
        assert mock_process.terminate.call_count == 1
        # kill must be called after grace period expires
        assert mock_process.kill.call_count == 1

    def test_stop_catches_all_cleanup_exceptions(self) -> None:
        """Verify stop swallows all exceptions during cleanup."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        # Various exceptions that might occur during cleanup
        mock_process.terminate.side_effect = OSError("Broken pipe")
        mock_process.kill.side_effect = OSError("No such process")
        mock_process.wait.side_effect = OSError("Broken pipe")

        # Should not raise
        try:
            stop_alertmanager_port_forward(
                process=mock_process,
                local_port=18457,
                run_id="test-run",
                run_label="test-label",
                log_event=MagicMock(),
            )
        except Exception as exc:
            pytest.fail(f"stop_alertmanager_port_forward raised: {exc}")

    def test_grace_timeout_is_reasonable(self) -> None:
        """Verify the grace timeout for terminate is reasonable (2 seconds)."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 2)

        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=18457,
            run_id="test-run",
            run_label="test-label",
            log_event=MagicMock(),
        )

        # Verify wait was called twice: first with timeout=2 (terminate), then without (after kill)
        assert mock_process.wait.call_count == 2
        # The first call should have timeout=2
        first_call_kwargs = mock_process.wait.call_args_list[0].kwargs
        assert first_call_kwargs.get("timeout") == 2
