"""OTel event helpers for diagnosis loop instrumentation.

This module provides event emission helpers that attach structured events
to OTel spans. Events are used to record important occurrences within spans
without creating child spans.

Design principles:
- Events use bounded, safe attributes only
- No raw check output, secrets, or LLM content is emitted
- Events are safe to call even when OTel is unavailable
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .otel_span_context import SpanContext

if TYPE_CHECKING:
    pass


# =============================================================================
# Event Names (imported from constants)
# =============================================================================

from .otel_constants import (
    ATTR_ARTIFACT_PATH,
    ATTR_ARTIFACT_SCHEMA_VALID,
    ATTR_CHECKS_ACCEPTED,
    ATTR_LOOP_STOP_REASON,
    EVENT_ARTIFACT_WRITTEN,
    EVENT_AUTODIAG_INCIDENT_LIST_FAILED,
    EVENT_AUTODIAG_INCIDENT_LIST_START,
    EVENT_AUTODIAG_INCIDENT_LIST_SUCCESS,
    EVENT_BUDGET_EXCEEDED,
    EVENT_CHECK_REJECTED,
    EVENT_CHECKS_EXECUTED,
    EVENT_LOOP_STOP,
)

# =============================================================================
# Event Helpers
# =============================================================================


def emit_budget_exceeded_event(
    span_ctx: SpanContext,
    stop_reason: str,
) -> None:
    """Emit a budget exceeded event on the span.

    Args:
        span_ctx: The span context to emit the event on
        stop_reason: The reason for budget exhaustion
    """
    span_ctx.add_event(EVENT_BUDGET_EXCEEDED, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


def emit_check_rejected_event(
    span_ctx: SpanContext,
    check_id: str,
    rejection_reason: str,
    is_unsafe: bool = False,
    is_sensitive: bool = False,
) -> None:
    """Emit a check rejected event on the span.

    Only includes bounded details - no raw check output or secrets.

    Args:
        span_ctx: The span context to emit the event on
        check_id: The check that was rejected
        rejection_reason: Reason for rejection
        is_unsafe: Whether the check was unsafe
        is_sensitive: Whether the check was sensitive
    """
    span_ctx.add_event(EVENT_CHECK_REJECTED, {
        "check_id": check_id,
        "rejection_reason": rejection_reason,
        "is_unsafe": is_unsafe,
        "is_sensitive": is_sensitive,
    })


def emit_checks_executed_event(
    span_ctx: SpanContext,
    count: int,
) -> None:
    """Emit a checks executed event on the span.

    Args:
        span_ctx: The span context to emit the event on
        count: Number of checks executed
    """
    span_ctx.add_event(EVENT_CHECKS_EXECUTED, {
        ATTR_CHECKS_ACCEPTED: count,
    })


def emit_artifact_written_event(
    span_ctx: SpanContext,
    artifact_path: str,
    schema_valid: bool,
) -> None:
    """Emit an artifact written event on the span.

    Args:
        span_ctx: The span context to emit the event on
        artifact_path: Path to the written artifact
        schema_valid: Whether the artifact schema is valid
    """
    span_ctx.add_event(EVENT_ARTIFACT_WRITTEN, {
        ATTR_ARTIFACT_PATH: artifact_path,
        ATTR_ARTIFACT_SCHEMA_VALID: schema_valid,
    })


def emit_stop_event(
    span_ctx: SpanContext,
    stop_reason: str,
) -> None:
    """Emit a stop event on the span.

    Args:
        span_ctx: The span context to emit the event on
        stop_reason: The stop reason
    """
    span_ctx.add_event(EVENT_LOOP_STOP, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


def emit_autodiag_incident_list_start_event(
    span_ctx: SpanContext,
    mode: str,
) -> None:
    """Emit an automatic diagnosis incident list start event.

    Args:
        span_ctx: The span context to emit the event on
        mode: The listing mode (local, backend-api)
    """
    span_ctx.add_event(EVENT_AUTODIAG_INCIDENT_LIST_START, {
        "listing_mode": mode,
    })


def emit_autodiag_incident_list_success_event(
    span_ctx: SpanContext,
    count: int,
    mode: str,
) -> None:
    """Emit an automatic diagnosis incident list success event.

    Args:
        span_ctx: The span context to emit the event on
        count: Number of incidents listed
        mode: The listing mode (local, backend-api)
    """
    span_ctx.add_event(EVENT_AUTODIAG_INCIDENT_LIST_SUCCESS, {
        "incident_count": count,
        "listing_mode": mode,
    })


def emit_autodiag_incident_list_failed_event(
    span_ctx: SpanContext,
    error: str,
    mode: str,
    error_type: str | None = None,
) -> None:
    """Emit an automatic diagnosis incident list failed event.

    Args:
        span_ctx: The span context to emit the event on
        error: Error message (sanitized)
        mode: The listing mode (local, backend-api)
        error_type: Optional classified error type (unauthorized, timeout, etc.)
    """
    attributes: dict[str, Any] = {
        "error": error,
        "listing_mode": mode,
    }
    if error_type:
        attributes["error_type"] = error_type
    span_ctx.add_event(EVENT_AUTODIAG_INCIDENT_LIST_FAILED, attributes)


# =============================================================================
# Legacy Event Helpers (accept raw span for backward compatibility)
# =============================================================================


def _add_event_to_span(
    span: Any,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Add an event to a raw span.

    Safe to call even if span is None or OTel is unavailable.

    Args:
        span: The raw span object (or None)
        name: Event name
        attributes: Optional event attributes
    """
    if span is None or not hasattr(span, 'add_event'):
        return
    try:
        span.add_event(name, attributes=attributes)
    except Exception:
        pass


