"""Tests for structured logging helper utilities.

These tests verify that the test helper utilities for validating structured
log output work correctly.

See: Child Epic CI Verification - Gate health-loop logs as structured JSON
"""

from __future__ import annotations

import json

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
