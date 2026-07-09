"""Pure incident lifecycle management without remediation, mutation, or LLM calls.

This module provides the Incident record schema and status enum.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims

State transitions are provided by incident_transitions.py.

Modules:
- incident_lifecycle_types.py: IncidentStatus, IncidentSignal
- incident_events.py: IncidentEvent, IncidentEventType, IncidentEventActor
- incident_review_packet_state.py: ReviewPacketState, ReviewPacketStatus
- incident_transitions.py: Pure transition functions
- incident_lifecycle_serialization.py: Dict serialization helpers
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.domain.incident_lifecycle import (
    IncidentId,
    IncidentLifecycle,
    ReviewPacketId,
    SnapshotBundleId,
    SourceCandidateId,
    TransitionApplied,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_collecting_evidence as domain_mark_collecting_evidence,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_ready_for_review as domain_mark_ready_for_review,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    suppress_incident as domain_suppress_incident,
)

# Re-export types from new modules for backward compatibility
from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_evidence import EvidenceLink, EvidenceRole
from .incident_lifecycle_serialization import (
    incident_from_dict as _incident_from_dict,
)
from .incident_lifecycle_serialization import (
    incident_to_dict as _incident_to_dict,
)
from .incident_lifecycle_types import IncidentSignal, IncidentStatus
from .incident_review_packet_state import ReviewPacketState, ReviewPacketStatus
from .incident_transitions import (
    attach_evidence_artifact,
    merge_candidate_into_incident,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


@dataclass
class Incident:
    """Internal incident record - aggregate root for k9b incident management."""

    incident_id: str
    source_candidate_id: str
    namespace: str
    object_kind: str
    object_name: str
    raw_object_kind: str | None
    candidate_class: str
    severity: str
    status: IncidentStatus
    first_observed_at: datetime
    last_observed_at: datetime
    signals: list[IncidentSignal] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    evidence_links: list[EvidenceLink] = field(default_factory=list)
    latest_snapshot_bundle_id: str | None = None
    review_packet: ReviewPacketState = field(default_factory=ReviewPacketState.not_generated)
    signal_count: int = 0
    evidence_count: int = 0
    events: list[IncidentEvent] = field(default_factory=list)
    suppressed_reason: str | None = None
    duplicate_of: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize incident to dict for JSON storage."""
        return _incident_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Incident:
        """Reconstruct an Incident from a dict (e.g., loaded from JSON)."""
        result: Incident = _incident_from_dict(data)
        return result

    def get_timeline(self) -> list[IncidentEvent]:
        """Get timeline sorted by occurrence time."""
        return sorted(self.events, key=lambda e: e.occurred_at)

    def get_latest_snapshot_bundle_id(self) -> str | None:
        """Get latest snapshot bundle ID."""
        return self.latest_snapshot_bundle_id


def make_incident_id(
    namespace: str,
    object_kind: str,
    object_name: str,
    candidate_class: str,
    raw_object_kind: str | None = None,
) -> str:
    """Create deterministic incident ID from components."""
    kind_value = raw_object_kind.lower() if raw_object_kind else object_kind.lower()
    parts = [namespace.lower(), kind_value, object_name.lower(), candidate_class.lower()]
    raw_id = "-".join(parts)
    return re.sub(r"[^a-z0-9_-]", "-", re.sub(r"-+", "-", raw_id)).strip("-")


def incident_id_from_candidate(candidate: IncidentCandidate) -> str:
    """Generate incident ID from a candidate."""
    return make_incident_id(
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        candidate_class=candidate.candidate_class.value,
        raw_object_kind=candidate.raw_object_kind,
    )


def open_incident_from_candidate(candidate: IncidentCandidate, observed_at: datetime) -> Incident:
    """Create an incident record from a deterministic candidate."""
    incident_id = incident_id_from_candidate(candidate)

    incident_signals = [
        IncidentSignal(
            source=sig.source,
            reason=sig.reason,
            message=sig.message,
            captured_at=observed_at,
        )
        for sig in candidate.signals
    ]

    # Create OPENED event for timeline
    opened_event = IncidentEvent(
        event_id=make_event_id(incident_id, "opened", observed_at),
        incident_id=incident_id,
        event_type=IncidentEventType.OPENED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message="Incident opened from candidate",
        data={"candidate_id": candidate.candidate_id, "signal_count": len(incident_signals)},
    )

    return Incident(
        incident_id=incident_id,
        source_candidate_id=candidate.candidate_id,
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        raw_object_kind=candidate.raw_object_kind,
        candidate_class=candidate.candidate_class.value,
        severity=candidate.severity.value,
        status=IncidentStatus.OPEN,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        signals=incident_signals,
        evidence_needed=list(candidate.evidence_needed),
        signal_count=len(incident_signals),
        events=[opened_event],
    )


# -----------------------------------------------------------------------------
# Pure adapter functions for status transitions (compatibility surface)
# These delegate to the typed domain core while preserving pure function semantics.
# -----------------------------------------------------------------------------

def _to_lifecycle(incident: Incident) -> IncidentLifecycle:
    """Convert an Incident to the domain IncidentLifecycle type."""
    return IncidentLifecycle(
        incident_id=IncidentId(incident.incident_id),
        source_candidate_id=SourceCandidateId(incident.source_candidate_id),
        status=incident.status.value,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signal_count=incident.signal_count,
        evidence_count=incident.evidence_count,
    )


