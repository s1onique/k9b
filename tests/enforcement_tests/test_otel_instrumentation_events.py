"""Tests for OTel event helpers in diagnosis loop runtime.

These tests verify that:
1. Event names use k9b namespace
2. Events are properly emitted with correct attributes
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import (
    EVENT_ARTIFACT_WRITTEN,
    EVENT_BUDGET_EXCEEDED,
    EVENT_CHECK_REJECTED,
    EVENT_CHECKS_EXECUTED,
    EVENT_LOOP_STOP,
    SpanContext,
)


class TestEventNames:
    """Tests for stable event name formatting."""

    def test_all_event_names_use_k9b_prefix(self) -> None:
        """All event names use the k9b. prefix."""
        assert EVENT_BUDGET_EXCEEDED.startswith("k9b.")
        assert EVENT_CHECK_REJECTED.startswith("k9b.")
        assert EVENT_CHECKS_EXECUTED.startswith("k9b.")
        assert EVENT_ARTIFACT_WRITTEN.startswith("k9b.")
        assert EVENT_LOOP_STOP.startswith("k9b.")


class TestSpanContextEvents:
    """Tests for SpanContext event emission."""

    def test_span_context_add_event(self) -> None:
        """SpanContext.add_event calls span.add_event."""
        mock_span = MagicMock()
        mock_span.add_event = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        
        ctx = SpanContext(name="test", manager=mock_span)
        # Simulate entering the context to set active_span
        with ctx:
            ctx.add_event("test_event", {"key": "value"})
            mock_span.add_event.assert_called_once_with("test_event", attributes={"key": "value"})

    def test_span_context_add_event_without_span(self) -> None:
        """SpanContext.add_event does not fail without span."""
        ctx = SpanContext(name="test")
        ctx.add_event("test_event", {"key": "value"})  # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
