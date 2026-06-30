"""Tests for OTel graceful degradation and noop behavior.

These tests verify that:
1. OTel helpers degrade gracefully when OTel is unavailable
2. Telemetry failures do not affect diagnosis loop behavior
3. Import safety is maintained
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    SpanContext,
    record_exception,
    set_span_error,
    set_span_ok,
    start_span,
)


class TestOTelGracefulDegradation:
    """Tests for graceful degradation when OTel is unavailable."""

    def test_start_span_returns_span_context_when_no_tracer(self) -> None:
        """start_span returns a valid SpanContext even without tracer."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_span("test.span", {"key": "value"})
            assert isinstance(ctx, SpanContext)
            assert ctx.name == "test.span"
            assert ctx.active_span is None
            assert ctx.span is None  # Backward-compatible property

    def test_record_exception_does_not_raise_without_span(self) -> None:
        """record_exception does not raise when span is None."""
        record_exception(None, ValueError("test error"))

    def test_set_span_ok_does_not_raise_without_span(self) -> None:
        """set_span_ok does not raise when span is None."""
        set_span_ok(None)

    def test_set_span_error_does_not_raise_without_span(self) -> None:
        """set_span_error does not raise when span is None."""
        set_span_error(None)

    def test_set_span_ok_uses_status_object_with_mock_span(self) -> None:
        """set_span_ok calls set_status with Status object on Mock spans."""
        from unittest.mock import Mock

        from opentelemetry.trace import StatusCode

        span = Mock()

        set_span_ok(span)

        span.set_status.assert_called_once()
        status = span.set_status.call_args.args[0]
        assert status.status_code == StatusCode.OK

    def test_set_span_error_uses_status_object_with_mock_span(self) -> None:
        """set_span_error calls set_status with Status object on Mock spans."""
        from unittest.mock import Mock

        from opentelemetry.trace import StatusCode

        span = Mock()

        set_span_error(span)

        span.set_status.assert_called_once()
        status = span.set_status.call_args.args[0]
        assert status.status_code == StatusCode.ERROR


class TestTelemetryFailureDoesNotBreakRuntime:
    """Tests that telemetry failures do not affect diagnosis loop behavior."""

    def test_telemetry_error_does_not_propagate(self) -> None:
        """OTel errors do not propagate to caller."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_span("test.span", {"key": "value"})
            assert ctx.active_span is None
            assert ctx.span is None

    def test_set_attribute_error_does_not_propagate(self) -> None:
        """Span.set_attribute errors do not propagate."""
        mock_span = MagicMock()
        mock_span.set_attribute.side_effect = RuntimeError("Attribute error")
        
        # Should not raise
        set_span_ok(mock_span)

    def test_set_status_error_does_not_propagate(self) -> None:
        """Span.set_status errors do not propagate."""
        mock_span = MagicMock()
        mock_span.set_status.side_effect = RuntimeError("Status error")
        
        # Should not raise
        set_span_ok(mock_span)

    def test_record_exception_error_does_not_propagate(self) -> None:
        """Span.record_exception errors do not propagate."""
        mock_span = MagicMock()
        mock_span.record_exception.side_effect = RuntimeError("Record error")
        
        # Should not raise
        record_exception(mock_span, ValueError("test"))


class TestExceptionRecording:
    """Tests for exception recording."""

    def test_record_exception_sets_error_status(self) -> None:
        """record_exception records exception and sets error status."""
        mock_span = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_span.add_event = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        
        exc = ValueError("test error")
        record_exception(mock_span, exc)
        mock_span.record_exception.assert_called_once_with(exc)
        mock_span.set_status.assert_called_once()

    def test_record_exception_without_span(self) -> None:
        """record_exception does not raise without span."""
        record_exception(None, ValueError("test error"))


class TestInMemoryOTelTracerEvents:
    """Tests for event recording using real in-memory OTel tracer."""

    @pytest.fixture
    def in_memory_tracer_provider(self) -> Any:
        """Create an in-memory tracer provider for testing."""
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import InMemorySpanExporter, SimpleSpanProcessor

            # Create in-memory exporter
            exporter = InMemorySpanExporter()
            
            # Create resource
            resource = Resource.create({"service.name": "k9b-test"})
            
            # Create tracer provider
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(SimpleSpanProcessor(exporter))
            
            # Set as global provider
            trace.set_tracer_provider(provider)
            
            yield exporter
            
            # Cleanup
            provider.shutdown()
        except ImportError:
            pytest.skip("OpenTelemetry SDK not available")

    def test_span_records_events(self, in_memory_tracer_provider: Any) -> None:
        """Spans correctly record events."""
        from opentelemetry import trace
        
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("test_span") as span:
            span.add_event("test_event", {"event_attr": "value"})
        
        spans = in_memory_tracer_provider.get_finished_spans()
        span = spans[0]
        
        events = span.events
        assert len(events) == 1
        assert events[0].name == "test_event"
        assert events[0].attributes.get("event_attr") == "value"

    def test_span_records_exception_on_error(self, in_memory_tracer_provider: Any) -> None:
        """Spans record exceptions when errors occur."""
        from opentelemetry import trace
        from opentelemetry.trace import StatusCode
        
        tracer = trace.get_tracer("test")
        
        try:
            with tracer.start_as_current_span("test_span") as span:
                raise ValueError("test error")
        except ValueError:
            pass
        
        spans = in_memory_tracer_provider.get_finished_spans()
        span = spans[0]
        
        assert span.status.status_code == StatusCode.ERROR
        assert len(span.events) == 1  # Exception event

    def test_budget_exceeded_emits_no_planner_span(self, in_memory_tracer_provider: Any) -> None:
        """Budget exceeded path should not emit planner span."""
        from k8s_diag_agent.collect.otel_helpers import start_budget_span
        
        # Simulate budget exceeded - no planner span should be started
        with start_budget_span("run-1", 1, True, "max_passes_reached"):
            pass
        
        spans = in_memory_tracer_provider.get_finished_spans()
        span_names = [s.name for s in spans]
        
        # Budget span should exist
        assert "k9b.diagnosis_loop.budget" in span_names
        # No planner span should exist (budget was exceeded)
        assert "k9b.diagnosis_loop.plan" not in span_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
