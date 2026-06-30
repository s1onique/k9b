"""OTel span helpers for diagnosis loop runtime.

This module provides OpenTelemetry span/event emission helpers that can be wired
to the actual OTel infrastructure when deployed. The helpers degrade safely
if OTel is unavailable or no provider is configured.

Usage:
    - Import helpers from this module
    - Call helpers in the diagnosis loop runtime
    - Application/deployment owns exporter configuration
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
)

if TYPE_CHECKING:
    pass

# =============================================================================
# OTel Import with Graceful Degradation
# =============================================================================

_trace: Any = None
_status_OK: Any = None
_status_ERROR: Any = None
_STATUS_CODES_AVAILABLE: bool = False

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    _trace = trace
    _status_OK = StatusCode.OK
    _status_ERROR = StatusCode.ERROR
    _STATUS_CODES_AVAILABLE = True
except ImportError:
    # OTel not available - helpers will be no-ops
    pass


# =============================================================================
# Span Names (k9b namespace)
# =============================================================================

SPAN_LOOP_RUN = "k9b.diagnosis_loop.run"
SPAN_LOOP_PASS = "k9b.diagnosis_loop.pass"
SPAN_LOOP_BUDGET = "k9b.diagnosis_loop.budget"
SPAN_LOOP_PLAN = "k9b.diagnosis_loop.plan"
SPAN_LOOP_GATE = "k9b.diagnosis_loop.gate"
SPAN_LOOP_EXECUTE = "k9b.diagnosis_loop.execute"
SPAN_LOOP_ARTIFACT = "k9b.diagnosis_loop.artifact"
SPAN_LOOP_STOP = "k9b.diagnosis_loop.stop"

# =============================================================================
# Attribute Keys (k9b namespace)
# =============================================================================

ATTR_INCIDENT_ID = "k9b.incident.id"
ATTR_LOOP_RUN_ID = "k9b.loop.run_id"
ATTR_LOOP_PASS_INDEX = "k9b.loop.pass_index"
ATTR_LOOP_SCHEMA_VERSION = "k9b.loop.schema_version"
ATTR_LOOP_POLICY_SCHEMA_VERSION = "k9b.loop.policy.schema_version"
ATTR_LOOP_MAX_PASSES = "k9b.loop.max_passes"
ATTR_LOOP_MAX_CHECKS_PER_PASS = "k9b.loop.max_checks_per_pass"
ATTR_LOOP_MAX_TOTAL_CHECKS = "k9b.loop.max_total_checks"
ATTR_LOOP_BUDGET_EXCEEDED = "k9b.loop.budget_exceeded"
ATTR_LOOP_STOP_REASON = "k9b.loop.stop_reason"
ATTR_LOOP_DECISION = "k9b.loop.decision"
ATTR_LOOP_RUNNER_KIND = "k9b.loop.runner_kind"

# Gate attributes
ATTR_CHECKS_PROPOSED = "k9b.loop.checks.proposed"
ATTR_CHECKS_ACCEPTED = "k9b.loop.checks.accepted"
ATTR_CHECKS_REJECTED = "k9b.loop.checks.rejected"
ATTR_CHECKS_REJECTED_MUTATING = "k9b.loop.checks.rejected_mutating"
ATTR_CHECKS_REJECTED_SENSITIVE = "k9b.loop.checks.rejected_sensitive"
ATTR_CHECKS_REJECTED_DUPLICATE = "k9b.loop.checks.rejected_duplicate"
ATTR_CHECKS_REJECTED_BUDGET = "k9b.loop.checks.rejected_budget"

# Execution/artifact attributes
ATTR_EVIDENCE_NEW_COUNT = "k9b.loop.evidence.new_count"
ATTR_ARTIFACT_PATH = "k9b.loop.artifact.path"
ATTR_ARTIFACT_SCHEMA_VALID = "k9b.loop.artifact.schema_valid"
ATTR_ARTIFACT_SCHEMA_MISSING_COUNT = "k9b.loop.artifact.schema_missing_count"

# Event names
EVENT_BUDGET_EXCEEDED = "k9b.diagnosis_loop.budget_exceeded"
EVENT_CHECK_REJECTED = "k9b.diagnosis_loop.check_rejected"
EVENT_CHECKS_EXECUTED = "k9b.diagnosis_loop.checks_executed"
EVENT_ARTIFACT_WRITTEN = "k9b.diagnosis_loop.artifact_written"
EVENT_LOOP_STOP = "k9b.diagnosis_loop.stop"


# =============================================================================
# Span Context Holder (for nested span management)
# =============================================================================

@dataclass
class SpanContext:
    """Context holder for span management.

    Provides a stable interface regardless of whether OTel is available.
    """
    name: str
    span: Any = None  # Will be Span or None

    def __enter__(self) -> "SpanContext":
        if self.span is not None:
            self.span.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.span is not None:
            self.span.__exit__(exc_type, exc_val, exc_tb)


# =============================================================================
# Core Span Helpers
# =============================================================================

def _get_tracer() -> Any:
    """Get the OTel tracer if available."""
    if _trace is None:
        return None
    try:
        return _trace.get_tracer(__name__)
    except Exception:
        return None


def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> SpanContext:
    """Start a span with the given name and attributes.

    This is a safe wrapper that degrades gracefully if OTel is unavailable.

    Args:
        name: Span name (e.g., "k9b.diagnosis_loop.run")
        attributes: Optional span attributes

    Returns:
        SpanContext that can be used as a context manager
    """
    tracer = _get_tracer()
    if tracer is None:
        return SpanContext(name=name)

    try:
        span = tracer.start_span(name)
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        return SpanContext(name=name, span=span)
    except Exception:
        return SpanContext(name=name)


def end_span(span: Any, status: Any = None) -> None:
    """End a span and optionally set its status.

    Safe to call even if span is None or OTel is unavailable.
    """
    if span is None or not hasattr(span, 'end'):
        return
    try:
        if status is not None:
            span.set_status(status)
        span.end()
    except Exception:
        pass


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


def add_span_event(
    span: Any,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Add an event to a span.

    Safe to call even if span is None or OTel is unavailable.
    """
    if span is None or not hasattr(span, 'add_event'):
        return
    try:
        span.add_event(name, attributes=attributes)
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


