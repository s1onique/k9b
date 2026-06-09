"""Regression tests for manual next-check output sanitization.

Tests verify that sensitive content (tokens, credentials, raw exceptions,
stderr/stdout) is properly sanitized before being projected to the UI.

These tests inject obvious sentinel strings and verify they do NOT appear
in sanitized output.
"""

from __future__ import annotations

import unittest


class TestSanitizeExecutionOutput(unittest.TestCase):
    """Tests for sanitize_execution_output function."""

    def test_none_inputs_return_none(self) -> None:
        """Test that None inputs return None outputs."""
        from k8s_diag_agent.security import sanitize_execution_output

        output, error = sanitize_execution_output(None, None)
        self.assertIsNone(output)
        self.assertIsNone(error)

    def test_sentinel_token_in_raw_output_is_scrubbed(self) -> None:
        """Test that KUBE_SECRET_TOKEN is scrubbed from raw output."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "kubectl get pods\nKUBE_SECRET_TOKEN_abc123=sensitive\nmore output"
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertNotIn("KUBE_SECRET_TOKEN_abc123", output)
        self.assertIn("<scrubbed>", output)

    def test_sentinel_bearer_token_in_raw_output_is_scrubbed(self) -> None:
        """Test that bearer token is scrubbed from raw output."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "Error: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\nsome error"
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertNotIn("bearer eyJ", output)
        self.assertIn("<scrubbed>", output)

    def test_sentinel_api_key_in_raw_output_is_scrubbed(self) -> None:
        """Test that api_key is scrubbed from raw output."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "Failed to call API: api_key=sk-abcdefghijk\nsome error"
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertNotIn("api_key=sk-abcdefghijk", output)
        self.assertIn("<scrubbed>", output)

    def test_sentinel_client_secret_in_error_summary_is_scrubbed(self) -> None:
        """Test that client_secret is scrubbed from error summary."""
        from k8s_diag_agent.security import sanitize_execution_output

        error_summary = "Authentication failed: client_secret=super_secret_value"
        _, sanitized_error = sanitize_execution_output(None, error_summary)
        assert sanitized_error is not None
        self.assertNotIn("client_secret=super_secret_value", sanitized_error)
        self.assertIn("<scrubbed>", sanitized_error)

    def test_sentinel_in_error_summary_is_scrubbed(self) -> None:
        """Test that KUBE_SECRET_TOKEN is scrubbed from error summary."""
        from k8s_diag_agent.security import sanitize_execution_output

        error_summary = "Command failed: KUBE_SECRET_TOKEN_abc123 leaked"
        _, sanitized_error = sanitize_execution_output(None, error_summary)
        assert sanitized_error is not None
        self.assertNotIn("KUBE_SECRET_TOKEN_abc123", sanitized_error)
        self.assertIn("<scrubbed>", sanitized_error)

    def test_long_raw_output_is_truncated(self) -> None:
        """Test that long raw output is truncated."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "x" * 1000
        output, _ = sanitize_execution_output(raw_output, None, max_output_length=100)
        assert output is not None
        self.assertLessEqual(len(output), 100)

    def test_safe_content_preserved(self) -> None:
        """Test that safe content is preserved after sanitization."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "kubectl get pods\nName: nginx\nStatus: Running\n"
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertIn("kubectl get pods", output)
        self.assertIn("nginx", output)
        self.assertIn("Running", output)

    def test_multiple_sentinels_all_scrubbed(self) -> None:
        """Test that multiple sentinel patterns are all scrubbed."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = "Token: KUBE_SECRET_TOKEN_abc123\nBearer: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\nAPI: api_key=sk-abcdefghijk"
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertNotIn("KUBE_SECRET_TOKEN_abc123", output)
        self.assertNotIn("bearer eyJ", output)
        self.assertNotIn("api_key=sk-", output)

    def test_secret_manifest_is_scrubbed(self) -> None:
        """Test that Secret manifests are scrubbed entirely."""
        from k8s_diag_agent.security import sanitize_execution_output

        raw_output = """apiVersion: v1
kind: Secret
metadata:
  name: my-secret
data:
  password: c3VwZXJzZWNyZXQ=
"""
        output, _ = sanitize_execution_output(raw_output, None)
        assert output is not None
        self.assertIn("<scrubbed>", output)

    def test_safe_fields_preserved(self) -> None:
        """Test that safe diagnostic fields are preserved."""
        from k8s_diag_agent.security import sanitize_execution_output

        error_summary = "Connection refused to API server at https://example.com"
        _, sanitized_error = sanitize_execution_output(None, error_summary)
        assert sanitized_error is not None
        self.assertIn("Connection refused", sanitized_error)
        self.assertIn("example.com", sanitized_error)


