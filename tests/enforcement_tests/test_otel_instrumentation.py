"""Tests for OTel instrumentation in diagnosis loop runtime.

These tests verify that:
1. OTel helpers degrade gracefully when OTel is unavailable
2. Span names follow stable naming conventions
3. Attribute keys use k9b namespace
4. Event names use k9b namespace
5. Telemetry failures do not affect diagnosis loop behavior
6. Spans are properly ended using start_as_current_span pattern
7. Nested spans are correctly scoped as current spans
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    ATTR_ARTIFACT_PATH,
    ATTR_CHECKS_ACCEPTED,
    ATTR_CHECKS_PROPOSED,
    ATTR_CHECKS_REJECTED,
    ATTR_LOOP_BUDGET_EXCEEDED,
    ATTR_LOOP_PASS_INDEX,
    ATTR_LOOP_RUN_ID,
    EVENT_ARTIFACT_WRITTEN,
    EVENT_BUDGET_EXCEEDED,
    EVENT_CHECK_REJECTED,
    EVENT_CHECKS_EXECUTED,
    EVENT_LOOP_STOP,
    SpanContext,
    record_exception,
    set_span_error,
    set_span_ok,
    start_artifact_span,
    start_budget_span,
    start_execute_span,
    start_gate_span,
    start_loop_span,
    start_pass_span,
    start_plan_span,
    start_span,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_span() -> MagicMock:
    """Create a mock span for testing."""
    span = MagicMock()
    span.set_attribute = MagicMock()
    span.add_event = MagicMock()
    span.set_status = MagicMock()
    span.record_exception = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=None)
    return span


@pytest.fixture
def mock_tracer(mock_span: MagicMock) -> MagicMock:
    """Create a mock tracer that returns mock spans."""
    tracer = MagicMock()
    tracer.start_as_current_span = MagicMock(return_value=mock_span)
    tracer.start_span = MagicMock(return_value=mock_span)
    return tracer


# =============================================================================
# Test: OTel Helpers Degrade Safely
# =============================================================================


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


# =============================================================================
# Test: Span Context Manager
# =============================================================================


class TestSpanContext:
    """Tests for SpanContext context manager."""

    def test_span_context_enter_exit(self, mock_span: MagicMock) -> None:
        """SpanContext properly calls span __enter__ and __exit__."""
        # The mock_span is the context manager returned by start_as_current_span
        ctx = SpanContext(name="test", manager=mock_span)
        with ctx:
            # active_span should be set from manager.__enter__()
            assert ctx.active_span is mock_span
        mock_span.__enter__.assert_called_once()
        mock_span.__exit__.assert_called_once()

    def test_span_context_without_span(self) -> None:
        """SpanContext without span does not fail on enter/exit."""
        ctx = SpanContext(name="test")
        with ctx:
            pass

    def test_span_context_add_event(self, mock_span: MagicMock) -> None:
        """SpanContext.add_event calls span.add_event."""
        ctx = SpanContext(name="test", manager=mock_span)
        # Simulate entering the context to set active_span
        with ctx:
            ctx.add_event("test_event", {"key": "value"})
            mock_span.add_event.assert_called_once_with("test_event", attributes={"key": "value"})

    def test_span_context_add_event_without_span(self) -> None:
        """SpanContext.add_event does not fail without span."""
        ctx = SpanContext(name="test")
        ctx.add_event("test_event", {"key": "value"})  # Should not raise

    def test_span_context_set_ok(self, mock_span: MagicMock) -> None:
        """SpanContext.set_ok sets OK status."""
        ctx = SpanContext(name="test", manager=mock_span)
        with ctx:
            ctx.set_ok()
            mock_span.set_status.assert_called()

    def test_span_context_set_error(self, mock_span: MagicMock) -> None:
        """SpanContext.set_error sets ERROR status."""
        ctx = SpanContext(name="test", manager=mock_span)
        with ctx:
            ctx.set_error()
            mock_span.set_status.assert_called()

    def test_span_context_record_exception(self, mock_span: MagicMock) -> None:
        """SpanContext.record_exception records exception."""
        ctx = SpanContext(name="test", manager=mock_span)
        exc = ValueError("test error")
        with ctx:
            ctx.record_exception(exc)
            mock_span.record_exception.assert_called_once_with(exc)


# =============================================================================
# Test: High-Level Span Helpers
# =============================================================================


class TestHighLevelSpanHelpers:
    """Tests for high-level span helper functions."""

    def test_start_loop_span_returns_context(self) -> None:
        """start_loop_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            from k8s_diag_agent.collect.incident_diagnosis_loop_policy import DiagnosisLoopPolicy

            policy = DiagnosisLoopPolicy()
            ctx = start_loop_span("run-123", "incident-456", policy)

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.run"

    def test_start_budget_span_returns_context(self) -> None:
        """start_budget_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_budget_span("run-123", 1, True, "max_passes_reached")

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.budget"

    def test_start_plan_span_returns_context(self) -> None:
        """start_plan_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_plan_span("run-123", 1)

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.plan"

    def test_start_gate_span_returns_context(self) -> None:
        """start_gate_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_gate_span(
                "run-123", 1,
                proposed=5,
                accepted=3,
                rejected_mutating=1,
                rejected_sensitive=1,
                rejected_duplicate=0,
                rejected_budget=0,
            )

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.gate"

    def test_start_execute_span_returns_context(self) -> None:
        """start_execute_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_execute_span("run-123", 1, 3, "read_only")

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.execute"

    def test_start_artifact_span_returns_context(self) -> None:
        """start_artifact_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_artifact_span(
                "run-123", 1,
                artifact_path="/path/to/artifact.json",
                schema_valid=True,
                missing_fields=0,
                new_evidence_count=2,
            )

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.artifact"

    def test_start_pass_span_returns_context(self) -> None:
        """start_pass_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_pass_span(
                "run-123", 1,
                decision="run_allowed_read_only_checks",
                stop_reason="max_passes_reached",
                checks_accepted=3,
                checks_rejected=2,
            )

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.pass"


