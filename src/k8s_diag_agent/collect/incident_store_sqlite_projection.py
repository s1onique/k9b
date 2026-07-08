"""Projection management for SQLite incident store.

This module handles the incident_current projection - a rebuildable cache
of current incident state derived from the append-only incident_events table.

Design notes:
- incident_current is a projection/cache, not the source of truth
- It can be safely truncated and rebuilt
- Rebuild is deterministic - same events produce same state
- Projection updates happen atomically with event appends
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .incident_store_sqlite_events import (
    IncidentEventType,
    StoredEvent,
    parse_stored_event,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# =============================================================================
# Event-to-State Projection
# =============================================================================


def apply_event_to_state(
    state: dict[str, Any],
    event: StoredEvent,
) -> dict[str, Any]:
    """Apply an event to a state dict to produce new state.

    This function implements the event sourcing pattern for incidents.
    Each event type updates specific fields in the state.

    Args:
        state: Current state dict (mutated in place)
        event: Event to apply

    Returns:
        Updated state dict (same object as input)
    """
    payload = json.loads(event.payload_json) if event.payload_json else {}

    # Update aggregate metadata
    state["aggregate_version"] = event.aggregate_version
    state["last_event_seq"] = event.event_seq
    state["updated_at"] = datetime.now(UTC).isoformat()

    # Apply event-specific updates
    if event.event_type == IncidentEventType.OPENED:
        _apply_opened(state, payload, event)
    elif event.event_type == IncidentEventType.SIGNAL_OBSERVED:
        _apply_signal_observed(state, payload, event)
    elif event.event_type == IncidentEventType.UPDATED:
        _apply_updated(state, payload, event)
    elif event.event_type == IncidentEventType.COLLECTING_EVIDENCE_STARTED:
        _apply_collecting_evidence_started(state, payload, event)
    elif event.event_type == IncidentEventType.READY_FOR_REVIEW:
        _apply_ready_for_review(state, payload, event)
    elif event.event_type == IncidentEventType.INVESTIGATION_STARTED:
        _apply_investigation_started(state, payload, event)
    elif event.event_type == IncidentEventType.SUPPRESSED:
        _apply_suppressed(state, payload, event)
    elif event.event_type == IncidentEventType.MARKED_DUPLICATE:
        _apply_marked_duplicate(state, payload, event)
    elif event.event_type == IncidentEventType.RESOLVED:
        _apply_resolved(state, payload, event)
    elif event.event_type == IncidentEventType.EVIDENCE_ATTACHED:
        _apply_evidence_attached(state, payload, event)
    elif event.event_type == IncidentEventType.DIAGNOSIS_LOOP_STARTED:
        _apply_diagnosis_loop_started(state, payload, event)
    elif event.event_type == IncidentEventType.DIAGNOSIS_LOOP_COMPLETED:
        _apply_diagnosis_loop_completed(state, payload, event)
    elif event.event_type == IncidentEventType.DIAGNOSIS_LOOP_FAILED:
        _apply_diagnosis_loop_failed(state, payload, event)
    elif event.event_type == IncidentEventType.IMPORTED:
        _apply_imported(state, payload, event)

    return state


def _apply_opened(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.opened event."""
    state["incident_id"] = event.incident_id
    state["source_candidate_id"] = payload.get("source_candidate_id", "")
    state["namespace"] = payload.get("namespace", "")
    state["object_kind"] = payload.get("object_kind", "")
    state["object_name"] = payload.get("object_name", "")
    state["raw_object_kind"] = payload.get("raw_object_kind")
    state["candidate_class"] = payload.get("candidate_class", "")
    state["severity"] = payload.get("severity", "")
    state["status"] = "open"
    state["first_observed_at"] = payload.get("first_observed_at", event.occurred_at.isoformat())
    state["last_observed_at"] = payload.get("last_observed_at", event.occurred_at.isoformat())
    state["signal_count"] = payload.get("signal_count", 1)
    state["evidence_count"] = payload.get("evidence_count", 0)
    state["signals"] = payload.get("signals", [])
    state["evidence_links"] = payload.get("evidence_links", [])
    state["evidence_needed"] = payload.get("evidence_needed", [])
    state["latest_snapshot_bundle_id"] = payload.get("latest_snapshot_bundle_id")
    state["suppressed_reason"] = None
    state["duplicate_of"] = None
    state["resolved_at"] = None
    state["resolution_notes"] = None
    state["review_packet"] = {"status": "not_generated"}
    state["events"] = []