def _map_transition_result(
    incident: Incident,
    result: TransitionApplied,
    *,
    preserve_last_observed_at: datetime | None = None,
) -> Incident:
    """Map a TransitionApplied result back to the Incident model."""
    status_map: dict[str, IncidentStatus] = {
        "open": IncidentStatus.OPEN,
        "collecting_evidence": IncidentStatus.COLLECTING_EVIDENCE,
        "ready_for_review": IncidentStatus.READY_FOR_REVIEW,
        "investigating": IncidentStatus.INVESTIGATING,
        "suppressed": IncidentStatus.SUPPRESSED,
        "duplicate": IncidentStatus.DUPLICATE,
        "resolved": IncidentStatus.RESOLVED,
    }

    new_lifecycle = result.incident
    new_status = status_map.get(new_lifecycle.status, incident.status)

    # Map domain events to incident events
    event_type_map = {
        "incident_promoted": IncidentEventType.OPENED,
        "incident_marked_collecting_evidence": IncidentEventType.EVIDENCE_COLLECTION_STARTED,
        "incident_marked_ready_for_review": IncidentEventType.REVIEW_PACKET_GENERATED,
        "incident_marked_investigating": IncidentEventType.STATUS_CHANGED,
        "incident_suppressed": IncidentEventType.SUPPRESSED,
        "incident_marked_duplicate": IncidentEventType.MARKED_DUPLICATE,
        "incident_resolved": IncidentEventType.CLOSED,
    }

    actor_map = {
        "system": IncidentEventActor.SYSTEM,
        "user": IncidentEventActor.USER,
        "diagnosis_loop": IncidentEventActor.SYSTEM,
        "test": IncidentEventActor.SYSTEM,
    }

    new_events = []
    for event in result.events:
        event_type = event_type_map.get(event.event_type, IncidentEventType.STATUS_CHANGED)
        actor = actor_map.get(event.actor, IncidentEventActor.SYSTEM)
        occurred_at = event.created_at
        new_events.append(IncidentEvent(
            event_id=make_event_id(incident.incident_id, event.event_type, occurred_at),
            incident_id=incident.incident_id,
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            message=event.detail or f"Transition: {event.event_type}",
            data={"lifecycle_event": event.event_type, "detail": event.detail},
        ))

    # Use preserved timestamp if provided, otherwise use domain's timestamp
    effective_last_observed_at = (
        preserve_last_observed_at if preserve_last_observed_at is not None
        else new_lifecycle.last_observed_at
    )

    return replace(
        incident,
        status=new_status,
        last_observed_at=effective_last_observed_at,
        events=incident.events + new_events,
    )


def mark_collecting_evidence(
    incident: Incident,
    bundle_id: str,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to COLLECTING_EVIDENCE state (pure function)."""
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    result = domain_mark_collecting_evidence(
        lifecycle,
        bundle_id=SnapshotBundleId(bundle_id),
        actor="system",
        now=now,
    )

    match result:
        case TransitionApplied():
            updated = _map_transition_result(incident, result, preserve_last_observed_at=now)
            # Project snapshot_bundle_id to the stored incident
            return replace(updated, latest_snapshot_bundle_id=bundle_id)
    return incident


def mark_ready_for_review(
    incident: Incident,
    review_packet_id: str | None = None,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to READY_FOR_REVIEW state (pure function)."""
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    # Prefer a provided packet ID, then an existing packet ID.
    # If neither exists, preserve legacy behavior: transition status only,
    # and leave review_packet non-available.
    existing_id = incident.review_packet.id
    effective_id = review_packet_id or existing_id

    result = domain_mark_ready_for_review(
        lifecycle,
        review_packet_id=ReviewPacketId(effective_id or ""),
        actor="system",
        now=now,
    )

    match result:
        case TransitionApplied():
            updated = _map_transition_result(incident, result, preserve_last_observed_at=now)
            # Project review_packet status to AVAILABLE if we have a non-empty ID
            if effective_id:
                return replace(
                    updated,
                    review_packet=ReviewPacketState.available(
                        id=effective_id,
                        generated_at=now,
                    ),
                )
            return updated
    return incident


def suppress_incident(
    incident: Incident,
    reason: str,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to SUPPRESSED state (pure function)."""
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    result = domain_suppress_incident(
        lifecycle,
        reason=reason,
        actor="user",
        now=now,
    )

    match result:
        case TransitionApplied():
            return _map_transition_result(incident, result, preserve_last_observed_at=now)
    return incident


__all__ = [
    # Core models
    "Incident",
    "IncidentSignal",
    "IncidentStatus",
    "IncidentEvent",
    "IncidentEventType",
    "IncidentEventActor",
    # Evidence models
    "EvidenceLink",
    "EvidenceRole",
    # Review packet state
    "ReviewPacketState",
    "ReviewPacketStatus",
    # Helper functions
    "make_incident_id",
    "incident_id_from_candidate",
    "make_event_id",
    # Incident creation
    "open_incident_from_candidate",
    # Non-status transition functions
    "merge_candidate_into_incident",
    "attach_evidence_artifact",
    # Status transition functions (pure, compatibility surface)
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "suppress_incident",
]
