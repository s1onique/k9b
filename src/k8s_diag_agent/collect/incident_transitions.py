"""Incident lifecycle transition functions.

This module provides pure functions for incident state transitions.
All functions are pure with no side effects.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_evidence import EvidenceLink, EvidenceRole
from .incident_review_packet_state import ReviewPacketState

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate
    from .incident_lifecycle import Incident  # noqa: F401


def merge_candidate_into_incident(
    incident: Incident,
    candidate: IncidentCandidate,
    observed_at: datetime,
) -> Incident:
    """Merge a new candidate observation into an existing incident."""
    from .incident_lifecycle import IncidentSignal

    new_signals = [
        IncidentSignal(
            source=sig.source,
            reason=sig.reason,
            message=sig.message,
            captured_at=observed_at,
        )
        for sig in candidate.signals
    ]

    # Create SIGNAL_MERGED event
    merge_data = {"signal_count": len(new_signals), "candidate_id": candidate.candidate_id}
    merge_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "signal_merged", observed_at, merge_data),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.SIGNAL_MERGED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Merged {len(new_signals)} signal(s) from candidate",
        data=merge_data,
    )

    return replace(
        incident,
        last_observed_at=observed_at,
        signals=incident.signals + new_signals,
        signal_count=incident.signal_count + len(new_signals),
        events=incident.events + [merge_event],
    )


def mark_collecting_evidence(
    incident: Incident,
    bundle_id: str,
    occurred_at: datetime | None = None,
) -> Incident:
    """Transition incident to COLLECTING_EVIDENCE state."""
    from .incident_lifecycle import IncidentStatus

    now = occurred_at or datetime.now(UTC)

    # Check idempotency: skip if already collecting this bundle
    if incident.latest_snapshot_bundle_id == bundle_id and incident.status == IncidentStatus.COLLECTING_EVIDENCE:
        return incident

    # Create evidence link
    new_link = EvidenceLink(
        incident_id=incident.incident_id,
        artifact_id=bundle_id,
        role=EvidenceRole.SNAPSHOT,
        attached_at=now,
    )

    # Create timeline event
    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "evidence_collection_started", now),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.EVIDENCE_COLLECTION_STARTED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message=f"Evidence collection started with bundle {bundle_id}",
        data={"bundle_id": bundle_id},
    )

    return replace(
        incident,
        status=IncidentStatus.COLLECTING_EVIDENCE,
        latest_snapshot_bundle_id=bundle_id,
        evidence_links=incident.evidence_links + [new_link],
        evidence_count=incident.evidence_count + 1,
        events=incident.events + [new_event],
    )


def mark_ready_for_review(
    incident: Incident,
    review_packet_id: str | None = None,
    occurred_at: datetime | None = None,
) -> Incident:
    """Transition incident to READY_FOR_REVIEW state."""
    from .incident_lifecycle import IncidentStatus

    now = occurred_at or datetime.now(UTC)

    # Determine review packet state and event
    effective_id = review_packet_id or incident.review_packet.id
    if effective_id:
        # Has a review packet ID
        new_review_packet = ReviewPacketState.available(id=effective_id, generated_at=now)
        event_type = IncidentEventType.REVIEW_PACKET_GENERATED
        message = "Review packet is now available"
        event_data = {"review_packet_id": effective_id}
    else:
        # No review packet ID - just mark as ready
        new_review_packet = incident.review_packet
        event_type = IncidentEventType.STATUS_CHANGED
        message = "Incident is ready for review"
        event_data = None

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, event_type.value, now),
        incident_id=incident.incident_id,
        event_type=event_type,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message=message,
        data=event_data,
    )

    return replace(
        incident,
        status=IncidentStatus.READY_FOR_REVIEW,
        review_packet=new_review_packet,
        events=incident.events + [new_event],
    )


def suppress_incident(
    incident: Incident,
    reason: str,
    occurred_at: datetime | None = None,
) -> Incident:
    """Transition incident to SUPPRESSED state."""
    from .incident_lifecycle import IncidentStatus

    now = occurred_at or datetime.now(UTC)

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "suppressed", now),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.SUPPRESSED,
        actor=IncidentEventActor.USER,
        occurred_at=now,
        message=f"Incident suppressed: {reason}",
        data={"reason": reason},
    )

    return replace(
        incident,
        status=IncidentStatus.SUPPRESSED,
        suppressed_reason=reason,
        events=incident.events + [new_event],
    )


def mark_duplicate(
    incident: Incident,
    duplicate_of: str,
    occurred_at: datetime | None = None,
) -> Incident:
    """Transition incident to DUPLICATE state."""
    from .incident_lifecycle import IncidentStatus

    now = occurred_at or datetime.now(UTC)

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "marked_duplicate", now),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.MARKED_DUPLICATE,
        actor=IncidentEventActor.USER,
        occurred_at=now,
        message=f"Marked as duplicate of {duplicate_of}",
        data={"duplicate_of": duplicate_of},
    )

    return replace(
        incident,
        status=IncidentStatus.DUPLICATE,
        duplicate_of=duplicate_of,
        events=incident.events + [new_event],
    )


def attach_evidence_artifact(
    incident: Incident,
    artifact_id: str,
    role: EvidenceRole,
    occurred_at: datetime | None = None,
) -> Incident:
    """Attach an evidence artifact to the incident (idempotent)."""
    now = occurred_at or datetime.now(UTC)

    # Check idempotency
    if any(link.artifact_id == artifact_id and link.role == role for link in incident.evidence_links):
        return incident

    new_link = EvidenceLink(
        incident_id=incident.incident_id,
        artifact_id=artifact_id,
        role=role,
        attached_at=now,
    )

    new_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "evidence_artifact_attached", now),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.EVIDENCE_ARTIFACT_ATTACHED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=now,
        message=f"Evidence artifact attached: {artifact_id}",
        data={"artifact_id": artifact_id, "role": role.value},
    )

    return replace(
        incident,
        evidence_links=incident.evidence_links + [new_link],
        evidence_count=incident.evidence_count + 1,
        events=incident.events + [new_event],
    )


__all__ = [
    "merge_candidate_into_incident",
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "suppress_incident",
    "mark_duplicate",
    "attach_evidence_artifact",
]