def _apply_signal_observed(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.signal_observed event."""
    state["last_observed_at"] = payload.get("last_observed_at", event.occurred_at.isoformat())
    state["signal_count"] = payload.get("signal_count", state.get("signal_count", 0) + 1)
    if "signals" in payload:
        state["signals"] = payload["signals"]


def _apply_updated(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.updated event."""
    if "severity" in payload:
        state["severity"] = payload["severity"]
    if "status" in payload:
        state["status"] = payload["status"]
    state["last_observed_at"] = payload.get("last_observed_at", event.occurred_at.isoformat())


def _apply_collecting_evidence_started(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.collecting_evidence_started event."""
    state["status"] = "collecting_evidence"
    state["latest_snapshot_bundle_id"] = payload.get("bundle_id")
    state["last_observed_at"] = payload.get("last_observed_at", event.occurred_at.isoformat())
    if "evidence_links" in payload:
        state["evidence_links"] = payload["evidence_links"]
    if "evidence_count" in payload:
        state["evidence_count"] = payload["evidence_count"]


def _apply_ready_for_review(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.ready_for_review event."""
    state["status"] = "ready_for_review"
    if "review_packet_id" in payload:
        state["review_packet"] = {
            "status": "generated",
            "id": payload["review_packet_id"],
        }


def _apply_investigation_started(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.investigation_started event."""
    state["status"] = "investigating"


def _apply_suppressed(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.suppressed event."""
    state["status"] = "suppressed"
    state["suppressed_reason"] = payload.get("reason")


def _apply_marked_duplicate(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.marked_duplicate event."""
    state["status"] = "duplicate"
    state["duplicate_of"] = payload.get("duplicate_of")


def _apply_resolved(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.resolved event."""
    state["status"] = "resolved"
    state["resolved_at"] = event.occurred_at.isoformat()
    state["resolution_notes"] = payload.get("notes")


def _apply_evidence_attached(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.evidence_attached event."""
    state["evidence_count"] = payload.get("evidence_count", state.get("evidence_count", 0) + 1)
    if "evidence_links" in payload:
        state["evidence_links"] = payload["evidence_links"]


def _apply_diagnosis_loop_started(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.diagnosis_loop_started event."""
    state["diagnosis_loop"] = {
        "status": "running",
        "run_id": payload.get("run_id"),
        "collector_run_id": payload.get("collector_run_id"),
        "started_at": event.occurred_at.isoformat(),
    }


def _apply_diagnosis_loop_completed(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.diagnosis_loop_completed event."""
    state["diagnosis_loop"] = {
        "status": "completed",
        "run_id": payload.get("run_id"),
        "collector_run_id": payload.get("collector_run_id"),
        "completed_at": event.occurred_at.isoformat(),
        "review_packet_name": payload.get("review_packet_name"),
        "checks_requested": payload.get("checks_requested", 0),
        "checks_run": payload.get("checks_run", 0),
        "checks_rejected": payload.get("checks_rejected", 0),
        "decision": payload.get("decision"),
    }


def _apply_diagnosis_loop_failed(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.diagnosis_loop_failed event."""
    state["diagnosis_loop"] = {
        "status": "failed",
        "run_id": payload.get("run_id"),
        "collector_run_id": payload.get("collector_run_id"),
        "failed_at": event.occurred_at.isoformat(),
        "unavailable_reason": payload.get("unavailable_reason"),
    }


def _apply_imported(state: dict[str, Any], payload: dict[str, Any], event: StoredEvent) -> None:
    """Apply incident.imported event (from file-backed store migration)."""
    # Import event restores the full state from the imported incident
    for key in [
        "incident_id", "source_candidate_id", "namespace", "object_kind",
        "object_name", "raw_object_kind", "candidate_class", "severity",
        "status", "first_observed_at", "last_observed_at", "signals",
        "evidence_needed", "evidence_links", "latest_snapshot_bundle_id",
        "signal_count", "evidence_count", "suppressed_reason", "duplicate_of",
        "resolved_at", "resolution_notes", "review_packet",
    ]:
        if key in payload:
            state[key] = payload[key]


# =============================================================================
# Projection Rebuild
# =============================================================================


def rebuild_projection_for_incident(
    conn: sqlite3.Connection,
    incident_id: str,
) -> dict[str, Any] | None:
    """Rebuild the current state for a single incident from its events.

    This function:
    1. Loads all events for the incident in order
    2. Applies each event to produce final state
    3. Returns the rebuilt state

    Args:
        conn: SQLite connection
        incident_id: ID of the incident to rebuild

    Returns:
        Rebuilt state dict, or None if no events found
    """
    # Load all events for this incident in order
    cursor = conn.execute(
        """
        SELECT event_seq, event_id, incident_id, aggregate_version, event_type,
               occurred_at, actor, actor_id, payload_json, payload_sha256,
               previous_event_sha256, event_sha256, created_at
        FROM incident_events
        WHERE incident_id = ?
        ORDER BY aggregate_version ASC
        """,
        (incident_id,),
    )

    rows = cursor.fetchall()
    if not rows:
        return None

    # Build initial empty state
    state: dict[str, Any] = {
        "incident_id": incident_id,
        "aggregate_version": 0,
        "source_candidate_id": "",
        "namespace": "",
        "object_kind": "",
        "object_name": "",
        "raw_object_kind": None,
        "candidate_class": "",
        "severity": "",
        "status": "",
        "first_observed_at": "",
        "last_observed_at": "",
        "current_state_json": "",
        "last_event_seq": 0,
        "updated_at": "",
    }

    # Apply each event
    for row in rows:
        event = parse_stored_event(row)
        apply_event_to_state(state, event)

    # Set current_state_json
    state["current_state_json"] = json.dumps(_extract_current_fields(state))

    return state


def rebuild_projection(conn: sqlite3.Connection) -> int:
    """Rebuild the entire incident_current projection from events.

    This function:
    1. Gets all distinct incident_ids from events
    2. Rebuilds state for each incident
    3. Deletes existing projection and inserts rebuilt state

    Args:
        conn: SQLite connection (should be in transaction)

    Returns:
        Number of incidents rebuilt
    """
    # Get all incident IDs with events
    cursor = conn.execute(
        "SELECT DISTINCT incident_id FROM incident_events ORDER BY incident_id"
    )
    incident_ids = [row[0] for row in cursor.fetchall()]

    # Delete existing projection
    conn.execute("DELETE FROM incident_current")

    rebuilt_count = 0
    now = datetime.now(UTC).isoformat()

    for incident_id in incident_ids:
        state = rebuild_projection_for_incident(conn, incident_id)
        if state is not None:
            # Insert rebuilt state
            conn.execute(
                """
                INSERT INTO incident_current (
                    incident_id, aggregate_version, source_candidate_id,
                    namespace, object_kind, object_name, raw_object_kind,
                    candidate_class, severity, status, first_observed_at,
                    last_observed_at, current_state_json, last_event_seq, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["incident_id"],
                    state["aggregate_version"],
                    state.get("source_candidate_id", ""),
                    state.get("namespace", ""),
                    state.get("object_kind", ""),
                    state.get("object_name", ""),
                    state.get("raw_object_kind"),
                    state.get("candidate_class", ""),
                    state.get("severity", ""),
                    state.get("status", ""),
                    state.get("first_observed_at", ""),
                    state.get("last_observed_at", ""),
                    state.get("current_state_json", ""),
                    state.get("last_event_seq", 0),
                    now,
                ),
            )
            rebuilt_count += 1

    _logger.info(
        "Rebuilt incident projection",
        extra={
            "event": "projection-rebuild",
            "incidents_rebuilt": rebuilt_count,
        },
    )

    return rebuilt_count


def _extract_current_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Extract the core fields for current_state_json from full state.

    Args:
        state: Full rebuilt state

    Returns:
        Dict with core current fields only
    """
    return {
        "incident_id": state.get("incident_id"),
        "source_candidate_id": state.get("source_candidate_id"),
        "namespace": state.get("namespace"),
        "object_kind": state.get("object_kind"),
        "object_name": state.get("object_name"),
        "raw_object_kind": state.get("raw_object_kind"),
        "candidate_class": state.get("candidate_class"),
        "severity": state.get("severity"),
        "status": state.get("status"),
        "first_observed_at": state.get("first_observed_at"),
        "last_observed_at": state.get("last_observed_at"),
        "signal_count": state.get("signal_count", 0),
        "evidence_count": state.get("evidence_count", 0),
        "signals": state.get("signals", []),
        "evidence_links": state.get("evidence_links", []),
        "evidence_needed": state.get("evidence_needed", []),
        "latest_snapshot_bundle_id": state.get("latest_snapshot_bundle_id"),
        "suppressed_reason": state.get("suppressed_reason"),
        "duplicate_of": state.get("duplicate_of"),
        "resolved_at": state.get("resolved_at"),
        "resolution_notes": state.get("resolution_notes"),
        "review_packet": state.get("review_packet", {"status": "not_generated"}),
        "diagnosis_loop": state.get("diagnosis_loop"),
        "aggregate_version": state.get("aggregate_version", 0),
    }


__all__ = [
    "apply_event_to_state",
    "rebuild_projection_for_incident",
    "rebuild_projection",
]
