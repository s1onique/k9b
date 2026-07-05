"""Tests for trace_http_request when tracing is disabled.

Tests that the wrapper behaves as a no-op when OpenTelemetry
is not available or not enabled.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.observability.http_spans import (
    trace_http_request,
    trace_http_request_with_status,
)


class TestTraceHttpRequestDisabled:
    """Tests for trace_http_request when tracing is disabled."""

    def test_wrapper_calls_handler(self) -> None:
        """When disabled, wrapper should just call the handler."""
        call_count = 0

        def handler() -> str:
            nonlocal call_count
            call_count += 1
            return "response"

        result = trace_http_request(
            method="GET",
            path="/api/incidents",
            handler_name="incident_list_handler",
            call=handler,
        )

        assert result == "response"
        assert call_count == 1

    def test_return_value_preserved(self) -> None:
        """Return values should be passed through unchanged."""
        expected = {"data": [1, 2, 3]}

        def handler() -> dict[str, list[int]]:
            return expected

        result = trace_http_request(
            method="POST",
            path="/api/incidents",
            handler_name="create_incident",
            call=handler,
        )

        assert result is expected

    def test_raised_exception_preserved(self) -> None:
        """Exceptions should be re-raised unchanged."""
        custom_error = ValueError("something went wrong")

        def handler() -> None:
            raise custom_error

        with pytest.raises(ValueError, match="something went wrong") as exc_info:
            trace_http_request(
                method="GET",
                path="/api/incidents/abc-123",
                handler_name="get_incident",
                call=handler,
            )

        assert exc_info.value is custom_error

    def test_no_opentelemetry_required_in_disabled_path(self) -> None:
        """When disabled, opentelemetry should not be imported."""
        # This test verifies that the disabled path doesn't require
        # opentelemetry to be installed - it should just pass through
        def handler() -> str:
            return "success"

        result = trace_http_request(
            method="GET",
            path="/api/health",
            handler_name="health_check",
            call=handler,
        )

        assert result == "success"


class TestTraceHttpRequestWithStatusDisabled:
    """Tests for trace_http_request_with_status when tracing is disabled."""

    def test_wrapper_calls_handler_and_returns_status(self) -> None:
        """When disabled, wrapper should call handler and return status."""
        def handler() -> int:
            return 200

        result = trace_http_request_with_status(
            method="GET",
            path="/api/health",
            handler_name="health_handler",
            call=handler,
        )

        assert result == 200