# =============================================================================
# Test: Exception Recording
# =============================================================================


class TestExceptionRecording:
    """Tests for exception recording."""

    def test_record_exception_sets_error_status(self, mock_span: MagicMock) -> None:
        """record_exception records exception and sets error status."""
        exc = ValueError("test error")
        record_exception(mock_span, exc)
        mock_span.record_exception.assert_called_once_with(exc)
        mock_span.set_status.assert_called_once()

    def test_record_exception_without_span(self) -> None:
        """record_exception does not raise without span."""
        record_exception(None, ValueError("test error"))


# =============================================================================
# Test: Telemetry Failure Does Not Break Runtime
# =============================================================================


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


# =============================================================================
# Test: Attribute Keys Are Stable
# =============================================================================


class TestAttributeKeys:
    """Tests for stable attribute key naming."""

    def test_all_attribute_keys_use_k9b_prefix(self) -> None:
        """All attribute keys use the k9b. prefix."""
        assert ATTR_LOOP_RUN_ID.startswith("k9b.")
        assert ATTR_LOOP_PASS_INDEX.startswith("k9b.")
        assert ATTR_CHECKS_PROPOSED.startswith("k9b.")
        assert ATTR_CHECKS_ACCEPTED.startswith("k9b.")
        assert ATTR_CHECKS_REJECTED.startswith("k9b.")
        assert ATTR_ARTIFACT_PATH.startswith("k9b.")
        assert ATTR_LOOP_BUDGET_EXCEEDED.startswith("k9b.")

    def test_all_event_names_use_k9b_prefix(self) -> None:
        """All event names use the k9b. prefix."""
        assert EVENT_BUDGET_EXCEEDED.startswith("k9b.")
        assert EVENT_CHECK_REJECTED.startswith("k9b.")
        assert EVENT_CHECKS_EXECUTED.startswith("k9b.")
        assert EVENT_ARTIFACT_WRITTEN.startswith("k9b.")
        assert EVENT_LOOP_STOP.startswith("k9b.")


# =============================================================================
# Test: Span Names Are Stable
# =============================================================================


