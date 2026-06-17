"""Incident event models for append-only timeline.

This module contains:
- IncidentEventType: enum for event types
- IncidentEventActor: enum for event actors
- IncidentEvent: append-only timeline event

Design notes:
- Events are immutable once created - they represent historical facts
- The current state is useful for the UI; the timeline explains how it was reached
- This is the foundation for explainability and auditability
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class IncidentEventType(StrEnum):
    """Types of events in the incident timeline."""

    OPENED = "opened"
    SIGNAL_MERGED = "signal_merged"
    SEVERITY_CHANGED = "severity_changed"
    EVIDENCE_COLLECTION_STARTED = "evidence_collection_started"
    SNAPSHOT_BUNDLE_ATTACHED = "snapshot_bundle_attached"
    EVIDENCE_ARTIFACT_ATTACHED = "evidence_artifact_attached"
    REVIEW_PACKET_GENERATED = "review_packet_generated"
    REVIEW_PACKET_FAILED = "review_packet_failed"
    STATUS_CHANGED = "status_changed"
    SUPPRESSED = "suppressed"
    MARKED_DUPLICATE = "marked_duplicate"
    CLOSED = "closed"


class IncidentEventActor(StrEnum):
    """Actor that triggered the event."""

    SYSTEM = "system"
    USER = "user"
    DETECTOR = "detector"
    SCHEDULER = "scheduler"


@dataclass(frozen=True)
class IncidentEvent:
    """Append-only event in the incident timeline.

    This is the foundation for explainability. The current state is useful for
    the UI; the event timeline explains how the incident reached that state.

    Events are immutable once created - they represent historical facts.
    """

    event_id: str
    incident_id: str
    event_type: IncidentEventType
    actor: IncidentEventActor
    occurred_at: datetime
    message: str

    # Optional context
    actor_id: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "event_id": self.event_id,
            "incident_id": self.incident_id,
            "event_type": self.event_type.value,
            "actor": self.actor.value,
            "occurred_at": self.occurred_at.isoformat(),
            "message": self.message,
        }
        if self.actor_id is not None:
            result["actor_id"] = self.actor_id
        if self.data is not None:
            result["data"] = self.data
        return result


def make_event_id(
    incident_id: str,
    event_type: str,
    occurred_at: datetime,
    data: dict[str, Any] | None = None,
) -> str:
    """Create a deterministic event ID.

    Format: incident_id-event_type-timestamp[-short_hash]

    The short_hash suffix is included when data is provided to avoid collisions
    when multiple events of the same type occur at the exact same timestamp.
    """
    timestamp = occurred_at.strftime("%Y%m%d%H%M%S%f")
    # Sanitize for use as an ID
    sanitized_type = re.sub(r"[^a-z0-9_]", "_", event_type.lower())
    base_id = f"{incident_id}-{sanitized_type}-{timestamp}"

    if data:
        # Include short hash of data to avoid collisions
        data_str = json.dumps(data, sort_keys=True, default=str)
        short_hash = hashlib.sha256(data_str.encode()).hexdigest()[:8]
        return f"{base_id}-{short_hash}"

    return base_id


__all__ = [
    "IncidentEvent",
    "IncidentEventType",
    "IncidentEventActor",
    "make_event_id",
]