def emit_budget_exceeded_event_legacy(
    span: Any,
    stop_reason: str,
) -> None:
    """Legacy wrapper for emit_budget_exceeded_event.

    DEPRECATED: Use emit_budget_exceeded_event with SpanContext instead.
    """
    if span is None:
        return
    _add_event_to_span(span, EVENT_BUDGET_EXCEEDED, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


def emit_check_rejected_event_legacy(
    span: Any,
    check_id: str,
    rejection_reason: str,
    is_unsafe: bool = False,
    is_sensitive: bool = False,
) -> None:
    """Legacy wrapper for emit_check_rejected_event.

    DEPRECATED: Use emit_check_rejected_event with SpanContext instead.
    """
    if span is None:
        return
    _add_event_to_span(span, EVENT_CHECK_REJECTED, {
        "check_id": check_id,
        "rejection_reason": rejection_reason,
        "is_unsafe": is_unsafe,
        "is_sensitive": is_sensitive,
    })


def emit_checks_executed_event_legacy(
    span: Any,
    count: int,
) -> None:
    """Legacy wrapper for emit_checks_executed_event.

    DEPRECATED: Use emit_checks_executed_event with SpanContext instead.
    """
    if span is None:
        return
    _add_event_to_span(span, EVENT_CHECKS_EXECUTED, {
        ATTR_CHECKS_ACCEPTED: count,
    })


def emit_artifact_written_event_legacy(
    span: Any,
    artifact_path: str,
    schema_valid: bool,
) -> None:
    """Legacy wrapper for emit_artifact_written_event.

    DEPRECATED: Use emit_artifact_written_event with SpanContext instead.
    """
    if span is None:
        return
    _add_event_to_span(span, EVENT_ARTIFACT_WRITTEN, {
        ATTR_ARTIFACT_PATH: artifact_path,
        ATTR_ARTIFACT_SCHEMA_VALID: schema_valid,
    })


def emit_stop_event_legacy(
    span: Any,
    stop_reason: str,
) -> None:
    """Legacy wrapper for emit_stop_event.

    DEPRECATED: Use emit_stop_event with SpanContext instead.
    """
    if span is None:
        return
    _add_event_to_span(span, EVENT_LOOP_STOP, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


__all__ = [
    # Event helpers (preferred - use SpanContext)
    "emit_budget_exceeded_event",
    "emit_check_rejected_event",
    "emit_checks_executed_event",
    "emit_artifact_written_event",
    "emit_stop_event",
    # Automatic diagnosis incident listing events
    "emit_autodiag_incident_list_start_event",
    "emit_autodiag_incident_list_success_event",
    "emit_autodiag_incident_list_failed_event",
    # Legacy event helpers (deprecated - use raw span)
    "emit_budget_exceeded_event_legacy",
    "emit_check_rejected_event_legacy",
    "emit_checks_executed_event_legacy",
    "emit_artifact_written_event_legacy",
    "emit_stop_event_legacy",
]