class TestSanitizeExceptionMessage(unittest.TestCase):
    """Tests for sanitize_exception_message function."""

    def test_exception_type_only_for_simple_exception(self) -> None:
        """Test that simple exception returns type name only."""
        from k8s_diag_agent.security import sanitize_exception_message

        exc = ValueError("some error")
        result = sanitize_exception_message(exc)
        self.assertIn("ValueError", result)
        self.assertIn("some error", result)

    def test_exception_with_credentials_is_sanitized(self) -> None:
        """Test that exception with credentials is sanitized."""
        from k8s_diag_agent.security import sanitize_exception_message

        exc = RuntimeError("Failed to authenticate: bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        result = sanitize_exception_message(exc)
        self.assertIn("RuntimeError", result)
        self.assertNotIn("bearer eyJ", result)
        self.assertIn("<scrubbed>", result)

    def test_exception_with_token_is_sanitized(self) -> None:
        """Test that exception with token is sanitized."""
        from k8s_diag_agent.security import sanitize_exception_message

        exc = RuntimeError("Auth failed: token=KUBE_SECRET_TOKEN_abc123")
        result = sanitize_exception_message(exc)
        self.assertIn("RuntimeError", result)
        self.assertNotIn("KUBE_SECRET_TOKEN_abc123", result)
        self.assertIn("<scrubbed>", result)

    def test_long_exception_message_is_truncated(self) -> None:
        """Test that long exception message is truncated."""
        from k8s_diag_agent.security import sanitize_exception_message

        long_message = "x" * 100
        exc = RuntimeError(long_message)
        result = sanitize_exception_message(exc, max_length=80)
        # Result includes "RuntimeError: " prefix (14 chars) + truncated message
        # So max_length=80 gives us at most 80 chars for the message part
        self.assertLessEqual(len(result), 80 + len("RuntimeError: "))
        self.assertIn("RuntimeError", result)


class TestContainsSentinel(unittest.TestCase):
    """Tests for _contains_sentinel helper (imported from private sanitizer module)."""

    def test_none_returns_false(self) -> None:
        """Test that None input returns False."""
        from k8s_diag_agent.security.sanitizer import _contains_sentinel

        self.assertFalse(_contains_sentinel(None))

    def test_empty_string_returns_false(self) -> None:
        """Test that empty string returns False."""
        from k8s_diag_agent.security.sanitizer import _contains_sentinel

        self.assertFalse(_contains_sentinel(""))

    def test_sentinel_detected(self) -> None:
        """Test that sentinel patterns are detected."""
        from k8s_diag_agent.security.sanitizer import _contains_sentinel

        self.assertTrue(_contains_sentinel("token: KUBE_SECRET_TOKEN_abc123"))
        self.assertTrue(_contains_sentinel("bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"))
        self.assertTrue(_contains_sentinel("api_key=sk-abcdefghijk"))
        self.assertTrue(_contains_sentinel("client_secret=super_secret_value"))

    def test_safe_content_not_detected(self) -> None:
        """Test that safe content is not flagged."""
        from k8s_diag_agent.security.sanitizer import _contains_sentinel

        self.assertFalse(_contains_sentinel("kubectl get pods"))
        self.assertFalse(_contains_sentinel("Connection refused"))
        self.assertFalse(_contains_sentinel("Error: something went wrong"))


class TestSanitizeBeforeTruncation(unittest.TestCase):
    """Test that sanitization happens BEFORE truncation to prevent credential pattern splitting."""

    def test_sentinel_across_truncation_boundary_is_caught(self) -> None:
        """Test that a credential pattern spanning the truncation boundary is still caught."""
        from k8s_diag_agent.security import sanitize_execution_output

        # Create output where the token spans the truncation boundary
        # TOKEN_abc123 is at position 50-64, truncation at position 60 would split it
        prefix = "x" * 50
        token = "TOKEN_abc123"
        suffix = "x" * 100
        raw_output = prefix + token + suffix

        # Truncate at position 60 - this would split the token if we truncated before sanitizing
        output, _ = sanitize_execution_output(raw_output, None, max_output_length=60)
        assert output is not None
        # Token should be scrubbed even though it's positioned such that truncation would split it
        # The key point: sanitization happens on the FULL string before truncation
        self.assertNotIn("TOKEN_abc123", output)
        self.assertIn("<scrubbed>", output)


class TestProjectionLevelSanitization(unittest.TestCase):
    """Projection-level tests verifying sanitization in response payloads."""

    def test_response_payload_does_not_leak_sentinels(self) -> None:
        """Test that the response payload does not contain sentinel strings.

        This tests the actual projection behavior: rawOutput, errorSummary,
        and error fields should not contain raw sentinels.
        """
        from k8s_diag_agent.security import sanitize_exception_message, sanitize_execution_output

        # Sentinel values that should NEVER appear in output
        sentinels = [
            "KUBE_SECRET_TOKEN_abc123",
            "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "api_key=sk-abcdefghijk",
            "client_secret=super_secret_value",
        ]

        # Test raw_output projection (simulates rawOutput field)
        for sentinel in sentinels:
            raw_output = f"command output with {sentinel} embedded"
            sanitized, _ = sanitize_execution_output(raw_output, None)
            assert sanitized is not None
            self.assertNotIn(sentinel, sanitized)

        # Test error_summary projection (simulates errorSummary field)
        for sentinel in sentinels:
            error_summary = f"Command failed: {sentinel}"
            _, sanitized = sanitize_execution_output(None, error_summary)
            assert sanitized is not None
            self.assertNotIn(sentinel, sanitized)

        # Test exception projection (simulates error field in response)
        for sentinel in sentinels:
            exc = RuntimeError(f"Operation failed: {sentinel}")
            sanitized = sanitize_exception_message(exc)
            self.assertNotIn(sentinel, sanitized)
            self.assertIn("<scrubbed>", sanitized)

    def test_command_field_safety(self) -> None:
        """Test that command field content is safe.

        Note: Commands from candidates are constructed from validated tokens,
        not raw user input. The command is built from:
        - candidate description (validated kubectl commands)
        - target context (cluster context, not credentials)
        - command family (restricted to safe kubectl subcommands)

        This test verifies that even if a command contained a sentinel,
        it would be detected.
        """
        from k8s_diag_agent.security.sanitizer import _contains_sentinel

        # Safe command patterns - should not trigger sentinel detection
        safe_commands = [
            "kubectl get pods -n default",
            "kubectl describe deployment nginx",
            "kubectl logs nginx-pod",
        ]
        for cmd in safe_commands:
            self.assertFalse(_contains_sentinel(cmd))

        # Commands with sentinels should be detected
        sentinel_commands = [
            "kubectl get secret --token=KUBE_SECRET_TOKEN_abc123",
            "kubectl get pods --bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        ]
        for cmd in sentinel_commands:
            self.assertTrue(_contains_sentinel(cmd))


if __name__ == "__main__":
    unittest.main()
