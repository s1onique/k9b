"""OTel span helpers for diagnosis loop instrumentation.

This module provides OpenTelemetry span helpers that use the start_as_current_span
pattern to ensure proper lifecycle management:
- Spans are automatically ended when exiting the context
- Nested spans are properly scoped as the current span
- Telemetry degrades gracefully when OTel is unavailable

The start_as_current_span pattern is the recommended approach in OpenTelemetry
Python SDK documentation, as it ensures spans are properly nested and ended.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
)

from .otel_constants import (
    ATTR_CHECKS_ACCEPTED,
    ATTR_CHECKS_PROPOSED,
    ATTR_CHECKS_REJECTED,
    ATTR_CHECKS_REJECTED_BUDGET,
    ATTR_CHECKS_REJECTED_DUPLICATE,
    ATTR_CHECKS_REJECTED_MUTATING,
    ATTR_CHECKS_REJECTED_SENSITIVE,
    ATTR_LOOP_BUDGET_EXCEEDED,
    ATTR_LOOP_DECISION,
    ATTR_LOOP_MAX_CHECKS_PER_PASS,
    ATTR_LOOP_MAX_PASSES,
    ATTR_LOOP_MAX_TOTAL_CHECKS,
    ATTR_LOOP_PASS_INDEX,
    ATTR_LOOP_POLICY_SCHEMA_VERSION,
    ATTR_LOOP_RUN_ID,
    ATTR_LOOP_RUNNER_KIND,
    ATTR_LOOP_STOP_REASON,
    SPAN_LOOP_ARTIFACT,
    SPAN_LOOP_BUDGET,
    SPAN_LOOP_EXECUTE,
    SPAN_LOOP_GATE,
    SPAN_LOOP_PASS,
    SPAN_LOOP_PLAN,
    SPAN_LOOP_RUN,
)
from .otel_span_context import SpanContext

if TYPE_CHECKING:
    pass


# =============================================================================
# OTel Import with Graceful Degradation
# =============================================================================

_trace: Any = None

try:
    from opentelemetry import trace

    _trace = trace
except ImportError:
    # OTel not available - helpers will be no-ops
    pass


# =============================================================================
# Tracer Access
# =============================================================================


def _get_tracer() -> Any:
    """Get the OTel tracer if available."""
    if _trace is None:
        return None
    try:
        return _trace.get_tracer(__name__)
    except Exception:
        return None


# =============================================================================
# Core Span Helper
# =============================================================================


def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> SpanContext:
    """Start a span using start_as_current_span pattern.

    This uses the OpenTelemetry recommended pattern that:
    - Sets the span as the current span
    - Automatically ends the span on context exit
    - Properly restores the previous current span

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
        # Use start_as_current_span for proper lifecycle management
        # This sets the span as current and ends it on exit
        manager = tracer.start_as_current_span(
            name,
            attributes=attributes or {},
            end_on_exit=True,
        )
        return SpanContext(name=name, manager=manager)
    except Exception:
        return SpanContext(name=name)


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
    from .otel_constants import (
        ATTR_ARTIFACT_PATH,
        ATTR_ARTIFACT_SCHEMA_MISSING_COUNT,
        ATTR_ARTIFACT_SCHEMA_VALID,
        ATTR_EVIDENCE_NEW_COUNT,
    )

    attributes = {
        ATTR_LOOP_RUN_ID: run_id,
        ATTR_LOOP_PASS_INDEX: pass_index,
        ATTR_ARTIFACT_PATH: artifact_path,
        ATTR_ARTIFACT_SCHEMA_VALID: schema_valid,
        ATTR_ARTIFACT_SCHEMA_MISSING_COUNT: missing_fields,
        ATTR_EVIDENCE_NEW_COUNT: new_evidence_count,
    }
    return start_span(SPAN_LOOP_ARTIFACT, attributes)


__all__ = [
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
]
