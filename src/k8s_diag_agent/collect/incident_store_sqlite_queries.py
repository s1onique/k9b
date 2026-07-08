"""SQLite query operations for incident store projection.

This module provides the projection management layer:
- Incident state creation and update
- Event-to-state projection logic
- State serialization/deserialization
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
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


# =============================================================================
# Projection State Management
# =============================================================================


def _extract_current_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Extract fields for current_state_json.

    NOTE: This must match _extract_current_fields in incident_store_sqlite_projection.py
    to ensure live projection matches rebuilt projection.
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


def create_initial_state(event: StoredEvent) -> dict[str, Any]:
    """Create initial state from an OPENED event.

    Args:
        event: The OPENED event

    Returns:
        Initial state dict
    """
    payload = json.loads(event.payload_json) if event.payload_json else {}

    state: dict[str, Any] = {
        "incident_id": event.incident_id,
        "aggregate_version": event.aggregate_version,
        "last_event_seq": event.event_seq,
        "source_candidate_id": payload.get("source_candidate_id", ""),
        "namespace": payload.get("namespace", ""),
        "object_kind": payload.get("object_kind", ""),
        "object_name": payload.get("object_name", ""),
        "raw_object_kind": payload.get("raw_object_kind"),
        "candidate_class": payload.get("candidate_class", ""),
        "severity": payload.get("severity", ""),
        "status": "open",
        "first_observed_at": payload.get("first_observed_at", event.occurred_at.isoformat()),
        "last_observed_at": payload.get("last_observed_at", event.occurred_at.isoformat()),
        "signals": payload.get("signals", []),
        "evidence_links": payload.get("evidence_links", []),
        "evidence_needed": payload.get("evidence_needed", []),
        "latest_snapshot_bundle_id": payload.get("latest_snapshot_bundle_id"),
        "signal_count": payload.get("signal_count", 1),
        "evidence_count": payload.get("evidence_count", 0),
        "suppressed_reason": None,
        "duplicate_of": None,
        "resolved_at": None,
        "resolution_notes": None,
        "review_packet": {"status": "not_generated"},
        "updated_at": datetime.now(UTC).isoformat(),
    }

    # Serialize current_state_json
    state["current_state_json"] = json.dumps(_extract_current_fields(state))

    return state


# =============================================================================
# Event-to-State Projection
# =============================================================================


def apply_event_to_state_projector(
    current_state: dict[str, Any],
    event: StoredEvent,
) -> dict[str, Any]:
    """Apply an event to an existing incident state.

    Args:
        current_state: Current incident state dict
        event: The event to apply

    Returns:
        Updated state dict
    """
    payload = json.loads(event.payload_json) if event.payload_json else {}

    # Update aggregate version
    current_state["aggregate_version"] = event.aggregate_version
    current_state["last_event_seq"] = event.event_seq
    current_state["updated_at"] = datetime.now(UTC).isoformat()

    # Apply event-type-specific logic
    if event.event_type == IncidentEventType.SIGNAL_OBSERVED:
        # Update last_observed_at and merge signals
        current_state["last_observed_at"] = payload.get(
            "last_observed_at", event.occurred_at.isoformat()
        )
        if "signals" in payload:
            existing_signals = current_state.get("signals", [])
            new_signals = payload["signals"]
            # Merge avoiding duplicates
            seen = {s.get("source", "") + s.get("reason", "") for s in existing_signals}
            for s in new_signals:
                key = s.get("source", "") + s.get("reason", "")
                if key not in seen:
                    existing_signals.append(s)
                    seen.add(key)
            current_state["signals"] = existing_signals
            current_state["signal_count"] = len(existing_signals)

    elif event.event_type == IncidentEventType.COLLECTING_EVIDENCE_STARTED:
        current_state["status"] = payload.get("status", "collecting_evidence")
        current_state["last_observed_at"] = payload.get(
            "last_observed_at", event.occurred_at.isoformat()
        )
        if "bundle_id" in payload:
            current_state["latest_snapshot_bundle_id"] = payload["bundle_id"]
        if "evidence_links" in payload:
            current_state["evidence_links"] = payload["evidence_links"]
            current_state["evidence_count"] = len(payload["evidence_links"])

    elif event.event_type == IncidentEventType.EVIDENCE_ATTACHED:
        if "evidence_links" in payload:
            current_state["evidence_links"] = payload["evidence_links"]
            current_state["evidence_count"] = payload.get("evidence_count", len(payload["evidence_links"]))

    elif event.event_type == IncidentEventType.READY_FOR_REVIEW:
        current_state["status"] = "ready_for_review"
        if "review_packet_id" in payload:
            current_state["review_packet"] = {
                "status": "generated",
                "id": payload["review_packet_id"],
            }

    elif event.event_type == IncidentEventType.SUPPRESSED:
        current_state["status"] = "suppressed"
        current_state["suppressed_reason"] = payload.get("reason")

    elif event.event_type == IncidentEventType.MARKED_DUPLICATE:
        current_state["status"] = "duplicate"
        current_state["duplicate_of"] = payload.get("duplicate_of")

    elif event.event_type == IncidentEventType.RESOLVED:
        current_state["status"] = "resolved"
        current_state["resolved_at"] = event.occurred_at.isoformat()
        if "resolution_notes" in payload:
            current_state["resolution_notes"] = payload["resolution_notes"]

    elif event.event_type == IncidentEventType.INVESTIGATION_STARTED:
        current_state["status"] = "investigating"

    # Re-serialize current_state_json
    current_state["current_state_json"] = json.dumps(_extract_current_fields(current_state))

    return current_state


# =============================================================================
# Database Projection Operations
# =============================================================================


def insert_projection(conn: sqlite3.Connection, state: dict[str, Any]) -> None:
    """Insert a new incident_current row."""
    # Ensure current_state_json is serialized (uses pre-computed value if available)
    current_state_json = state.get("current_state_json") or json.dumps(_extract_current_fields(state))
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
            state.get("status", "open"),
            state.get("first_observed_at", ""),
            state.get("last_observed_at", ""),
            current_state_json,
            state.get("last_event_seq", 0),
            state.get("updated_at", datetime.now(UTC).isoformat()),
        ),
    )


def update_projection(conn: sqlite3.Connection, state: dict[str, Any]) -> None:
    """Update an existing incident_current row."""
    state["current_state_json"] = json.dumps(_extract_current_fields(state))
    conn.execute(
        """
        UPDATE incident_current SET
            aggregate_version = ?,
            source_candidate_id = ?,
            namespace = ?,
            object_kind = ?,
            object_name = ?,
            raw_object_kind = ?,
            candidate_class = ?,
            severity = ?,
            status = ?,
            first_observed_at = ?,
            last_observed_at = ?,
            current_state_json = ?,
            last_event_seq = ?,
            updated_at = ?
        WHERE incident_id = ?
        """,
        (
            state.get("aggregate_version", 0),
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
            state.get("current_state_json", "{}"),
            state.get("last_event_seq", 0),
            state.get("updated_at", datetime.now(UTC).isoformat()),
            state.get("incident_id"),
        ),
    )


def update_projection_for_event(
    conn: sqlite3.Connection,
    event: StoredEvent,
) -> None:
    """Update incident_current projection for a single event.

    This function uses the canonical event-to-state projector from
    incident_store_sqlite_projection to ensure live projection matches
    rebuilt projection (deterministic event sourcing).

    For new incidents (no existing row), we create an empty state dict and
    apply the event. For existing incidents, we load the current state and
    apply the event. Both paths use apply_event_to_state() for determinism.

    This handles all event types including IMPORTED as first event.

    Args:
        conn: Database connection
        event: The appended event
    """
    # Import here to avoid circular imports
    from .incident_store_sqlite_projection import apply_event_to_state

    # Check if incident exists in projection
    cursor = conn.execute(
        "SELECT incident_id, current_state_json FROM incident_current WHERE incident_id = ?",
        (event.incident_id,),
    )
    row = cursor.fetchone()

    # Use canonical projector for both new and existing rows
    # This ensures deterministic event sourcing regardless of event type
    if row is None:
        # New incident - start with empty state and apply event
        state: dict[str, Any] = {}
        apply_event_to_state(state, event)
        # Set required fields that may not be set by all event types
        state["incident_id"] = event.incident_id
        state["aggregate_version"] = event.aggregate_version
        state["last_event_seq"] = event.event_seq
        state["updated_at"] = datetime.now(UTC).isoformat()
        insert_projection(conn, state)
    else:
        # Existing incident - update state using canonical projector
        current_state = json.loads(row[1]) if row[1] else {}
        apply_event_to_state(current_state, event)
        update_projection(conn, current_state)


def get_previous_version_info(
    conn: sqlite3.Connection,
    incident_id: str,
) -> tuple[int, str | None]:
    """Get the previous aggregate version and event hash for an incident.

    Args:
        conn: Database connection
        incident_id: The incident ID

    Returns:
        Tuple of (previous_version, previous_event_sha256 or None)
    """
    cursor = conn.execute(
        """
        SELECT aggregate_version, event_sha256
        FROM incident_events
        WHERE incident_id = ?
        ORDER BY aggregate_version DESC
        LIMIT 1
        """,
        (incident_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return 0, None
    return row[0], row[1]


__all__ = [
    "_extract_current_fields",
    "create_initial_state",
    "apply_event_to_state_projector",
    "insert_projection",
    "update_projection",
    "update_projection_for_event",
    "get_previous_version_info",
]