# =============================================================================
# High-Level Loop Span Helpers
# =============================================================================

def start_loop_span(
    run_id: str,
    incident_id: str,
    policy: DiagnosisLoopPolicy,
) -> SpanContext:
    """Start the loop run span.

    Args:
        run_id: Unique identifier for this loop run
        incident_id: The incident being diagnosed
        policy: The policy in effect

    Returns:
        SpanContext for the loop run span
    """
    attributes = {
        ATTR_INCIDENT_ID: incident_id,
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_POLICY_SCHEMA_VERSION: policy.schema_version,
        ATTR_LOOP_MAX_PASSES: policy.max_passes,
        ATTR_LOOP_MAX_CHECKS_PER_PASS: policy.max_checks_per_pass,
        ATTR_LOOP_MAX_TOTAL_CHECKS: policy.max_total_checks,
    }
    return start_span(SPAN_LOOP_RUN, attributes)


def start_pass_span(
    run_id: str,
    pass_index: int,
    decision: str,
    stop_reason: str | None,
    checks_accepted: int,
    checks_rejected: int,
) -> SpanContext:
    """Start the pass span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number (1-based)
        decision: The loop decision
        stop_reason: The stop reason if stopped
        checks_accepted: Number of checks accepted
        checks_rejected: Number of checks rejected

    Returns:
        SpanContext for the pass span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_LOOP_DECISION: decision,
        ATTR_LOOP_STOP_REASON: stop_reason,
        ATTR_CHECKS_ACCEPTED: checks_accepted,
        ATTR_CHECKS_REJECTED: checks_rejected,
    }
    return start_span(SPAN_LOOP_PASS, attributes)


def start_budget_span(
    run_id: str,
    pass_index: int,
    budget_exceeded: bool,
    stop_reason: str | None,
) -> SpanContext:
    """Start the budget span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        budget_exceeded: Whether budget was exceeded
        stop_reason: The stop reason if exceeded

    Returns:
        SpanContext for the budget span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_LOOP_BUDGET_EXCEEDED: budget_exceeded,
        ATTR_LOOP_STOP_REASON: stop_reason,
    }
    return start_span(SPAN_LOOP_BUDGET, attributes)


def start_plan_span(
    run_id: str,
    pass_index: int,
) -> SpanContext:
    """Start the planner span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number

    Returns:
        SpanContext for the planner span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
    }
    return start_span(SPAN_LOOP_PLAN, attributes)


def start_gate_span(
    run_id: str,
    pass_index: int,
    proposed: int,
    accepted: int,
    rejected_mutating: int,
    rejected_sensitive: int,
    rejected_duplicate: int,
    rejected_budget: int = 0,
) -> SpanContext:
    """Start the gate span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        proposed: Total proposed checks
        accepted: Number of accepted checks
        rejected_mutating: Number rejected for mutating
        rejected_sensitive: Number rejected for sensitive
        rejected_duplicate: Number rejected for duplicate
        rejected_budget: Number rejected for budget

    Returns:
        SpanContext for the gate span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_CHECKS_PROPOSED: proposed,
        ATTR_CHECKS_ACCEPTED: accepted,
        ATTR_CHECKS_REJECTED: rejected_mutating + rejected_sensitive + rejected_duplicate + rejected_budget,
        ATTR_CHECKS_REJECTED_MUTATING: rejected_mutating,
        ATTR_CHECKS_REJECTED_SENSITIVE: rejected_sensitive,
        ATTR_CHECKS_REJECTED_DUPLICATE: rejected_duplicate,
        ATTR_CHECKS_REJECTED_BUDGET: rejected_budget,
    }
    return start_span(SPAN_LOOP_GATE, attributes)


