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
# Fallback Status Objects (defined first to allow helper below)
# =============================================================================


class _FallbackStatusCode:
    """Fallback enum-like status codes when OTel is unavailable."""
    OK = "OK"
    ERROR = "ERROR"


@dataclass(frozen=True)
class _FallbackStatus:
    """Fallback Status object when OTel is unavailable.

    Provides duck-compatible interface with `status_code` and `description` attributes.
    """
    status_code: Any
    description: str | None = None


# =============================================================================
# OTel Import with Graceful Degradation
# =============================================================================


def _load_otel_status_types() -> tuple[Any, Any, bool]:
    """Load OTel Status types if available, otherwise return fallbacks.

    Returns:
        tuple of (Status class, StatusCode class, availability flag)
    """
    try:
        from opentelemetry.trace import Status, StatusCode

        return Status, StatusCode, True
    except ImportError:
        # OTel not available - use fallback status objects
        return _FallbackStatus, _FallbackStatusCode, False


_OTelStatus, _OTelStatusCode, _OTEL_AVAILABLE = _load_otel_status_types()


def _status_code_ok() -> Any:
    """Get the OK status code (OTel or fallback)."""
    return _OTelStatusCode.OK


def _status_code_error() -> Any:
    """Get the ERROR status code (OTel or fallback)."""
    return _OTelStatusCode.ERROR


def _make_status(status_code: Any, description: str | None = None) -> Any:
    """Create a Status object (OTel or fallback).

    Args:
        status_code: The status code (OK or ERROR)
        description: Optional description for error status

    Returns:
        OTel Status object if available, otherwise _FallbackStatus
    """
    if description is None:
        return _OTelStatus(status_code)
    return _OTelStatus(status_code, description=description)


# Aliases for backward compatibility
_Status = _OTelStatus
_StatusCode = _OTelStatusCode
_STATUS_CODES_AVAILABLE = _OTEL_AVAILABLE


# =============================================================================
# Duck-Typed Span Helpers
# =============================================================================


def _span_is_recording(span: object) -> bool:
    """Check if span is recording using duck-typed approach.

    Returns True if we cannot determine recording status,
    allowing status setting on test doubles.
    """
    is_recording = getattr(span, "is_recording", None)
    if not callable(is_recording):
        return True

    try:
        return bool(is_recording())
    except Exception:  # noqa: BLE001 - defensive: span.is_recording() may raise
        return True


def _set_span_status(
    span: object | None,
    status_code: object | None,
    description: str | None = None,
) -> None:
    """Set span status using duck-typed approach.

    Only requires that the span has a callable set_status method.
    Works with real OTel spans and test doubles (Mock/MagicMock).
    """
    if span is None or status_code is None:
        return

    set_status = getattr(span, "set_status", None)
    if not callable(set_status):
        return

    if not _span_is_recording(span):
        return

    try:
        status = _make_status(status_code, description)
        set_status(status)
    except Exception:  # noqa: BLE001 - defensive: span.set_status() may raise
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
        Uses duck-typed approach to work with real spans and test doubles.
        """
        _set_span_status(
            self.active_span,
            _status_code_ok(),
        )

    def set_error(self, description: str | None = None) -> None:
        """Set span status to ERROR.

        Safe to call even if span is None or OTel is unavailable.
        Uses duck-typed approach to work with real spans and test doubles.

        Args:
            description: Optional description for the error status.
        """
        _set_span_status(
            self.active_span,
            _status_code_error(),
            description,
        )

    def record_exception(self, exc: Exception) -> None:
        """Record an exception on the span.

        Safe to call even if span is None or OTel is unavailable.
        Uses duck-typed approach to work with real spans and test doubles.

        Args:
            exc: The exception to record
        """
        if self.active_span is None:
            return

        record_exception = getattr(self.active_span, "record_exception", None)
        if callable(record_exception):
            try:
                record_exception(exc)
            except Exception:
                pass

        self.set_error(f"{type(exc).__name__}: {exc}")


__all__ = [
    "SpanContext",
]
