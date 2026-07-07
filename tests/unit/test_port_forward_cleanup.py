"""Tests for port-forward cleanup boundary in loop_alertmanager_port_forward.py.

Tests cover:
- Normal successful cleanup behavior
- Cleanup handles OSError gracefully
- Cleanup handles subprocess.SubprocessError gracefully
- Cleanup handles TimeoutError gracefully
- No credential/secret/path leakage in logs during cleanup errors
- Cleanup never propagates exceptions to caller (final containment)
"""
import subprocess
import unittest
from unittest.mock import MagicMock


def _recursive_check_for_secrets(obj: object, secret_keywords: list[str]) -> list[str]:
    """Recursively check an object for secret keywords in strings."""
    found_secrets: list[str] = []
    if isinstance(obj, str):
        lower = obj.lower()
        for keyword in secret_keywords:
            if keyword in lower:
                found_secrets.append(f"Found '{keyword}' in string: {obj[:100]}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            found_secrets.extend(_recursive_check_for_secrets(key, secret_keywords))
            found_secrets.extend(_recursive_check_for_secrets(value, secret_keywords))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found_secrets.extend(_recursive_check_for_secrets(item, secret_keywords))
    return found_secrets


class TestStopAlertmanagerPortForward(unittest.TestCase):
    """Tests for stop_alertmanager_port_forward cleanup boundary."""

    # Secret keywords to check for - no secrets should appear in logs
    SECRET_KEYWORDS = ["secret", "password", "token", "bearer", "/var/run/secrets"]

    def _make_mock_process(self, poll_result: int | None = None) -> MagicMock:
        """Create a mock Popen process.
        
        Note: We don't use spec=subprocess.Popen because the guard fixture
        in conftest_kubectl_guard.py patches subprocess.Popen with a blocking
        function during test execution. Instead, we manually set the required
        methods that stop_alertmanager_port_forward uses: poll, terminate,
        wait, kill.
        """
        mock = MagicMock()
        mock.poll.return_value = poll_result
        mock.terminate = MagicMock()
        mock.wait = MagicMock()
        mock.kill = MagicMock()
        return mock

    def _make_log_event(self) -> tuple[list, MagicMock]:
        """Create a capturing mock log_event function."""
        logs: list = []
        mock_log = MagicMock(side_effect=lambda *args, **kwargs: logs.append((args, kwargs)))
        return logs, mock_log

    def test_normal_cleanup_with_running_process(self) -> None:
        """Normal cleanup of a running process completes without errors."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=2)

    def test_normal_cleanup_with_already_stopped_process(self) -> None:
        """Cleanup of an already-stopped process completes without errors."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=0)
        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # terminate should not be called for already-stopped process
        mock_process.terminate.assert_not_called()

    def test_oserror_during_terminate_is_caught(self) -> None:
        """OSError during process terminate is caught and logged as warning."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate.side_effect = OSError("Broken pipe")
        mock_process.kill.side_effect = OSError("Broken pipe")
        mock_process.wait.side_effect = OSError("Broken pipe")

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # Should log a warning with error_type containing the exception type name
        self.assertEqual(len(logs), 1)
        _, kwargs = logs[0]
        self.assertEqual(kwargs.get("error_type"), "OSError")
        self.assertIn("cleanup-error", kwargs.get("reason", ""))

    def test_subprocess_timeout_error_during_wait_is_caught(self) -> None:
        """subprocess.TimeoutExpired during wait is caught and logged as warning."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate = MagicMock()
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=2)

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # Should log a warning (timeout triggers kill, then wait)
        self.assertEqual(len(logs), 1)
        _, kwargs = logs[0]
        self.assertIn(kwargs.get("reason"), "cleanup-error")

    def test_kill_and_wait_timeout_error_is_caught(self) -> None:
        """TimeoutExpired during kill fallback is caught and logged as warning."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=2)
        mock_process.kill.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=2)
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=2)

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # Should log a warning
        self.assertEqual(len(logs), 1)

    def test_no_credentials_in_log_output(self) -> None:
        """Cleanup error logs do not contain credentials or secrets."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate.side_effect = OSError("Permission denied: /var/run/secrets/kubernetes.io")

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run-123",
            run_label="test-label-prod",
            log_event=log_event,
        )

        # Check no secrets leaked - recursively check all args and kwargs
        for log_entry in logs:
            args, kwargs = log_entry
            # Check positional args
            for arg in args:
                found = _recursive_check_for_secrets(arg, self.SECRET_KEYWORDS)
                self.assertEqual(found, [], f"Secrets found in positional args: {found}")
            # Check kwargs keys and values
            for key, value in kwargs.items():
                found = _recursive_check_for_secrets(key, self.SECRET_KEYWORDS)
                self.assertEqual(found, [], f"Secrets found in kwarg keys: {found}")
                found = _recursive_check_for_secrets(value, self.SECRET_KEYWORDS)
                self.assertEqual(found, [], f"Secrets found in kwarg '{key}': {found}")

    def test_error_type_is_exception_class_name_not_raw_text(self) -> None:
        """Verify error_type contains only the exception class name, not raw exception text."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate.side_effect = OSError("This is a very long error message with sensitive info: API_KEY=abc123")

        logs, log_event = self._make_log_event()

        # Should not raise
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # Check that error_type is just the class name
        _, kwargs = logs[0]
        self.assertEqual(kwargs.get("error_type"), "OSError")
        # The raw error message should NOT appear in any logged field
        for key, value in kwargs.items():
            if isinstance(value, str):
                self.assertNotIn("API_KEY", value)
                self.assertNotIn("abc123", value)

    def test_cleanup_exceptions_never_propagate(self) -> None:
        """Cleanup exceptions never propagate to caller - final containment."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate.side_effect = Exception("Unexpected error")

        logs, log_event = self._make_log_event()

        # Should NOT raise - the final broad catch should contain it
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # Should log a warning
        self.assertEqual(len(logs), 1)
        _, kwargs = logs[0]
        self.assertEqual(kwargs.get("error_type"), "Exception")
        self.assertIn("cleanup-error", kwargs.get("reason", ""))

    def test_cleanup_behavior_preserved_after_fix(self) -> None:
        """Verify that cleanup behavior is preserved - terminate timeout triggers kill."""
        from k8s_diag_agent.health.loop_alertmanager_port_forward import (
            stop_alertmanager_port_forward,
        )

        # Test with a process where wait() times out (so kill is called)
        mock_process = self._make_mock_process(poll_result=None)
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()
        # wait() raises TimeoutExpired, triggering kill
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=2)
        mock_process.kill = MagicMock()

        logs, log_event = self._make_log_event()

        # Should complete without raising
        stop_alertmanager_port_forward(
            process=mock_process,
            local_port=8080,
            run_id="test-run",
            run_label="test-label",
            log_event=log_event,
        )

        # kill should be called when wait times out
        mock_process.kill.assert_called_once()
        mock_process.wait.assert_called()


if __name__ == "__main__":
    unittest.main()
