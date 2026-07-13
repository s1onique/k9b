"""Bundle-attached incident promotion logic.

This module provides pure functions for promoting candidates with bundle attachment:
- open_incident_from_candidate_with_bundle: creates incident in OPEN state with bundle metadata
- merge_candidate_into_incident_with_bundle: merges candidate while respecting terminal-ish statuses

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (pure functions only)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .incident_evidence import (
    EvidenceLink,
    EvidenceRole,
    make_artifact_id,
)
from .incident_lifecycle import (
    Incident,
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
    IncidentSignal,
    IncidentStatus,
    make_event_id,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


def open_incident_from_candidate_with_bundle(
    candidate: IncidentCandidate,
    observed_at: datetime,
    snapshot_bundle_id: str,
) -> Incident:
    """Create an incident record from a candidate with bundle attachment.

    Creates a new incident with the bundle_id and evidence links attached.
    The incident status remains OPEN; the caller should transition to COLLECTING_EVIDENCE
    using store_mark_collecting_evidence if that state is desired.

    Args:
        candidate: The deterministic incident candidate to promote
        observed_at: When this candidate was observed
        snapshot_bundle_id: ID of the snapshot bundle containing evidence

    Returns:
        New incident with bundle metadata attached (status remains OPEN)
    """
    # Import here to avoid circular imports at module level
    from .incident_lifecycle import open_incident_from_candidate

    # Start with the base incident creation
    incident = open_incident_from_candidate(candidate, observed_at)

    # Create evidence link for the bundle using branded ID
    bundle_link = EvidenceLink(
        incident_id=incident.incident_id,
        artifact_id=make_artifact_id(snapshot_bundle_id),
        role=EvidenceRole.SNAPSHOT,
        attached_at=observed_at,
    )

    # Create bundle attached event
    bundle_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "evidence_collection_started", observed_at),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.EVIDENCE_COLLECTION_STARTED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Evidence collection started with bundle {snapshot_bundle_id}",
        data={"bundle_id": snapshot_bundle_id},
    )

    # Attach bundle metadata without projecting status
    # Status transition should be done by caller using store_mark_collecting_evidence
    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=incident.status,  # Keep OPEN status
        first_observed_at=incident.first_observed_at,
        last_observed_at=observed_at,
        signals=incident.signals,
        evidence_needed=incident.evidence_needed,
        evidence_links=incident.evidence_links + [bundle_link],
        latest_snapshot_bundle_id=snapshot_bundle_id,
        review_packet=incident.review_packet,
        signal_count=incident.signal_count,
        evidence_count=incident.evidence_count + 1,
        events=incident.events + [bundle_event],
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


# Terminal-ish statuses that should not be reopened or downgraded
_TERMINAL_REOPEN_BLOCKED_STATUSES: frozenset[IncidentStatus] = frozenset({
    IncidentStatus.SUPPRESSED,
    IncidentStatus.DUPLICATE,
    IncidentStatus.RESOLVED,
})


def merge_candidate_into_incident_with_bundle(
    incident: Incident,
    candidate: IncidentCandidate,
    observed_at: datetime,
    snapshot_bundle_id: str,
) -> Incident:
    """Merge a candidate into an existing incident with bundle attachment.

    Updates last_observed_at, appends signals, and updates snapshot_bundle_id.
    Does NOT create a new incident identity.

    Terminal status handling:
    - SUPPRESSED, DUPLICATE, RESOLVED: incident status is NOT changed,
      only last_observed_at and signals are updated
    - READY_FOR_REVIEW: status is NOT downgraded to COLLECTING_EVIDENCE
    - Other statuses (OPEN, COLLECTING_EVIDENCE, INVESTIGATING):
      snapshot_bundle_id is updated to latest

    Args:
        incident: Existing incident record
        candidate: New candidate observation
        observed_at: When this candidate was observed
        snapshot_bundle_id: ID of the snapshot bundle containing evidence

    Returns:
        Updated incident with new signals, updated timestamp, and bundle ID
    """
    # Convert candidate signals to incident signals
    new_signals: list[IncidentSignal] = []
    for sig in candidate.signals:
        new_signals.append(
            IncidentSignal(
                source=sig.source,
                reason=sig.reason,
                message=sig.message,
                captured_at=observed_at,
                fingerprint=sig.fingerprint,
            )
        )

    # Determine status: only update if not in a terminal-ish status
    # and not already at READY_FOR_REVIEW (don't downgrade)
    new_status = incident.status
    should_collect = False
    if incident.status not in _TERMINAL_REOPEN_BLOCKED_STATUSES:
        if incident.status != IncidentStatus.READY_FOR_REVIEW:
            new_status = IncidentStatus.COLLECTING_EVIDENCE
            should_collect = True

    # Determine snapshot_bundle_id: update if transitioning to collecting_evidence
    new_bundle_id = incident.latest_snapshot_bundle_id
    new_evidence_links = list(incident.evidence_links)
    new_evidence_count = incident.evidence_count
    new_events = list(incident.events)

    if should_collect:
        new_bundle_id = snapshot_bundle_id
        # Check idempotency: don't duplicate evidence link if same bundle already attached
        existing_link = any(
            link.artifact_id == snapshot_bundle_id and link.role == EvidenceRole.SNAPSHOT
            for link in incident.evidence_links
        )
        if not existing_link:
            # Create evidence link for the new bundle using branded ID
            new_link = EvidenceLink(
                incident_id=incident.incident_id,
                artifact_id=make_artifact_id(snapshot_bundle_id),
                role=EvidenceRole.SNAPSHOT,
                attached_at=observed_at,
            )
            new_evidence_links.append(new_link)
            new_evidence_count += 1
            # Create timeline event only when link is actually added
            new_event = IncidentEvent(
                event_id=make_event_id(incident.incident_id, "evidence_collection_started", observed_at),
                incident_id=incident.incident_id,
                event_type=IncidentEventType.EVIDENCE_COLLECTION_STARTED,
                actor=IncidentEventActor.SYSTEM,
                occurred_at=observed_at,
                message=f"Evidence collection started with bundle {snapshot_bundle_id}",
                data={"bundle_id": snapshot_bundle_id},
            )
            new_events.append(new_event)

    # Create signal merge event
    signal_event = IncidentEvent(
        event_id=make_event_id(incident.incident_id, "signal_merged", observed_at),
        incident_id=incident.incident_id,
        event_type=IncidentEventType.SIGNAL_MERGED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message=f"Merged {len(new_signals)} new signal(s) from candidate",
        data={"signal_count": len(new_signals), "candidate_id": candidate.candidate_id},
    )
    new_events.append(signal_event)

    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=new_status,
        first_observed_at=incident.first_observed_at,
        last_observed_at=observed_at,
        signals=incident.signals + new_signals,
        evidence_needed=list(incident.evidence_needed),
        evidence_links=new_evidence_links,
        latest_snapshot_bundle_id=new_bundle_id,
        review_packet=incident.review_packet,
        signal_count=incident.signal_count + len(new_signals),
        evidence_count=new_evidence_count,
        events=new_events,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


__all__ = [
    "open_incident_from_candidate_with_bundle",
    "merge_candidate_into_incident_with_bundle",
]
