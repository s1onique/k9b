"""Event types and hashing for SQLite incident store.

This module defines:
- Canonical event types for the incident lifecycle
- Event hash chain implementation (payload_sha256 + event_sha256)
- Canonical JSON serialization for deterministic hashing
- Event factory functions for creating new events

Design notes:
- Events are immutable once created
- Hash chain provides tamper evidence
- Canonical JSON ensures deterministic hashing across systems
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# TYPE_CHECKING is used for conditional imports that are only needed for type hints
# This is safe to have as no runtime imports are needed in TYPE_CHECKING block


# =============================================================================
# Canonical Event Types
# =============================================================================


class IncidentEventType(StrEnum):
    """Canonical event types for incident lifecycle.

    These events are appended to incident_events and form the immutable
    source of truth. Each event type has a payload that allows rebuilding
    the current state (incident_current projection).
    """

    # Incident lifecycle events
    OPENED = "incident.opened"
    SIGNAL_OBSERVED = "incident.signal_observed"
    UPDATED = "incident.updated"
    COLLECTING_EVIDENCE_STARTED = "incident.collecting_evidence_started"
    READY_FOR_REVIEW = "incident.ready_for_review"
    INVESTIGATION_STARTED = "incident.investigation_started"
    SUPPRESSED = "incident.suppressed"
    MARKED_DUPLICATE = "incident.marked_duplicate"
    RESOLVED = "incident.resolved"
    EVIDENCE_ATTACHED = "incident.evidence_attached"

    # Diagnosis loop events
    DIAGNOSIS_LOOP_STARTED = "incident.diagnosis_loop_started"
    DIAGNOSIS_LOOP_COMPLETED = "incident.diagnosis_loop_completed"
    DIAGNOSIS_LOOP_FAILED = "incident.diagnosis_loop_failed"

    # Import event (for migrating from file-backed store)
    IMPORTED = "incident.imported"


class IncidentEventActor(StrEnum):
    """Actor that triggered the event."""

    SYSTEM = "system"
    USER = "user"
    SCHEDULER = "scheduler"
    ALERT = "alert"
    COLLECTOR = "collector"


# =============================================================================
# Event Record (stored in SQLite)
# =============================================================================


@dataclass(frozen=True)
class StoredEvent:
    """An event record as stored in SQLite incident_events table."""

    event_id: str
    incident_id: str
    aggregate_version: int
    event_type: str
    occurred_at: datetime
    actor: str
    actor_id: str | None
    payload_json: str
    payload_sha256: str
    previous_event_sha256: str | None
    event_sha256: str
    created_at: datetime
    event_seq: int | None = None  # Assigned by SQLite autoincrement


# =============================================================================
# Canonical JSON Serialization
# =============================================================================


def _canonical_json(data: dict[str, Any]) -> str:
    """Serialize data to canonical JSON for deterministic hashing.

    Rules:
    - sort_keys=True (deterministic key ordering)
    - separators=(',', ':') (compact format)
    - ensure ASCII output (no unicode escapes for normal chars)
    - UTC ISO timestamps

    Args:
        data: Dict to serialize

    Returns:
        Canonical JSON string
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )


def _json_default(obj: object) -> str:
    """Default JSON serializer for non-standard types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, StrEnum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _datetime_to_iso(dt: datetime) -> str:
    """Convert datetime to UTC ISO string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


# =============================================================================
# Hash Chain Implementation
# =============================================================================


def compute_payload_sha256(payload: dict[str, Any]) -> str:
    """Compute SHA256 hash of event payload.

    Args:
        payload: Event payload dict

    Returns:
        SHA256 hex digest of canonical JSON
    """
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_event_sha256(
    event_id: str,
    incident_id: str,
    aggregate_version: int,
    event_type: str,
    occurred_at: datetime,
    actor: str,
    actor_id: str | None,
    payload_sha256: str,
    previous_event_sha256: str | None,
) -> str:
    """Compute SHA256 hash of event envelope (excluding payload content).

    This creates a tamper-evident hash chain where each event's hash
    depends on the previous event's hash.

    Args:
        event_id: Unique event identifier
        incident_id: Parent incident identifier
        aggregate_version: Version number for this incident
        event_type: Event type string
        occurred_at: When the event occurred
        actor: Who triggered the event
        actor_id: Optional actor identifier
        payload_sha256: Hash of the payload
        previous_event_sha256: Hash of previous event (None for first event)

    Returns:
        SHA256 hex digest of event envelope
    """
    envelope: dict[str, Any] = {
        "event_id": event_id,
        "incident_id": incident_id,
        "aggregate_version": aggregate_version,
        "event_type": event_type,
        "occurred_at": _datetime_to_iso(occurred_at),
        "actor": actor,
        "payload_sha256": payload_sha256,
    }

    if actor_id is not None:
        envelope["actor_id"] = actor_id

    if previous_event_sha256 is not None:
        envelope["previous_event_sha256"] = previous_event_sha256

    return compute_payload_sha256(envelope)


# =============================================================================
# Event Factory
# =============================================================================


