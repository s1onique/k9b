"""Tests for trace_http_request when tracing is enabled (with mocks).

Tests that the wrapper creates proper spans with bounded attributes
when OpenTelemetry is available and enabled.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.observability.http_spans import (
    trace_http_request,
    trace_http_request_with_status,
)


@pytest.fixture(autouse=True)
def mock_otel_tracing() -> Generator[MagicMock, None, None]:
    """Mock OTel tracing to test enabled path without live collector."""
    # Create mock tracer and span
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)

    mock_tracer = MagicMock()
    mock_tracer.start_as_current_span.return_value = mock_span

    with patch(
        "k8s_diag_agent.observability.http_spans._get_tracer",
        return_value=mock_tracer,
    ), patch(
        "k8s_diag_agent.observability.http_spans._is_tracing_enabled",
        return_value=True,
    ):
        yield mock_span


class TestTraceHttpRequestEnabled:
    """Tests for trace_http_request when tracing is enabled."""

    def test_span_name_uses_normalized_route(
        self,
        mock_otel_tracing: MagicMock,
    ) -> None:
        """Span name should use normalized route, not raw path."""
        mock_span = mock_otel_tracing

        def handler() -> str:
            return "response"

        trace_http_request(
            method="GET",
            path="/api/incidents/abc-123",
            handler_name="get_incident",
            call=handler,
        )

        # Verify span was created with normalized route as name
        mock_span.set_attribute.assert_called()
        # Check that span name contains normalized route
        calls = mock_span.set_attribute.call_args_list
        route_call = next(
            (c for c in calls if c[0][0] == "k9b.api.route"),
            None,
        )
        assert route_call is not None
        assert route_call[0][1] == "GET /api/incidents/{incident_id}"

    def test_bounded_attributes_are_set(
        self,
        mock_otel_tracing: MagicMock,
    ) -> None:
        """Bounded attributes should be set on the span."""
        mock_span = mock_otel_tracing

        def handler() -> str:
            return "response"

        trace_http_request(
            method="POST",
            path="/api/incidents/xyz-456/diagnosis-loop/one-pass",
            handler_name="one_pass_diagnosis",
            call=handler,
        )

        # Verify all bounded attributes are set
        attribute_names = {c[0][0] for c in mock_span.set_attribute.call_args_list}

        assert "k9b.api.method" in attribute_names
        assert "k9b.api.route" in attribute_names
        assert "k9b.api.handler" in attribute_names
        assert "k9b.api.route_known" in attribute_names
        assert "http.request.method" in attribute_names

        # Get specific values
        method_call = next(
            c for c in mock_span.set_attribute.call_args_list
            if c[0][0] == "k9b.api.method"
        )
        assert method_call[0][1] == "POST"

        handler_call = next(
            c for c in mock_span.set_attribute.call_args_list
            if c[0][0] == "k9b.api.handler"
        )
        assert handler_call[0][1] == "one_pass_diagnosis"

        route_known_call = next(
            c for c in mock_span.set_attribute.call_args_list
            if c[0][0] == "k9b.api.route_known"
        )
        assert route_known_call[0][1] is True

    def test_exception_is_recorded(
        self,
        mock_otel_tracing: MagicMock,
    ) -> None:
        """Exceptions should be recorded on the span and re-raised."""
        mock_span = mock_otel_tracing

        def handler() -> None:
            raise RuntimeError("handler failed")

        with pytest.raises(RuntimeError, match="handler failed"):
            trace_http_request(
                method="GET",
                path="/api/incidents/inc-999",
                handler_name="get_incident",
                call=handler,
            )

        # Verify exception was recorded
        mock_span.record_exception.assert_called_once()
        # Verify error status was set per OTel semantic conventions
        mock_span.set_status.assert_called_once()
        status_args = mock_span.set_status.call_args[0]
        assert status_args[0] == "ERROR"
        assert "handler failed" in status_args[1]
        # Verify status code was set to 500
        status_call = next(
            (c for c in mock_span.set_attribute.call_args_list
             if c[0][0] == "k9b.http.status_code"),
            None,
        )
        assert status_call is not None
        assert status_call[0][1] == 500

    def test_raw_incident_id_not_in_span_name(
        self,
        mock_otel_tracing: MagicMock,
    ) -> None:
        """Raw incident ID should NOT appear in any span attribute."""
        mock_span = mock_otel_tracing

        def handler() -> str:
            return "response"

        trace_http_request(
            method="GET",
            path="/api/incidents/private-incident-12345",
            handler_name="get_incident",
            call=handler,
        )

        # Check all set_attribute calls for raw ID
        for call in mock_span.set_attribute.call_args_list:
            value = str(call[0][1])
            assert "private-incident-12345" not in value, (
                f"Raw incident ID found in attribute {call[0][0]}: {value}"
            )


class TestTraceHttpRequestWithStatusEnabled:
    """Tests for trace_http_request_with_status when tracing is enabled."""

    def test_status_code_recorded_on_span(
        self,
        mock_otel_tracing: MagicMock,
    ) -> None:
        """HTTP status code should be recorded on the span."""
        mock_span = mock_otel_tracing

        def handler() -> int:
            return 201

        result = trace_http_request_with_status(
            method="POST",
            path="/api/incidents",
            handler_name="create_incident",
            call=handler,
        )

        assert result == 201

        # Verify status code attributes
        http_status_call = next(
            (c for c in mock_span.set_attribute.call_args_list
             if c[0][0] == "http.response.status_code"),
            None,
        )
        assert http_status_call is not None
        assert http_status_call[0][1] == 201

        k9b_status_call = next(
            (c for c in mock_span.set_attribute.call_args_list
             if c[0][0] == "k9b.http.status_code"),
            None,
        )
        assert k9b_status_call is not None
        assert k9b_status_call[0][1] == 201
