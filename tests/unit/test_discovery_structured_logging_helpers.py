"""Tests for structured logging helper utilities.

These tests verify that the test helper utilities for validating structured
log output work correctly, and that discovery structured logging fallback
exception handling is safe.

See: Child Epic CI Verification - Gate health-loop logs as structured JSON
See: ACT: Harden discovery structured logging fallback exception handling
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestStructuredLogAssertionHelpers:
    """Verify the test helpers work correctly."""

    def test_parse_log_lines_extracts_json(self):
        """Test that parse_log_lines correctly extracts JSON from mixed output."""
        from tests.helpers.test_structured_log_assertions import parse_log_lines

        output = '''
Some debug output
{"timestamp": "2024-01-01T00:00:00Z", "component": "test", "severity": "INFO", "message": "hello", "event": "test-event"}
Some more text
{"timestamp": "2024-01-01T00:00:01Z", "component": "test", "severity": "WARNING", "message": "world", "event": "test-warn"}
'''
        records = parse_log_lines(output)
        assert len(records) == 2
        assert records[0]["message"] == "hello"
        assert records[1]["message"] == "world"

    def test_assert_no_raw_forbidden_errors_passes_on_structured(self):
        """Test that assertion passes when Forbidden is in JSON."""
        from tests.helpers.test_structured_log_assertions import (
            assert_no_raw_forbidden_errors,
        )

        # Structured output with Forbidden in JSON is OK
        captured_out = '{"message": "Forbidden: kubectl failed"}'
        captured_err = ""

        # Should not raise
        assert_no_raw_forbidden_errors(captured_out, captured_err)

    def test_assert_no_raw_forbidden_errors_fails_on_raw(self):
        """Test that assertion fails when Forbidden is raw text."""
        from tests.helpers.test_structured_log_assertions import (
            assert_no_raw_forbidden_errors,
        )

        # Raw output with Forbidden is NOT OK
        captured_out = "Error from server (Forbidden): cannot list"
        captured_err = ""

        with pytest.raises(AssertionError, match="raw Forbidden error"):
            assert_no_raw_forbidden_errors(captured_out, captured_err)

    def test_assert_all_log_lines_are_structured_passes(self):
        """Test that assertion passes for valid structured output."""
        from tests.helpers.test_structured_log_assertions import (
            assert_all_log_lines_are_structured,
        )

        captured_out = json.dumps({
            "timestamp": "2024-01-01T00:00:00Z",
            "component": "test",
            "severity": "WARNING",
            "message": "test",
            "event": "test-event",
        })
        captured_err = ""

        records = assert_all_log_lines_are_structured(captured_out, captured_err)
        assert len(records) == 1
        assert records[0]["severity"] == "WARNING"

    def test_assert_all_log_lines_are_structured_fails_on_raw(self):
        """Test that assertion fails for unstructured output."""
        from tests.helpers.test_structured_log_assertions import (
            assert_all_log_lines_are_structured,
        )

        captured_out = "Some raw log output"
        captured_err = ""

        with pytest.raises(AssertionError, match="unstructured log line"):
            assert_all_log_lines_are_structured(captured_out, captured_err)


class TestSafeEmitDiscoveryFailure:
    """Regression tests for safe discovery structured logging fallback.

    Verifies that when structured emitter raises with a sensitive message,
    the captured logs do NOT contain forbidden/kubectl/cluster error text.

    See: ACT: Harden discovery structured logging fallback exception handling
    """

    def test_emit_discovery_event_suppresses_emitter_exception_without_raw_message(
        self, caplog
    ):
        """Structured emitter exceptions should be suppressed without leaking exception text."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the emit function to raise with a sensitive message
        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(
                "Error from server (Forbidden): users 'system:serviceaccount:...' "
                "cannot list resource 'alertmanagers'"
            )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            # Should not raise
            emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-strategy",
                errors=("Forbidden error",),
            )

        # Check that no sensitive text appears in any log
        for record in caplog.records:
            assert "Forbidden" not in record.message, (
                f"Found raw Forbidden error in fallback log: {record.message}"
            )
            assert "system:serviceaccount" not in record.message, (
                f"Found serviceaccount in fallback log: {record.message}"
            )
            assert "cannot list resource" not in record.message, (
                f"Found kubectl error in fallback log: {record.message}"
            )

    def test_emit_discovery_event_does_not_log_forbidden_exception_text(
        self, caplog
    ):
        """When emitter raises, the exception text should not be logged anywhere."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the emit function to raise with forbidden kubectl error
        sensitive_error = (
            "Error from server (Forbidden): "
            "users \"system:serviceaccount:kube-system:...\" "
            "cannot list resource ... in API group \"monitoring.coreos.com\""
        )

        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(sensitive_error)

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            emit_discovery_strategy_failure(
                component="alertmanager-discovery",
                strategy_name="alertmanager-crd",
                errors=(f"kubectl failed: Forbidden - {sensitive_error[:200]}",),
            )

        # Verify no raw forbidden text in any captured log
        log_text = "\n".join(r.message for r in caplog.records)
        assert "Forbidden" not in log_text, (
            f"Found Forbidden in fallback logs: {log_text}"
        )
        assert "system:serviceaccount" not in log_text
        assert "cannot list resource" not in log_text

    def test_safe_emit_discovery_failure_wraps_inner_failure(
        self, caplog
    ):
        """safe_emit_discovery_failure should wrap emit_discovery_strategy_failure safely."""
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            safe_emit_discovery_failure,
        )

        caplog.set_level(logging.DEBUG)

        # Mock the inner emit function to raise with a sensitive message
        def mock_emit_with_sensitive(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError(
                "Error from server (Forbidden): cannot list resource 'vmalerts'"
            )

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_sensitive,
        ):
            # Should not raise
            safe_emit_discovery_failure(
                component="vmalert-discovery",
                strategy_name="vmalert-crd",
                errors=("kubectl failed: Forbidden - Error from server (Forbidden): ...",),
            )

        # Verify no sensitive text in logs
        for record in caplog.records:
            assert "Forbidden" not in record.message
            assert "cannot list resource" not in record.message

    def test_emit_discovery_event_failure_preserves_discovery_result_flow(
        self, caplog
    ):
        """Emitter failure should not prevent the caller from continuing.

        This test verifies that when structured logging fails, the discovery
        result (error tuple) is still accessible to the caller.
        """
        from k8s_diag_agent.external_analysis.discovery_structured_logging import (
            emit_discovery_strategy_failure,
        )

        caplog.set_level(logging.WARNING)

        # Track calls to verify the function completes
        call_completed = False

        def mock_emit_with_error(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Structured logging service unavailable")

        with patch(
            "k8s_diag_agent.external_analysis.discovery_structured_logging._get_emit_fn",
            return_value=mock_emit_with_error,
        ):
            # Should complete without raising
            emit_discovery_strategy_failure(
                component="test-discovery",
                strategy_name="test-crd",
                errors=("kubectl failed: Some error",),
            )
            call_completed = True

        assert call_completed, "emit_discovery_strategy_failure should complete without raising"

        # Verify no sensitive text leaked
        log_text = "\n".join(r.message for r in caplog.records)
        assert "Some error" not in log_text, (
            f"Found 'Some error' in fallback logs: {log_text}"
        )
        assert "kubectl failed" not in log_text, (
            f"Found 'kubectl failed' in fallback logs: {log_text}"
        )


class TestServiceStrategyNoRawLogs:
    """Regression tests verifying service strategies don't emit raw kubectl errors.

    These tests verify that when service heuristic strategies fail,
    they do not log raw error text containing forbidden/kubectl details.
    """

    def test_alertmanager_service_strategy_no_raw_forbidden_on_failure(
        self, caplog
    ):
        """Alertmanager service strategy should not log raw Forbidden text on failure."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_service_strategy import (
            ServiceHeuristicDiscoveryStrategy,
        )

        caplog.set_level(logging.WARNING)

        strategy = ServiceHeuristicDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = (
            "Error from server (Forbidden): services is forbidden: "
            "cannot list resource 'services' in API group '' in the namespace 'default'"
        )

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is captured in result
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]

        # Verify no raw Forbidden text in logs
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                assert "Error from server (Forbidden):" not in record.message
                assert "system:serviceaccount" not in record.message

    def test_vmalert_service_strategy_no_raw_forbidden_on_failure(self, caplog):
        """VMAlert service strategy should not log raw Forbidden text on failure."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_service_strategy import (
            ServiceHeuristicDiscoveryStrategy,
        )

        caplog.set_level(logging.WARNING)

        strategy = ServiceHeuristicDiscoveryStrategy()

        # Mock subprocess to return a Forbidden error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = (
            "Error from server (Forbidden): services is forbidden: "
            "cannot list resource 'services' in API group ''"
        )

        with patch("subprocess.run", return_value=mock_result):
            result = strategy.discover(context="test-context")

        # Verify error is captured in result
        assert len(result.errors) == 1
        assert "Forbidden" in result.errors[0]

        # Verify no raw Forbidden text in logs
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                assert "Error from server (Forbidden):" not in record.message
                assert "cannot list resource" not in record.message
