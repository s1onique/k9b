"""Tests for OTel span helpers in diagnosis loop runtime.

These tests verify that:
1. High-level span helpers return SpanContext
2. Span names follow stable naming conventions
3. Spans are properly ended using start_as_current_span pattern
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    SpanContext,
    start_artifact_span,
    start_budget_span,
    start_execute_span,
    start_gate_span,
    start_loop_span,
    start_pass_span,
    start_plan_span,
)


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


class TestInMemoryOTelTracer:
    """Tests using real in-memory OTel tracer when available."""

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
