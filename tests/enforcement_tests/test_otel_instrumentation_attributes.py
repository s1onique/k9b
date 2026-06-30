"""Tests for OTel SpanContext behavior in diagnosis loop runtime.

These tests verify that:
1. SpanContext context manager properly enters/exits
2. SpanContext methods handle None spans gracefully
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_otel import SpanContext


class TestSpanContext:
    """Tests for SpanContext context manager."""

    def test_span_context_enter_exit(self) -> None:
        """SpanContext properly calls span __enter__ and __exit__."""
        mock_span = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_span.add_event = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        
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

    def test_span_context_set_ok(self) -> None:
        """SpanContext.set_ok sets OK status."""
        mock_span = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        
        ctx = SpanContext(name="test", manager=mock_span)
        with ctx:
            ctx.set_ok()
            mock_span.set_status.assert_called()

    def test_span_context_set_error(self) -> None:
        """SpanContext.set_error sets ERROR status."""
        mock_span = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        
        ctx = SpanContext(name="test", manager=mock_span)
        with ctx:
            ctx.set_error()
            mock_span.set_status.assert_called()

    def test_span_context_record_exception(self) -> None:
        """SpanContext.record_exception records exception."""
        mock_span = MagicMock()
        mock_span.set_status = MagicMock()
        mock_span.record_exception = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=None)
        
        ctx = SpanContext(name="test", manager=mock_span)
        exc = ValueError("test error")
        with ctx:
            ctx.record_exception(exc)
            mock_span.record_exception.assert_called_once_with(exc)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
