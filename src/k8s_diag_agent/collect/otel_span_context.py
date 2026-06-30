"""OTel SpanContext for diagnosis loop instrumentation.

This module provides the SpanContext dataclass that wraps OpenTelemetry
spans and ensures proper lifecycle management via context managers.

The SpanContext uses start_as_current_span to ensure:
- Spans are automatically ended when exiting the context
- Nested spans are properly scoped as the current span
- Telemetry is correctly nested in the trace hierarchy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# =============================================================================
# OTel Import with Graceful Degradation
# =============================================================================

_Status: Any = None
_status_OK: Any = None
_status_ERROR: Any = None
_STATUS_CODES_AVAILABLE: bool = False

try:
    from opentelemetry.trace import Status, StatusCode

    _Status = Status
    _status_OK = StatusCode.OK
    _status_ERROR = StatusCode.ERROR
    _STATUS_CODES_AVAILABLE = True
except ImportError:
    # OTel not available - helpers will be no-ops
    pass


# =============================================================================
# SpanContext Dataclass
# =============================================================================


@dataclass
class SpanContext:
    """Context holder for span management using start_as_current_span pattern.

    This class wraps an OpenTelemetry span context manager to ensure:
    - Spans are automatically ended on context exit
    - Nested spans are properly scoped as the current span
    - Telemetry degrades gracefully when OTel is unavailable

    The active_span attribute holds the actual OTel span object when available,
    or None when OTel is not configured.

    Usage:
        with start_budget_span(...) as ctx:
            # ctx.active_span is the current span
            ctx.add_event("event_name")
            # Span is automatically ended when exiting
    """

    name: str
    manager: Any = field(default=None, repr=False)
    active_span: Any = field(default=None, repr=False)

    @property
    def span(self) -> Any:
        """Backward-compatible property returning the active span.

        DEPRECATED: Use active_span directly instead.
        """
        return self.active_span

    def __enter__(self) -> SpanContext:
        """Enter the span context.

        For start_as_current_span, this sets the span as current and
        stores the returned active span.
        """
        if self.manager is not None:
            self.active_span = self.manager.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the span context.

        This ends the span and restores the parent.
        """
        if self.manager is not None:
            self.manager.__exit__(exc_type, exc_val, exc_tb)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span.

        Safe to call even if span is None or OTel is unavailable.

        Args:
            name: Event name
            attributes: Optional event attributes
        """
        if self.active_span is None or not hasattr(self.active_span, 'add_event'):
            return
        try:
            self.active_span.add_event(name, attributes=attributes)
        except Exception:
            pass

    def set_ok(self) -> None:
        """Set span status to OK.

        Safe to call even if span is None or OTel is unavailable.
        """
        if self.active_span is None or not hasattr(self.active_span, 'set_status'):
            return
        try:
            if _Status is not None and _status_OK is not None:
                self.active_span.set_status(_Status(_status_OK))
        except Exception:
            pass

    def set_error(self) -> None:
        """Set span status to ERROR.

        Safe to call even if span is None or OTel is unavailable.
        """
        if self.active_span is None or not hasattr(self.active_span, 'set_status'):
            return
        try:
            if _Status is not None and _status_ERROR is not None:
                self.active_span.set_status(_Status(_status_ERROR))
        except Exception:
            pass

    def record_exception(self, exc: Exception) -> None:
        """Record an exception on the span.

        Safe to call even if span is None or OTel is unavailable.

        Args:
            exc: The exception to record
        """
        if self.active_span is None or not hasattr(self.active_span, 'record_exception'):
            return
        try:
            self.active_span.record_exception(exc)
            if _Status is not None and _status_ERROR is not None:
                self.active_span.set_status(_Status(_status_ERROR))
        except Exception:
            pass


__all__ = [
    "SpanContext",
]
