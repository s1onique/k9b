"""Bundle-attached incident promotion logic.

This module provides pure functions for promoting candidates with bundle attachment:
- open_incident_from_candidate_with_bundle: creates incident in COLLECTING_EVIDENCE state
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

from .incident_lifecycle import (
    Incident,
    IncidentStatus,
    mark_collecting_evidence,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


def open_incident_from_candidate_with_bundle(
    candidate: IncidentCandidate,
    observed_at: datetime,
    snapshot_bundle_id: str,
) -> Incident:
    """Create an incident record from a candidate with bundle attachment.

    This is the candidate → collecting_evidence transition for bundle-attached promotion.

    Args:
        candidate: The deterministic incident candidate to promote
        observed_at: When this candidate was observed
        snapshot_bundle_id: ID of the snapshot bundle containing evidence

    Returns:
        New incident in COLLECTING_EVIDENCE state with bundle ID attached
    """
    # Import here to avoid circular imports at module level
    from .incident_lifecycle import open_incident_from_candidate

    # Start with the base incident creation
    incident = open_incident_from_candidate(candidate, observed_at)

    # Transition to collecting_evidence with bundle attachment
    return mark_collecting_evidence(incident, snapshot_bundle_id)


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
    from .incident_lifecycle import IncidentSignal

    # Convert candidate signals to incident signals
    new_signals: list[IncidentSignal] = []
    for sig in candidate.signals:
        new_signals.append(
            IncidentSignal(
                source=sig.source,
                reason=sig.reason,
                message=sig.message,
                captured_at=observed_at,
            )
        )

    # Determine status: only update if not in a terminal-ish status
    # and not already at READY_FOR_REVIEW (don't downgrade)
    new_status = incident.status
    if incident.status not in _TERMINAL_REOPEN_BLOCKED_STATUSES:
        if incident.status != IncidentStatus.READY_FOR_REVIEW:
            new_status = IncidentStatus.COLLECTING_EVIDENCE

    # Determine snapshot_bundle_id: update if transitioning to collecting_evidence
    new_bundle_id = incident.snapshot_bundle_id
    if new_status == IncidentStatus.COLLECTING_EVIDENCE:
        new_bundle_id = snapshot_bundle_id

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
        snapshot_bundle_id=new_bundle_id,
        review_packet_available=incident.review_packet_available,
        review_packet_id=incident.review_packet_id,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


__all__ = [
    "open_incident_from_candidate_with_bundle",
    "merge_candidate_into_incident_with_bundle",
]
