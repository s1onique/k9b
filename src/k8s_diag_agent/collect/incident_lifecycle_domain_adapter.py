"""Domain adapter for incident lifecycle transitions.

This module provides adapter functions that bridge between the store's Incident
model and the typed domain core in k8s_diag_agent.domain.incident_lifecycle.

Adapters ensure:
- Store-specific fields are preserved during lifecycle transitions
- Domain events are mapped to store events
- Type conversions between branded identifiers and plain types
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from k8s_diag_agent.domain.incident_lifecycle import (
    IncidentId,
    IncidentLifecycle,
    IncidentLifecycleActor,
    IncidentLifecycleEventType,
    SourceCandidateId,
    TransitionApplied,
)

from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_lifecycle import Incident, IncidentStatus

if TYPE_CHECKING:
    from k8s_diag_agent.domain.incident_lifecycle import IncidentLifecycleEvent


def _to_incident_lifecycle(incident: Incident) -> IncidentLifecycle:
    """Convert an Incident to the domain IncidentLifecycle type.

    This is an adapter function that bridges between the store's Incident
    model and the typed domain core.
    """
    return IncidentLifecycle(
        incident_id=IncidentId(incident.incident_id),
        source_candidate_id=SourceCandidateId(incident.source_candidate_id),
        status=incident.status.value,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signal_count=incident.signal_count,
        evidence_count=incident.evidence_count,
    )


# -----------------------------------------------------------------------------
# Mapping tables (centralized, total)
# Keys are domain IncidentLifecycleEventType / IncidentLifecycleActor values
# Values are store IncidentEventType / IncidentEventActor enum values
# -----------------------------------------------------------------------------

_DOMAIN_EVENT_TO_STORE_EVENT: dict[IncidentLifecycleEventType, IncidentEventType] = {
    "incident_promoted": IncidentEventType.OPENED,
    "incident_marked_collecting_evidence": IncidentEventType.EVIDENCE_COLLECTION_STARTED,
    "incident_marked_ready_for_review": IncidentEventType.REVIEW_PACKET_GENERATED,
    "incident_marked_investigating": IncidentEventType.STATUS_CHANGED,
    "incident_suppressed": IncidentEventType.SUPPRESSED,
    "incident_marked_duplicate": IncidentEventType.MARKED_DUPLICATE,
    "incident_resolved": IncidentEventType.CLOSED,
}

_DOMAIN_ACTOR_TO_STORE_ACTOR: dict[IncidentLifecycleActor, IncidentEventActor] = {
    "system": IncidentEventActor.SYSTEM,
    "user": IncidentEventActor.USER,
    "diagnosis_loop": IncidentEventActor.SYSTEM,
    "test": IncidentEventActor.SYSTEM,
}


def _map_lifecycle_event_to_incident_event(
    domain_event: IncidentLifecycleEvent,
    occurred_at: datetime,
) -> IncidentEvent:
    """Map a domain IncidentLifecycleEvent to the store's IncidentEvent.

    This preserves the existing event serialization shape while capturing
    the lifecycle transition information.

    Raises:
        ValueError: If domain event type or actor is not in the mapping table.
    """
    # Map domain event type - raise on unknown (total mapping)
    try:
        store_event_type = _DOMAIN_EVENT_TO_STORE_EVENT[domain_event.event_type]
    except KeyError as exc:
        raise ValueError(
            f"unmapped lifecycle event type: {domain_event.event_type!r}"
        ) from exc

    # Map domain actor - raise on unknown (total mapping)
    try:
        store_actor = _DOMAIN_ACTOR_TO_STORE_ACTOR[domain_event.actor]
    except KeyError as exc:
        raise ValueError(f"unmapped lifecycle actor: {domain_event.actor!r}") from exc

    return IncidentEvent(
        event_id=make_event_id(
            str(domain_event.incident_id),
            domain_event.event_type,
            occurred_at,
        ),
        incident_id=str(domain_event.incident_id),
        event_type=store_event_type,
        actor=store_actor,
        occurred_at=occurred_at,
        message=domain_event.detail or f"Transition: {domain_event.event_type}",
        data={"lifecycle_event": domain_event.event_type, "detail": domain_event.detail},
    )


def _apply_lifecycle_transition(
    incident: Incident,
    transition_result: TransitionApplied,
) -> Incident:
    """Apply a TransitionApplied result back to the Incident model.

    This adapter function applies the lifecycle state changes from the
    domain core to the store's Incident model.
    """
    # Map domain status literals to IncidentStatus enum values
    status_map: dict[str, IncidentStatus] = {
        "open": IncidentStatus.OPEN,
        "collecting_evidence": IncidentStatus.COLLECTING_EVIDENCE,
        "ready_for_review": IncidentStatus.READY_FOR_REVIEW,
        "investigating": IncidentStatus.INVESTIGATING,
        "suppressed": IncidentStatus.SUPPRESSED,
        "duplicate": IncidentStatus.DUPLICATE,
        "resolved": IncidentStatus.RESOLVED,
    }

    new_lifecycle = transition_result.incident
    new_status = status_map.get(new_lifecycle.status, incident.status)

    # Build new events from the domain lifecycle events
    new_events = [
        _map_lifecycle_event_to_incident_event(event, new_lifecycle.last_observed_at)
        for event in transition_result.events
    ]

    return replace(
        incident,
        status=new_status,
        last_observed_at=new_lifecycle.last_observed_at,
        events=incident.events + new_events,
    )


__all__ = [
    "_to_incident_lifecycle",
    "_map_lifecycle_event_to_incident_event",
    "_apply_lifecycle_transition",
]
