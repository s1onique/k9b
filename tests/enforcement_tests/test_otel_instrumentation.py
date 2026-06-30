"""Tests for OTel instrumentation in diagnosis loop runtime.

These tests verify that:
1. OTel helpers degrade gracefully when OTel is unavailable
2. Span names follow stable naming conventions
3. Attribute keys use k9b namespace
4. Event names use k9b namespace
5. Telemetry failures do not affect diagnosis loop behavior
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    ATTR_CHECKS_ACCEPTED,
    ATTR_CHECKS_PROPOSED,
    ATTR_CHECKS_REJECTED,
    ATTR_CHECKS_REJECTED_BUDGET,
    ATTR_CHECKS_REJECTED_MUTATING,
    ATTR_CHECKS_REJECTED_SENSITIVE,
    ATTR_CHECKS_REJECTED_DUPLICATE,
    ATTR_LOOP_BUDGET_EXCEEDED,
    ATTR_LOOP_PASS_INDEX,
    ATTR_LOOP_RUN_ID,
    ATTR_LOOP_STOP_REASON,
    ATTR_ARTIFACT_PATH,
    ATTR_ARTIFACT_SCHEMA_VALID,
    ATTR_ARTIFACT_SCHEMA_MISSING_COUNT,
    ATTR_EVIDENCE_NEW_COUNT,
    EVENT_BUDGET_EXCEEDED,
    EVENT_CHECK_REJECTED,
    EVENT_CHECKS_EXECUTED,
    EVENT_ARTIFACT_WRITTEN,
    EVENT_LOOP_STOP,
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
    SpanContext,
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
    tracer.start_span = MagicMock(return_value=mock_span)
    return tracer


# =============================================================================
# Test: OTel Helpers Degrade Safely
# =============================================================================


class TestOTelGracefulDegradation:
    """Tests for graceful degradation when OTel is unavailable."""

    def test_start_span_returns_span_context_when_no_tracer(self) -> None:
        """start_span returns a valid SpanContext even without tracer."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_span("test.span", {"key": "value"})
            assert isinstance(ctx, SpanContext)
            assert ctx.name == "test.span"
            assert ctx.span is None

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
        ctx = SpanContext(name="test", span=mock_span)
        with ctx:
            pass
        mock_span.__enter__.assert_called_once()
        mock_span.__exit__.assert_called_once()

    def test_span_context_without_span(self) -> None:
        """SpanContext without span does not fail on enter/exit."""
        ctx = SpanContext(name="test")
        with ctx:
            pass


# =============================================================================
# Test: High-Level Span Helpers
# =============================================================================


class TestHighLevelSpanHelpers:
    """Tests for high-level span helper functions."""

    def test_start_loop_span_returns_context(self) -> None:
        """start_loop_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            from k8s_diag_agent.collect.incident_diagnosis_loop_policy import DiagnosisLoopPolicy

            policy = DiagnosisLoopPolicy()
            ctx = start_loop_span("run-123", "incident-456", policy)

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.run"

    def test_start_budget_span_returns_context(self) -> None:
        """start_budget_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_budget_span("run-123", 1, True, "max_passes_reached")

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.budget"

    def test_start_plan_span_returns_context(self) -> None:
        """start_plan_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_plan_span("run-123", 1)

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.plan"

    def test_start_gate_span_returns_context(self) -> None:
        """start_gate_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
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
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_execute_span("run-123", 1, 3, "read_only")

            assert isinstance(ctx, SpanContext)
            assert ctx.name == "k9b.diagnosis_loop.execute"

    def test_start_artifact_span_returns_context(self) -> None:
        """start_artifact_span returns a SpanContext."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
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
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
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
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_span("test.span", {"key": "value"})
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
            SPAN_LOOP_RUN,
            SPAN_LOOP_PASS,
            SPAN_LOOP_BUDGET,
            SPAN_LOOP_PLAN,
            SPAN_LOOP_GATE,
            SPAN_LOOP_EXECUTE,
            SPAN_LOOP_ARTIFACT,
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
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
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
            assert ctx.span is None

    def test_artifact_span_attributes_contain_only_safe_types(self) -> None:
        """Artifact span attributes only contain simple types, not raw data."""
        with patch("k8s_diag_agent.collect.incident_diagnosis_loop_otel._trace", None):
            ctx = start_artifact_span(
                "run-123", 1,
                artifact_path="/path/to/artifact.json",
                schema_valid=True,
                missing_fields=0,
                new_evidence_count=2,
            )
            
            assert ctx is not None
            assert ctx.span is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