@dataclass
class EventBuilder:
    """Builder for creating new incident events with hash chain support."""

    incident_id: str
    event_type: IncidentEventType
    actor: IncidentEventActor
    occurred_at: datetime

    # Optional fields
    actor_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    # Set by _prepare() before building
    _aggregate_version: int = 0
    _previous_event_sha256: str | None = None

    def with_previous_version(
        self,
        version: int,
        previous_sha256: str | None,
    ) -> EventBuilder:
        """Set the previous version info for hash chain.

        Args:
            version: Previous aggregate version
            previous_sha256: SHA256 of previous event

        Returns:
            Self for chaining
        """
        self._aggregate_version = version
        self._previous_event_sha256 = previous_sha256
        return self

    def build(self) -> tuple[StoredEvent, dict[str, Any]]:
        """Build a new stored event with hash chain.

        Returns:
            Tuple of (StoredEvent, raw_payload) for storing
        """
        # Generate event ID if not set
        event_id = self._generate_event_id()

        # Next version
        next_version = self._aggregate_version + 1

        # Compute payload hash
        payload_sha256 = compute_payload_sha256(self.payload)

        # Compute event hash
        event_sha256 = compute_event_sha256(
            event_id=event_id,
            incident_id=self.incident_id,
            aggregate_version=next_version,
            event_type=self.event_type.value,
            occurred_at=self.occurred_at,
            actor=self.actor.value,
            actor_id=self.actor_id,
            payload_sha256=payload_sha256,
            previous_event_sha256=self._previous_event_sha256,
        )

        # Serialize payload
        payload_json = _canonical_json(self.payload)

        # Created timestamp
        created_at = datetime.now(UTC)

        event = StoredEvent(
            event_id=event_id,
            incident_id=self.incident_id,
            aggregate_version=next_version,
            event_type=self.event_type.value,
            occurred_at=self.occurred_at,
            actor=self.actor.value,
            actor_id=self.actor_id,
            payload_json=payload_json,
            payload_sha256=payload_sha256,
            previous_event_sha256=self._previous_event_sha256,
            event_sha256=event_sha256,
            created_at=created_at,
        )

        return event, self.payload

    def _generate_event_id(self) -> str:
        """Generate a unique event ID.

        Format: {incident_id}-{event_type-short}-{timestamp}-{uuid-short}
        """
        type_short = self.event_type.value.replace(".", "_").replace("incident_", "")[:20]
        ts = self.occurred_at.strftime("%Y%m%d%H%M%S%f")
        uid = uuid.uuid4().hex[:8]
        safe_incident = self.incident_id.replace("/", "_")[:50]
        return f"{safe_incident}-{type_short}-{ts}-{uid}"


# =============================================================================
# Event Parsing
# =============================================================================


def parse_stored_event(row: tuple[Any, ...]) -> StoredEvent:
    """Parse a stored event from a database row.

    Args:
        row: Database row tuple

    Returns:
        StoredEvent instance
    """
    return StoredEvent(
        event_seq=row[0],
        event_id=row[1],
        incident_id=row[2],
        aggregate_version=row[3],
        event_type=row[4],
        occurred_at=datetime.fromisoformat(row[5]),
        actor=row[6],
        actor_id=row[7],
        payload_json=row[8],
        payload_sha256=row[9],
        previous_event_sha256=row[10],
        event_sha256=row[11],
        created_at=datetime.fromisoformat(row[12]),
    )


def event_to_dict(event: StoredEvent) -> dict[str, Any]:
    """Convert a stored event to a dict for API response.

    Args:
        event: The stored event

    Returns:
        Dict suitable for JSON serialization
    """
    result: dict[str, Any] = {
        "event_seq": event.event_seq,
        "event_id": event.event_id,
        "incident_id": event.incident_id,
        "aggregate_version": event.aggregate_version,
        "event_type": event.event_type,
        "occurred_at": _datetime_to_iso(event.occurred_at),
        "actor": event.actor,
        "payload": json.loads(event.payload_json) if event.payload_json else {},
        "event_sha256": event.event_sha256,
        "created_at": _datetime_to_iso(event.created_at),
    }

    if event.actor_id is not None:
        result["actor_id"] = event.actor_id

    if event.previous_event_sha256 is not None:
        result["previous_event_sha256"] = event.previous_event_sha256

    return result


# =============================================================================
# Hash Chain Verification
# =============================================================================


def verify_hash_chain(events: list[StoredEvent]) -> bool:
    """Verify the hash chain for a list of events.

    This verifies:
    1. Each event's envelope hash (event_sha256) matches recomputed hash
    2. Each event's payload hash (payload_sha256) matches the payload_json
    3. Sequence integrity (versions are consecutive and linked)

    Args:
        events: List of events for a single incident (ordered by aggregate_version)

    Returns:
        True if hash chain is valid, False otherwise
    """
    import json

    for i, event in enumerate(events):
        # Verify payload_json matches payload_sha256
        # This catches tampering where payload_json is changed but payload_sha256 is not
        if event.payload_json:
            try:
                payload_dict = json.loads(event.payload_json)
                computed_payload_hash = compute_payload_sha256(payload_dict)
                if computed_payload_hash != event.payload_sha256:
                    return False
            except json.JSONDecodeError:
                # Invalid JSON in payload_json
                return False

        # Compute expected event hash
        expected_hash = compute_event_sha256(
            event_id=event.event_id,
            incident_id=event.incident_id,
            aggregate_version=event.aggregate_version,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            actor=event.actor,
            actor_id=event.actor_id,
            payload_sha256=event.payload_sha256,
            previous_event_sha256=event.previous_event_sha256,
        )

        if expected_hash != event.event_sha256:
            return False

        # Verify sequence
        if i > 0:
            prev = events[i - 1]
            if event.aggregate_version != prev.aggregate_version + 1:
                return False
            if event.previous_event_sha256 != prev.event_sha256:
                return False

    return True


__all__ = [
    "IncidentEventType",
    "IncidentEventActor",
    "StoredEvent",
    "EventBuilder",
    "compute_payload_sha256",
    "compute_event_sha256",
    "parse_stored_event",
    "event_to_dict",
    "verify_hash_chain",
    "_canonical_json",
]
