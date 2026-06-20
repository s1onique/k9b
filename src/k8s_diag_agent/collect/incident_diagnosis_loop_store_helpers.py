"""Diagnosis loop event helpers for incident store.

This module provides store-level methods for emitting diagnosis loop lifecycle events.
Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.

Public API:
    mark_diagnosis_loop_started
    mark_diagnosis_loop_completed
    mark_diagnosis_loop_failed
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_lifecycle import Incident
    from .incident_store import IncidentStore


def mark_diagnosis_loop_started(
    store: IncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
) -> Incident | None:
    """Mark that automatic diagnosis loop started for an incident.

    Args:
        store: IncidentStore instance
        incident_id: ID of the incident
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID

    Returns:
        Updated incident or None if not found
    """
    from .incident_transitions import mark_diagnosis_loop_started as _mark_diagnosis_loop_started

    incident = store.get_incident(incident_id)
    if incident is None:
        return None

    updated = _mark_diagnosis_loop_started(incident, run_id, collector_run_id)
    store._incidents[incident_id] = updated
    return updated


def mark_diagnosis_loop_completed(
    store: IncidentStore,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    review_packet_name: str | None = None,
    checks_requested: int = 0,
    checks_run: int = 0,
    checks_rejected: int = 0,
) -> Incident | None:
    """Mark that automatic diagnosis loop completed successfully.

    Args:
        store: IncidentStore instance
        incident_id: ID of the incident
        run_id: The run_id for this diagnosis loop pass
        collector_run_id: The batch collector run ID
        review_packet_name: Optional review packet filename
        checks_requested: Number of checks requested
        checks_run: Number of checks actually run
        checks_rejected: Number of checks rejected

    Returns:
        Updated incident or None if not found
    """
    from .incident_transitions import mark_diagnosis_loop_completed as _mark_diagnosis_loop_completed

    incident = store.get_incident(incident_id)
    if incident is None:
        return None

    updated = _mark_diagnosis_loop_completed(
        incident,
        run_id,
        collector_run_id,
        review_packet_name=review_packet_name,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_rejected=checks_rejected,
    )
    store._incidents[incident_id] = updated
    return updated


def mark_diagnosis_loop_failed(
    store: IncidentStore,
    incident_id: str,
    run_id: str | None = None,
    collector_run_id: str | None = None,
    unavailable_reason: str | None = None,
) -> Incident | None:
    """Mark that automatic diagnosis loop failed or produced unavailable state.

    Args:
        store: IncidentStore instance
        incident_id: ID of the incident
        run_id: Optional run_id for the failed pass
        collector_run_id: Optional batch collector run ID
        unavailable_reason: Safe reason code (e.g., "unsafe_run_id", "case_file_error")

    Returns:
        Updated incident or None if not found
    """
    from .incident_transitions import mark_diagnosis_loop_failed as _mark_diagnosis_loop_failed

    incident = store.get_incident(incident_id)
    if incident is None:
        return None

    updated = _mark_diagnosis_loop_failed(
        incident,
        run_id=run_id,
        collector_run_id=collector_run_id,
        unavailable_reason=unavailable_reason,
    )
    store._incidents[incident_id] = updated
    return updated


__all__ = [
    "mark_diagnosis_loop_started",
    "mark_diagnosis_loop_completed",
    "mark_diagnosis_loop_failed",
]
