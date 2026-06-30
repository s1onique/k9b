"""OTel span helpers for diagnosis loop runtime.

This module provides OpenTelemetry span/event emission helpers that can be wired
to the actual OTel infrastructure when deployed. The helpers degrade safely
if OTel is unavailable or no provider is configured.

This module is a thin re-export layer. The actual implementation is split into:
- otel_constants: Span names, attribute keys, event names
- otel_span_context: SpanContext dataclass with proper lifecycle management
- otel_helpers: Core span helpers using start_as_current_span pattern
- otel_events: Event emission helpers

Usage:
    - Import helpers from this module
    - Call helpers in the diagnosis loop runtime
    - Application/deployment owns exporter configuration
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
        DiagnosisLoopPolicy,
    )

# Re-export constants
from .otel_constants import (
    ATTR_ARTIFACT_PATH,
    ATTR_ARTIFACT_SCHEMA_MISSING_COUNT,
    ATTR_ARTIFACT_SCHEMA_VALID,
    ATTR_CHECKS_ACCEPTED,
    ATTR_CHECKS_PROPOSED,
    ATTR_CHECKS_REJECTED,
    ATTR_CHECKS_REJECTED_BUDGET,
    ATTR_CHECKS_REJECTED_DUPLICATE,
    ATTR_CHECKS_REJECTED_MUTATING,
    ATTR_CHECKS_REJECTED_SENSITIVE,
    ATTR_EVIDENCE_NEW_COUNT,
    # Attribute keys
    ATTR_INCIDENT_ID,
    ATTR_LOOP_BUDGET_EXCEEDED,
    ATTR_LOOP_DECISION,
    ATTR_LOOP_MAX_CHECKS_PER_PASS,
    ATTR_LOOP_MAX_PASSES,
    ATTR_LOOP_MAX_TOTAL_CHECKS,
    ATTR_LOOP_PASS_INDEX,
    ATTR_LOOP_POLICY_SCHEMA_VERSION,
    ATTR_LOOP_RUN_ID,
    ATTR_LOOP_RUNNER_KIND,
    ATTR_LOOP_SCHEMA_VERSION,
    ATTR_LOOP_STOP_REASON,
    EVENT_ARTIFACT_WRITTEN,
    # Event names
    EVENT_BUDGET_EXCEEDED,
    EVENT_CHECK_REJECTED,
    EVENT_CHECKS_EXECUTED,
    EVENT_LOOP_STOP,
    SPAN_LOOP_ARTIFACT,
    SPAN_LOOP_BUDGET,
    SPAN_LOOP_EXECUTE,
    SPAN_LOOP_GATE,
    SPAN_LOOP_PASS,
    SPAN_LOOP_PLAN,
    # Span names
    SPAN_LOOP_RUN,
    SPAN_LOOP_STOP,
)

# Re-export event helpers
from .otel_events import (
    emit_artifact_written_event,
    emit_budget_exceeded_event,
    emit_check_rejected_event,
    emit_checks_executed_event,
    emit_stop_event,
)

# Re-export helpers
from .otel_helpers import (
    _get_tracer,
    start_artifact_span,
    start_budget_span,
    start_execute_span,
    start_gate_span,
    start_loop_span,
    start_pass_span,
    start_plan_span,
    start_span,
)

# Re-export SpanContext
# Import for legacy wrappers
from .otel_span_context import _STATUS_CODES_AVAILABLE, SpanContext, _status_ERROR, _status_OK

# Re-export status codes for backward compatibility
status_OK = _status_OK
status_ERROR = _status_ERROR


# =============================================================================
# Guarded OTel Import for Graceful Degradation
# =============================================================================


def _get_current_span() -> Any | None:
    """Get the current OTel span, safely returning None if OTel is unavailable.

    This replaces direct opentelemetry.trace imports to ensure graceful
    degradation when OTel is not installed or configured.
    """
    try:
        from opentelemetry import trace

        return trace.get_current_span()
    except ImportError:
        return None
    except Exception:
        return None


# =============================================================================
# Legacy API Wrappers (for backward compatibility)
# =============================================================================


def emit_loop_span(
    run_id: str,
    incident_id: str,
    policy: DiagnosisLoopPolicy,
    event: str,
) -> None:
    """Legacy wrapper for loop span emission.

    DEPRECATED: Use start_loop_span() with context manager instead.

    Args:
        run_id: Unique identifier for this loop run
        incident_id: The incident being diagnosed
        policy: The policy in effect
        event: The event name (started, completed, failed)
    """
    # For legacy compatibility, we emit events on the current span
    tracer = _get_tracer()
    if tracer is None:
        return

    try:
        current_span = _get_current_span()
        if current_span is None:
            return

        if event == "started":
            current_span.set_attribute(ATTR_INCIDENT_ID, incident_id)
            current_span.set_attribute(ATTR_LOOP_RUN_ID, run_id)
            current_span.set_attribute(ATTR_LOOP_MAX_PASSES, policy.max_passes)
            current_span.set_attribute(ATTR_LOOP_MAX_CHECKS_PER_PASS, policy.max_checks_per_pass)
        elif event == "completed":
            current_span.add_event("k9b.diagnosis_loop.completed")
        elif event == "failed":
            current_span.add_event("k9b.diagnosis_loop.failed")
    except Exception:
        pass


def emit_pass_span(
    run_id: str,
    pass_index: int,
    decision: str,
    stop_reason: str | None,
    checks_accepted: int,
    checks_rejected: int,
) -> None:
    """Legacy wrapper for pass span emission.

    DEPRECATED: Use start_pass_span() with context manager instead.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        decision: The loop decision
        stop_reason: The stop reason if stopped
        checks_accepted: Number of checks accepted
        checks_rejected: Number of checks rejected
    """
    tracer = _get_tracer()
    if tracer is None:
        return

    try:
        current_span = _get_current_span()
        if current_span is None:
            return

        current_span.set_attribute(ATTR_LOOP_RUN_ID, run_id)
        current_span.set_attribute(ATTR_LOOP_PASS_INDEX, pass_index)
        current_span.set_attribute(ATTR_LOOP_DECISION, decision)
        if stop_reason:
            current_span.set_attribute(ATTR_LOOP_STOP_REASON, stop_reason)
        current_span.set_attribute(ATTR_CHECKS_ACCEPTED, checks_accepted)
        current_span.set_attribute(ATTR_CHECKS_REJECTED, checks_rejected)
    except Exception:
        pass


def emit_check_gate_span(
    run_id: str,
    pass_index: int,
    check_id: str,
    accepted: bool,
    rejection_reason: str | None,
) -> None:
    """Legacy wrapper for check gate span emission.

    DEPRECATED: Use start_gate_span() and emit_check_rejected_event() instead.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        check_id: The check that was gated
        accepted: Whether the check was accepted
        rejection_reason: Reason for rejection if not accepted
    """
    if not accepted and rejection_reason:
        tracer = _get_tracer()
        if tracer is None:
            return

        try:
            current_span = _get_current_span()
            if current_span is None:
                return

            emit_check_rejected_event(
                SpanContext(name="current", active_span=current_span),
                check_id=check_id,
                rejection_reason=rejection_reason,
                is_unsafe=(rejection_reason == "mutating_check_rejected"),
                is_sensitive=(rejection_reason == "sensitive_read_denied"),
            )
        except Exception:
            pass


# =============================================================================
# Legacy Helpers (accept raw span for backward compatibility)
# =============================================================================


def record_exception(span: Any, exc: Exception) -> None:
    """Record an exception on a span.

    Safe to call even if span is None or OTel is unavailable.
    """
    if span is None or not hasattr(span, 'record_exception'):
        return
    try:
        span.record_exception(exc)
        span.set_status(_status_ERROR if _STATUS_CODES_AVAILABLE else None)
    except Exception:
        pass


def set_span_ok(span: Any) -> None:
    """Set span status to OK.

    Safe to call even if span is None or OTel is unavailable.
    """
    if span is None or not hasattr(span, 'set_status'):
        return
    try:
        if _status_OK is not None:
            span.set_status(_status_OK)
    except Exception:
        pass


def set_span_error(span: Any) -> None:
    """Set span status to ERROR.

    Safe to call even if span is None or OTel is unavailable.
    """
    if span is None or not hasattr(span, 'set_status'):
        return
    try:
        if _status_ERROR is not None:
            span.set_status(_status_ERROR)
    except Exception:
        pass


__all__ = [
    # Span names
    "SPAN_LOOP_RUN",
    "SPAN_LOOP_PASS",
    "SPAN_LOOP_BUDGET",
    "SPAN_LOOP_PLAN",
    "SPAN_LOOP_GATE",
    "SPAN_LOOP_EXECUTE",
    "SPAN_LOOP_ARTIFACT",
    "SPAN_LOOP_STOP",
    # Attribute keys
    "ATTR_INCIDENT_ID",
    "ATTR_LOOP_RUN_ID",
    "ATTR_LOOP_PASS_INDEX",
    "ATTR_LOOP_SCHEMA_VERSION",
    "ATTR_LOOP_POLICY_SCHEMA_VERSION",
    "ATTR_LOOP_MAX_PASSES",
    "ATTR_LOOP_MAX_CHECKS_PER_PASS",
    "ATTR_LOOP_MAX_TOTAL_CHECKS",
    "ATTR_LOOP_BUDGET_EXCEEDED",
    "ATTR_LOOP_STOP_REASON",
    "ATTR_LOOP_DECISION",
    "ATTR_LOOP_RUNNER_KIND",
    "ATTR_CHECKS_PROPOSED",
    "ATTR_CHECKS_ACCEPTED",
    "ATTR_CHECKS_REJECTED",
    "ATTR_CHECKS_REJECTED_MUTATING",
    "ATTR_CHECKS_REJECTED_SENSITIVE",
    "ATTR_CHECKS_REJECTED_DUPLICATE",
    "ATTR_CHECKS_REJECTED_BUDGET",
    "ATTR_EVIDENCE_NEW_COUNT",
    "ATTR_ARTIFACT_PATH",
    "ATTR_ARTIFACT_SCHEMA_VALID",
    "ATTR_ARTIFACT_SCHEMA_MISSING_COUNT",
    # Event names
    "EVENT_BUDGET_EXCEEDED",
    "EVENT_CHECK_REJECTED",
    "EVENT_CHECKS_EXECUTED",
    "EVENT_ARTIFACT_WRITTEN",
    "EVENT_LOOP_STOP",
    # Span context
    "SpanContext",
    # Core helpers
    "start_span",
    # High-level helpers
    "start_loop_span",
    "start_pass_span",
    "start_budget_span",
    "start_plan_span",
    "start_gate_span",
    "start_execute_span",
    "start_artifact_span",
    # Event helpers
    "emit_budget_exceeded_event",
    "emit_check_rejected_event",
    "emit_checks_executed_event",
    "emit_artifact_written_event",
    "emit_stop_event",
    # Legacy helpers
    "record_exception",
    "set_span_ok",
    "set_span_error",
    # Legacy API
    "emit_loop_span",
    "emit_pass_span",
    "emit_check_gate_span",
]