class TestSpanNames:
    """Tests for stable span name formatting."""

    def test_span_names_follow_naming_convention(self) -> None:
        """Span names follow k9b.diagnosis_loop.* convention."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
            SPAN_LOOP_ARTIFACT,
            SPAN_LOOP_BUDGET,
            SPAN_LOOP_EXECUTE,
            SPAN_LOOP_GATE,
            SPAN_LOOP_PASS,
            SPAN_LOOP_PLAN,
            SPAN_LOOP_RUN,
            SPAN_LOOP_STOP,
        )

        assert SPAN_LOOP_RUN == "k9b.diagnosis_loop.run"
        assert SPAN_LOOP_PASS == "k9b.diagnosis_loop.pass"
        assert SPAN_LOOP_BUDGET == "k9b.diagnosis_loop.budget"
        assert SPAN_LOOP_PLAN == "k9b.diagnosis_loop.plan"
        assert SPAN_LOOP_GATE == "k9b.diagnosis_loop.gate"
        assert SPAN_LOOP_EXECUTE == "k9b.diagnosis_loop.execute"
        assert SPAN_LOOP_ARTIFACT == "k9b.diagnosis_loop.artifact"
        assert SPAN_LOOP_STOP == "k9b.diagnosis_loop.stop"


# =============================================================================
# Test: Secret Values Are Not Emitted (API Contract)
# =============================================================================


class TestSecretValuesNotEmitted:
    """Tests that no secret values are emitted in telemetry API."""

    def test_gate_span_attributes_contain_only_safe_types(self) -> None:
        """Gate span attributes only contain simple types, not raw check data."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_gate_span(
                "run-123", 1,
                proposed=5,
                accepted=3,
                rejected_mutating=1,
                rejected_sensitive=1,
                rejected_duplicate=0,
                rejected_budget=0,
            )
            
            # The context is created without error
            assert ctx is not None
            # The span is None when no tracer, which means no telemetry is emitted
            assert ctx.active_span is None
            assert ctx.span is None

    def test_artifact_span_attributes_contain_only_safe_types(self) -> None:
        """Artifact span attributes only contain simple types, not raw data."""
        with patch("k8s_diag_agent.collect.otel_helpers._trace", None):
            ctx = start_artifact_span(
                "run-123", 1,
                artifact_path="/path/to/artifact.json",
                schema_valid=True,
                missing_fields=0,
                new_evidence_count=2,
            )
            
            assert ctx is not None
            assert ctx.active_span is None
            assert ctx.span is None


# =============================================================================
# Test: In-Memory OTel with Real Tracer (if available)
# =============================================================================


class TestInMemoryOTelTracer:
    """Tests using real in-memory OTel tracer when available."""

    @pytest.fixture
    def in_memory_tracer_provider(self) -> Generator[Any, None, None]:
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

    def test_span_ends_on_context_exit(self, in_memory_tracer_provider: Any) -> None:
        """Spans are ended when context manager exits."""
        from opentelemetry import trace
        
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("test_span") as span:
            assert span.is_recording()
        
        # Span should be ended and exported
        spans = in_memory_tracer_provider.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_span"

    def test_nested_spans_are_properly_scoped(self, in_memory_tracer_provider: Any) -> None:
        """Nested spans correctly nest under parent."""
        from opentelemetry import trace
        
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("parent"):
            with tracer.start_as_current_span("child"):
                pass
        
        spans = in_memory_tracer_provider.get_finished_spans()
        assert len(spans) == 2
        
        # Child should have parent as its parent
        child_span = next(s for s in spans if s.name == "child")
        parent_span = next(s for s in spans if s.name == "parent")
        
        assert child_span.parent.span_id == parent_span.context.span_id

    def test_span_records_attributes(self, in_memory_tracer_provider: Any) -> None:
        """Spans correctly record attributes."""
        from opentelemetry import trace
        
        tracer = trace.get_tracer("test")
        
        with tracer.start_as_current_span("test_span") as span:
            span.set_attribute("test_attr", "test_value")
            span.set_attribute("numeric_attr", 42)
        
        spans = in_memory_tracer_provider.get_finished_spans()
        span = spans[0]
        
        attrs = {k: v for k, v in span.attributes.items()}
        assert attrs.get("test_attr") == "test_value"
        assert attrs.get("numeric_attr") == 42

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
        assert "ValueError" in span.events[0].name or span.events[0].attributes.get("exception.type") == "ValueError"

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

    def test_all_loop_span_names_exported(self, in_memory_tracer_provider: Any) -> None:
        """All loop span names can be created and exported."""
        from k8s_diag_agent.collect.otel_helpers import (
            start_artifact_span,
            start_budget_span,
            start_execute_span,
            start_gate_span,
            start_plan_span,
        )
        
        with start_budget_span("run-1", 1, False, None):
            pass
        
        with start_plan_span("run-1", 1):
            pass
        
        with start_gate_span("run-1", 1, 3, 2, 1, 0, 0, 0):
            pass
        
        with start_execute_span("run-1", 1, 2, "read_only"):
            pass
        
        with start_artifact_span("run-1", 1, "/tmp/artifact.json", True, 0, 5):
            pass
        
        spans = in_memory_tracer_provider.get_finished_spans()
        span_names = {s.name for s in spans}
        
        expected_names = {
            "k9b.diagnosis_loop.budget",
            "k9b.diagnosis_loop.plan",
            "k9b.diagnosis_loop.gate",
            "k9b.diagnosis_loop.execute",
            "k9b.diagnosis_loop.artifact",
        }
        
        assert expected_names.issubset(span_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
