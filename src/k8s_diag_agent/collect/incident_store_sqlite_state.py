"""SQLite state transition methods for incident store.

This module provides the state transition methods for SQLite-backed incidents:
- mark_collecting_evidence
- mark_ready_for_review
- suppress
- mark_duplicate
- resolve
- mark_investigating
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from .incident_lifecycle import Incident, IncidentStatus
from .incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)
from .incident_store_sqlite_events_writer import append_event as _append_event

if TYPE_CHECKING:

    from .incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


# =============================================================================
# State Transition Methods
# =============================================================================


def mark_collecting_evidence_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    bundle_id: str,
) -> Incident | None:
    """Transition to COLLECTING_EVIDENCE."""
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not incident.can_mark_collecting_evidence():
        _logger.warning(
            "Cannot transition %s to collecting_evidence from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "bundle_id": bundle_id,
        "status": IncidentStatus.COLLECTING_EVIDENCE.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.mark_collecting_evidence(bundle_id))
    store._incidents[incident_id] = updated
    return updated


def mark_ready_for_review_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    reviewer_id: str,
) -> Incident | None:
    """Transition to READY_FOR_REVIEW."""
    from .incident_transitions import can_transition_to_ready_for_review

    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not can_transition_to_ready_for_review(incident):
        _logger.warning(
            "Cannot transition %s to ready_for_review from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "reviewer_id": reviewer_id,
        "status": IncidentStatus.READY_FOR_REVIEW.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.READY_FOR_REVIEW,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.mark_ready_for_review(reviewer_id))
    store._incidents[incident_id] = updated
    return updated


def suppress_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    reason: str,
) -> Incident | None:
    """Suppress an incident."""
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not incident.can_suppress():
        _logger.warning(
            "Cannot suppress %s from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "reason": reason,
        "previous_status": incident.status.value,
        "status": IncidentStatus.SUPPRESSED.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.SUPPRESSED,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.suppress(reason))
    store._incidents[incident_id] = updated
    return updated


def mark_duplicate_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    duplicate_of_id: str,
) -> Incident | None:
    """Mark an incident as duplicate."""
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not incident.can_mark_duplicate():
        _logger.warning(
            "Cannot mark %s as duplicate from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "duplicate_of_id": duplicate_of_id,
        "previous_status": incident.status.value,
        "status": IncidentStatus.DUPLICATE.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.MARKED_DUPLICATE,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.mark_duplicate(duplicate_of_id))
    store._incidents[incident_id] = updated
    return updated


def resolve_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    resolution: str,
) -> Incident | None:
    """Resolve an incident."""
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not incident.can_resolve():
        _logger.warning(
            "Cannot resolve %s from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "resolution": resolution,
        "previous_status": incident.status.value,
        "status": IncidentStatus.RESOLVED.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.RESOLVED,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.resolve(resolution))
    store._incidents[incident_id] = updated
    return updated


def mark_investigating_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
) -> Incident | None:
    """Transition to INVESTIGATING."""
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    if not incident.can_mark_investigating():
        _logger.warning(
            "Cannot transition %s to investigating from status %s",
            incident_id,
            incident.status.value,
        )
        return None

    occurred_at = datetime.now(UTC)
    payload = {
        "status": IncidentStatus.INVESTIGATING.value,
    }

    _append_event(
        store,
        store._conn,
        incident_id=incident_id,
        event_type=IncidentEventType.INVESTIGATING_STARTED,
        actor=IncidentEventActor.SYSTEM,
        payload=payload,
        occurred_at=occurred_at,
    )

    updated = cast(Incident, incident.mark_investigating())
    store._incidents[incident_id] = updated
    return updated