def start_execute_span(
    run_id: str,
    pass_index: int,
    checks_count: int,
    runner_kind: str = "read_only",
) -> SpanContext:
    """Start the execution span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        checks_count: Number of checks to execute
        runner_kind: Kind of runner ("read_only", "golden_case")

    Returns:
        SpanContext for the execution span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_CHECKS_ACCEPTED: checks_count,
        ATTR_LOOP_RUNNER_KIND: runner_kind,
    }
    return start_span(SPAN_LOOP_EXECUTE, attributes)


def start_artifact_span(
    run_id: str,
    pass_index: int,
    artifact_path: str | None,
    schema_valid: bool,
    missing_fields: int,
    new_evidence_count: int,
) -> SpanContext:
    """Start the artifact span.

    Args:
        run_id: Unique identifier for this loop run
        pass_index: The pass number
        artifact_path: Path to the artifact file
        schema_valid: Whether the artifact schema is valid
        missing_fields: Number of missing required fields
        new_evidence_count: Number of new evidence items

    Returns:
        SpanContext for the artifact span
    """
    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_ARTIFACT_PATH: artifact_path,
        ATTR_ARTIFACT_SCHEMA_VALID: schema_valid,
        ATTR_ARTIFACT_SCHEMA_MISSING_COUNT: missing_fields,
        ATTR_EVIDENCE_NEW_COUNT: new_evidence_count,
    }
    return start_span(SPAN_LOOP_ARTIFACT, attributes)


# =============================================================================
# Event Helpers
# =============================================================================

def emit_budget_exceeded_event(span: Any, stop_reason: str) -> None:
    """Emit a budget exceeded event on the span.

    Args:
        span: The span to emit the event on
        stop_reason: The reason for budget exhaustion
    """
    add_span_event(span, EVENT_BUDGET_EXCEEDED, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


def emit_check_rejected_event(
    span: Any,
    check_id: str,
    rejection_reason: str,
    is_unsafe: bool = False,
    is_sensitive: bool = False,
) -> None:
    """Emit a check rejected event on the span.

    Only includes bounded details - no raw check output or secrets.

    Args:
        span: The span to emit the event on
        check_id: The check that was rejected
        rejection_reason: Reason for rejection
        is_unsafe: Whether the check was unsafe
        is_sensitive: Whether the check was sensitive
    """
    add_span_event(span, EVENT_CHECK_REJECTED, {
        "check_id": check_id,
        "rejection_reason": rejection_reason,
        "is_unsafe": is_unsafe,
        "is_sensitive": is_sensitive,
    })


def emit_checks_executed_event(span: Any, count: int) -> None:
    """Emit a checks executed event on the span.

    Args:
        span: The span to emit the event on
        count: Number of checks executed
    """
    add_span_event(span, EVENT_CHECKS_EXECUTED, {
        ATTR_CHECKS_ACCEPTED: count,
    })


def emit_artifact_written_event(
    span: Any,
    artifact_path: str,
    schema_valid: bool,
) -> None:
    """Emit an artifact written event on the span.

    Args:
        span: The span to emit the event on
        artifact_path: Path to the written artifact
        schema_valid: Whether the artifact schema is valid
    """
    add_span_event(span, EVENT_ARTIFACT_WRITTEN, {
        ATTR_ARTIFACT_PATH: artifact_path,
        ATTR_ARTIFACT_SCHEMA_VALID: schema_valid,
    })


def emit_stop_event(span: Any, stop_reason: str) -> None:
    """Emit a stop event on the span.

    Args:
        span: The span to emit the event on
        stop_reason: The stop reason
    """
    add_span_event(span, EVENT_LOOP_STOP, {
        ATTR_LOOP_STOP_REASON: stop_reason,
    })


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
        current_span = _trace.get_current_span()
        if current_span is None:
            return

        if event == "started":
            current_span.set_attribute(ATTR_INCIDENT_ID, incident_id)
            current_span.set_attribute(ATTR_LOOP_RUN_ID, run_id)
            current_span.set_attribute(ATTR_LOOP_MAX_PASSES, policy.max_passes)
            current_span.set_attribute(ATTR_LOOP_MAX_CHECKS_PER_PASS, policy.max_checks_per_pass)
        elif event == "completed":
            add_span_event(current_span, "k9b.diagnosis_loop.completed")
        elif event == "failed":
            add_span_event(current_span, "k9b.diagnosis_loop.failed")
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
        current_span = _trace.get_current_span()
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
            current_span = _trace.get_current_span()
            if current_span is None:
                return

            emit_check_rejected_event(
                current_span,
                check_id=check_id,
                rejection_reason=rejection_reason,
                is_unsafe=(rejection_reason == "mutating_check_rejected"),
                is_sensitive=(rejection_reason == "sensitive_read_denied"),
            )
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
    "end_span",
    "record_exception",
    "add_span_event",
    "set_span_ok",
    "set_span_error",
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
    # Legacy API
    "emit_loop_span",
    "emit_pass_span",
    "emit_check_gate_span",
]
