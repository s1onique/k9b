"""Automatic diagnosis loop summary projection for incident detail.

This module provides a read-only summary of the latest automatic diagnosis
loop run for an incident, derived from incident timeline events and existing
automatic diagnosis review metadata.

The summary exposes:
- Status: not_run | running_or_started | completed | failed_or_unavailable
- Timestamps for latest events
- Check counts when available
- Review packet availability
- Safety flags (always true)

Hard constraints enforced:
- NO remediation actions
- NO raw packet contents
- NO raw event data
- NO logs, stdout/stderr, stack traces
- NO kubectl/Helm command text
- NO arbitrary exception text

Design notes:
- "Latest" is based on occurred_at, not input list order
- Unknown/malformed metadata is ignored safely (null returned)
- All fields are optional/null-safe where backend can omit
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .api_payloads_incident_reads import (
        AutomaticDiagnosisLoopSummary,
        IncidentEventPayload,
    )


# =============================================================================
# Status literal type (matches AutomaticDiagnosisLoopSummary TypedDict)
# =============================================================================

DiagnosisLoopStatusLiteral = Literal[
    "not_run",
    "running_or_started",
    "completed",
    "failed_or_unavailable",
]


class DiagnosisLoopStatus:
    """Status values for automatic diagnosis loop summary."""

    NOT_RUN: DiagnosisLoopStatusLiteral = "not_run"
    RUNNING_OR_STARTED: DiagnosisLoopStatusLiteral = "running_or_started"
    COMPLETED: DiagnosisLoopStatusLiteral = "completed"
    FAILED_OR_UNAVAILABLE: DiagnosisLoopStatusLiteral = "failed_or_unavailable"


# =============================================================================
# Diagnosis loop event types (from incident_events.py)
# =============================================================================

_DIAGNOSIS_LOOP_STARTED = "diagnosis_loop_started"
_DIAGNOSIS_LOOP_COMPLETED = "diagnosis_loop_completed"
_DIAGNOSIS_LOOP_FAILED = "diagnosis_loop_failed"


# =============================================================================
# Constants for field bounds (safety)
# =============================================================================

MAX_EVENT_ID_LENGTH = 200
MAX_EVENT_TYPE_LENGTH = 50
MAX_REASON_LENGTH = 200


# =============================================================================
# Helper functions
# =============================================================================


def _is_diagnosis_loop_event(event_type: str) -> bool:
    """Check if an event type is a diagnosis loop lifecycle event."""
    return event_type in (
        _DIAGNOSIS_LOOP_STARTED,
        _DIAGNOSIS_LOOP_COMPLETED,
        _DIAGNOSIS_LOOP_FAILED,
    )


def _get_event_status(event_type: str) -> DiagnosisLoopStatusLiteral | None:
    """Map diagnosis loop event type to status.

    Returns None for non-diagnosis-loop event types.
    """
    if event_type == _DIAGNOSIS_LOOP_STARTED:
        return DiagnosisLoopStatus.RUNNING_OR_STARTED
    if event_type == _DIAGNOSIS_LOOP_COMPLETED:
        return DiagnosisLoopStatus.COMPLETED
    if event_type == _DIAGNOSIS_LOOP_FAILED:
        return DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
    return None


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse a datetime value from various formats.

    Handles:
    - datetime objects (returned as-is)
    - ISO format strings (parsed)
    - None or empty strings (returns None)
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _bound_string(value: str | None, max_length: int) -> str | None:
    """Bound a string to a maximum length for safety."""
    if value is None:
        return None
    return value[:max_length]


def _extract_timestamp(event_data: dict[str, object] | None, key: str) -> str | None:
    """Extract and format a timestamp from event data.

    Returns ISO format string or None if not present/invalid.
    """
    if event_data is None:
        return None
    value = event_data.get(key)
    if value is None:
        return None
    # Only call _parse_datetime if value is a string or datetime
    if isinstance(value, str):
        dt = _parse_datetime(value)
        if dt is None:
            return None
        return dt.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _extract_int(event_data: dict[str, object] | None, key: str) -> int | None:
    """Extract an integer from event data.

    Returns None if not present or not a valid integer.
    """
    if event_data is None:
        return None
    value = event_data.get(key)
    if value is None:
        return None
    return _safe_get_int(value)


def _extract_reason(event_data: dict[str, object] | None) -> str | None:
    """Extract unavailable_reason from event data.

    Returns bounded reason string or None if not present.
    """
    if event_data is None:
        return None
    reason = event_data.get("unavailable_reason")
    if reason is None:
        return None
    return _bound_string(str(reason), MAX_REASON_LENGTH)


# =============================================================================

# =============================================================================
# Type-guard helpers for dict access
# =============================================================================


def _safe_get_str(value: object) -> str | None:
    """Safely extract a string from a dict value."""
    if isinstance(value, str):
        return value
    return None


def _safe_get_int(value: object) -> int | None:
    """Safely extract an integer from a dict value."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


