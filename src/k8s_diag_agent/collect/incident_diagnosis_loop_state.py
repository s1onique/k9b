"""State management for incident diagnosis loop.

This module contains pure state helper functions.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from datetime import UTC, datetime

from .incident_diagnosis_loop_models import (
    DiagnosisPass,
    LoopState,
    StopReason,
)
from .incident_next_check_policy_registry import DISALLOWED_ACTIONS

# =============================================================================
# State Helpers
# =============================================================================


def create_initial_loop_state(
    incident_id: str,
    *,
    now: datetime | None = None,
    max_passes: int = 3,
    max_checks_per_pass: int = 5,
    max_total_checks: int = 15,
) -> LoopState:
    """Create initial loop state for a diagnosis session.

    Args:
        incident_id: The incident to diagnose
        now: Optional datetime for deterministic timestamps
        max_passes: Maximum diagnosis passes
        max_checks_per_pass: Maximum checks per pass
        max_total_checks: Maximum total checks across all passes

    Returns:
        Initial LoopState
    """
    from .incident_diagnosis_loop_models import LOOP_SCHEMA_VERSION

    timestamp = now if now is not None else datetime.now(UTC)
    timestamp_str = timestamp.isoformat()

    return LoopState(
        schema_version=LOOP_SCHEMA_VERSION,
        incident_id=incident_id,
        started_at=timestamp_str,
        updated_at=timestamp_str,
        read_only=True,
        allowed_actions=(),
        disallowed_actions=tuple(DISALLOWED_ACTIONS),
        pass_budget={
            "max_passes": max_passes,
            "current_pass": 1,
            "max_checks_per_pass": max_checks_per_pass,
            "max_total_checks": max_total_checks,
        },
        passes=(),
        status="running",
        stop_reason=None,
        total_checks_planned=0,
    )


def increment_pass(state: LoopState, now: datetime | None = None) -> LoopState:
    """Increment pass counter in loop state.

    Args:
        state: Current loop state
        now: Optional datetime for timestamp

    Returns:
        New LoopState with incremented pass
    """
    timestamp = now if now is not None else datetime.now(UTC)
    timestamp_str = timestamp.isoformat()

    budget = dict(state.pass_budget)
    new_pass = budget["current_pass"] + 1
    budget["current_pass"] = new_pass

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp_str,
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=budget,
        passes=state.passes,
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned,
    )


def add_pass_to_state(
    state: LoopState,
    diagnosis_pass: DiagnosisPass | dict[str, object],
    *,
    now: datetime | None = None,
) -> LoopState:
    """Add a completed pass to loop state.

    Args:
        state: Current loop state
        diagnosis_pass: Completed diagnosis pass
        now: Optional datetime for deterministic timestamps

    Returns:
        New LoopState with pass added
    """
    timestamp = now if now is not None else datetime.now(UTC)

    # Convert to DiagnosisPass if dict
    if isinstance(diagnosis_pass, dict):
        diagnosis_pass = DiagnosisPass.from_dict(diagnosis_pass)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes + (diagnosis_pass,),
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned,
    )


def stop_loop(
    state: LoopState,
    stop_reason: StopReason,
    *,
    now: datetime | None = None,
) -> LoopState:
    """Stop the loop with a reason.

    Args:
        state: Current loop state
        stop_reason: Reason for stopping
        now: Optional datetime for deterministic timestamps

    Returns:
        New LoopState with status=stopped
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes,
        status="stopped",
        stop_reason=stop_reason.value,
        total_checks_planned=state.total_checks_planned,
    )


def record_planned_checks(
    state: LoopState,
    count: int,
    *,
    now: datetime | None = None,
) -> LoopState:
    """Record planned checks in loop state.

    Args:
        state: Current loop state
        count: Number of checks being planned
        now: Optional datetime for timestamp

    Returns:
        New LoopState with updated total_checks_planned
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return LoopState(
        schema_version=state.schema_version,
        incident_id=state.incident_id,
        started_at=state.started_at,
        updated_at=timestamp.isoformat(),
        read_only=state.read_only,
        allowed_actions=state.allowed_actions,
        disallowed_actions=state.disallowed_actions,
        pass_budget=state.pass_budget,
        passes=state.passes,
        status=state.status,
        stop_reason=state.stop_reason,
        total_checks_planned=state.total_checks_planned + count,
    )


__all__ = [
    "create_initial_loop_state",
    "increment_pass",
    "add_pass_to_state",
    "stop_loop",
    "record_planned_checks",
]
