"""Diagnosis loop helpers for incident store.

Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_lifecycle import Incident


def mark_diagnosis_loop_started_for_store(
    store: IncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
) -> Incident | None:
    """Mark that automatic diagnosis loop started for an incident.

    Safe metadata only - no raw packet contents, logs, or stack traces.

    Args:
        store: The incident store
        incident_id: ID of the incident
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID
    Returns:
        Updated incident snapshot, or None if not found
    """
    from .incident_diagnosis_loop_store_helpers import mark_diagnosis_loop_started as _helper

    updated = _helper(store, incident_id, run_id, collector_run_id)
    return store._snapshot_incident(updated) if updated else None


def mark_diagnosis_loop_completed_for_store(
    store: IncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    review_packet_name: str | None = None,
    checks_requested: int = 0,
    checks_run: int = 0,
    checks_rejected: int = 0,
    decision: str | None = None,
) -> Incident | None:
    """Mark that automatic diagnosis loop completed successfully.

    Safe metadata only - no raw packet contents, logs, or stack traces.

    Args:
        store: The incident store
        incident_id: ID of the incident
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID
        review_packet_name: Optional review packet filename
        checks_requested: Number of checks requested
        checks_run: Number of checks actually run
        checks_rejected: Number of checks rejected
        decision: The terminal decision from the policy-enforced loop pass
    Returns:
        Updated incident snapshot, or None if not found
    """
    from .incident_diagnosis_loop_store_helpers import mark_diagnosis_loop_completed as _helper

    updated = _helper(
        store, incident_id, run_id, collector_run_id,
        review_packet_name, checks_requested, checks_run, checks_rejected,
        decision=decision,
    )
    return store._snapshot_incident(updated) if updated else None


def mark_diagnosis_loop_failed_for_store(
    store: IncidentStore,
    incident_id: str,
    run_id: str | None = None,
    collector_run_id: str | None = None,
    unavailable_reason: str | None = None,
) -> Incident | None:
    """Mark that automatic diagnosis loop failed or produced unavailable state.

    Safe metadata only - no raw packet contents, logs, stack traces, or prompts.

    Args:
        store: The incident store
        incident_id: ID of the incident
        run_id: Optional run_id for the failed pass
        collector_run_id: Optional batch collector run ID
        unavailable_reason: Safe reason code
    Returns:
        Updated incident snapshot, or None if not found
    """
    from .incident_diagnosis_loop_store_helpers import mark_diagnosis_loop_failed as _helper

    updated = _helper(store, incident_id, run_id, collector_run_id, unavailable_reason)
    return store._snapshot_incident(updated) if updated else None


# Import type alias for type checking
if TYPE_CHECKING:
    from .incident_store import IncidentStore


__all__ = [
    "mark_diagnosis_loop_started_for_store",
    "mark_diagnosis_loop_completed_for_store",
    "mark_diagnosis_loop_failed_for_store",
]