# Main summary builder
# =============================================================================


def build_automatic_diagnosis_loop_summary(
    events: Sequence[IncidentEventPayload],
    review_packet_available: bool,
    review_packet_id: str | None = None,
) -> AutomaticDiagnosisLoopSummary:
    """Build AutomaticDiagnosisLoopSummary from incident events and review state.

    This function derives a read-only summary of the latest automatic diagnosis
    loop run from existing incident timeline events and review metadata.

    Each diagnosis_loop_completed event represents one observable pass; its run_id
    is accumulated into pass_run_ids for multi-pass validation.

    Args:
        events: List of incident timeline events (serialized as dicts)
            Expected keys: event_id, event_type, occurred_at, data
        review_packet_available: Whether a review packet exists
        review_packet_id: Optional review packet identifier

    Returns:
        Dictionary with summary fields:
        - status: not_run | running_or_started | completed | failed_or_unavailable
        - latest_started_at: ISO timestamp or null
        - latest_completed_at: ISO timestamp or null
        - latest_failed_at: ISO timestamp or null
        - latest_event_id: Event ID or null
        - latest_event_type: Event type or null
        - unavailable_reason: Reason for failure/unavailability or null
        - checks_requested: Count or null
        - checks_run: Count or null
        - checks_rejected: Count or null
        - review_packet_available: Boolean
        - review_packet_id: ID string or null
        - read_only: Always True
        - review_required_before_any_action: Always True
        - no_remediation_attempted: Always True
        - pass_count: Number of completed passes
        - pass_run_ids: List of unique run_ids from completed passes
        - terminal_decision: Decision from latest completed pass

    Safety constraints enforced:
    - Only diagnosis_loop_started/completed/failed events are considered
    - Latest event is determined by occurred_at, not input order
    - All string fields are bounded
    - No raw event data is exposed
    - Safety flags are always True

    Hard constraints:
    - NO remediation actions
    - NO raw packet contents
    - NO raw event data
    - NO logs, stdout/stderr, stack traces
    """
    # Filter to only diagnosis loop lifecycle events
    diagnosis_events: list[tuple[datetime, IncidentEventPayload]] = []
    for event in events:
        event_type = event.get("event_type", "")
        if not _is_diagnosis_loop_event(event_type):
            continue

        occurred_at = event.get("occurred_at")
        dt = _parse_datetime(occurred_at)
        if dt is None:
            # Skip events with invalid/missing timestamps
            continue

        diagnosis_events.append((dt, event))

    # Handle empty state - no diagnosis loop events
    if not diagnosis_events:
        return {
            "status": DiagnosisLoopStatus.NOT_RUN,
            "latest_started_at": None,
            "latest_completed_at": None,
            "latest_failed_at": None,
            "latest_event_id": None,
            "latest_event_type": None,
            "unavailable_reason": None,
            "checks_requested": None,
            "checks_run": None,
            "checks_rejected": None,
            "review_packet_available": review_packet_available,
            "review_packet_id": review_packet_id,
            "read_only": True,
            "review_required_before_any_action": True,
            "no_remediation_attempted": True,
            "pass_count": None,
            "pass_run_ids": None,
            "terminal_decision": None,
        }

    # Sort by occurred_at descending to find latest event
    diagnosis_events.sort(key=lambda x: x[0], reverse=True)
    latest_dt, latest_event = diagnosis_events[0]

    # Extract event metadata
    latest_event_type = _bound_string(latest_event.get("event_type"), MAX_EVENT_TYPE_LENGTH)
    latest_event_id = _bound_string(latest_event.get("event_id"), MAX_EVENT_ID_LENGTH)

    # Determine status from event type
    status: DiagnosisLoopStatusLiteral = (
        _get_event_status(latest_event_type or "") or DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE
    )

    # Extract timestamps for each event type
    latest_started_at: str | None = None
    latest_completed_at: str | None = None
    latest_failed_at: str | None = None

    # Each completed event represents one observable pass.
    completed_run_ids: list[str] = []
    # Track terminal decision from the latest completed pass
    terminal_decision: str | None = None

    for dt, evt in diagnosis_events:
        et = evt.get("event_type", "")
        ts = dt.isoformat()
        if et == _DIAGNOSIS_LOOP_STARTED and latest_started_at is None:
            latest_started_at = ts
        elif et == _DIAGNOSIS_LOOP_COMPLETED:
            if latest_completed_at is None:
                latest_completed_at = ts
            # Accumulate run_id from each completed pass
            evt_data = evt.get("data")
            if evt_data:
                run_id = evt_data.get("run_id")
                if isinstance(run_id, str) and run_id:
                    completed_run_ids.append(run_id)
        elif et == _DIAGNOSIS_LOOP_FAILED and latest_failed_at is None:
            latest_failed_at = ts

    # Extract terminal decision from latest completed pass.
    if status == DiagnosisLoopStatus.COMPLETED:
        # Find the latest completed event to get its terminal decision
        for dt, evt in diagnosis_events:
            evt_type = evt.get("event_type", "")
            if evt_type == _DIAGNOSIS_LOOP_COMPLETED:
                evt_data = evt.get("data")
                if evt_data:
                    terminal_decision = evt_data.get("decision")
                    if terminal_decision is not None:
                        terminal_decision = _bound_string(str(terminal_decision), MAX_REASON_LENGTH)
                break

    # Extract unavailable_reason from failed events only
    unavailable_reason: str | None = None
    if status == DiagnosisLoopStatus.FAILED_OR_UNAVAILABLE:
        for dt, evt in diagnosis_events:
            evt_type = evt.get("event_type", "")
            if evt_type == _DIAGNOSIS_LOOP_FAILED:
                evt_data = evt.get("data")
                reason = _extract_reason(evt_data)
                if reason:
                    unavailable_reason = reason
                    break

    # Extract check counts from latest completed event
    checks_requested: int | None = None
    checks_run: int | None = None
    checks_rejected: int | None = None

    if status == DiagnosisLoopStatus.COMPLETED:
        for dt, evt in diagnosis_events:
            evt_type = evt.get("event_type", "")
            if evt_type == _DIAGNOSIS_LOOP_COMPLETED:
                evt_data = evt.get("data")
                checks_requested = _extract_int(evt_data, "checks_requested")
                checks_run = _extract_int(evt_data, "checks_run")
                checks_rejected = _extract_int(evt_data, "checks_rejected")
                break

    # Return accumulated pass_run_ids and pass_count.
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_run_ids: list[str] = []
    for rid in completed_run_ids:
        if rid not in seen:
            seen.add(rid)
            unique_run_ids.append(rid)

    return {
        "status": status,
        "latest_started_at": latest_started_at,
        "latest_completed_at": latest_completed_at,
        "latest_failed_at": latest_failed_at,
        "latest_event_id": latest_event_id,
        "latest_event_type": latest_event_type,
        "unavailable_reason": unavailable_reason,
        "checks_requested": checks_requested,
        "checks_run": checks_run,
        "checks_rejected": checks_rejected,
        "review_packet_available": review_packet_available,
        "review_packet_id": review_packet_id,
        "read_only": True,
        "review_required_before_any_action": True,
        "no_remediation_attempted": True,
        # P4c contract fields
        "pass_count": len(unique_run_ids) if unique_run_ids else None,
        "pass_run_ids": unique_run_ids if unique_run_ids else None,
        "terminal_decision": terminal_decision,
    }


__all__ = [
    "DiagnosisLoopStatus",
    "build_automatic_diagnosis_loop_summary",
]