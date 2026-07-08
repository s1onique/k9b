"""Typed incident lifecycle domain core.

This module provides a small, typed, pure domain layer for incident lifecycle transitions.
It is isolated from IO, Kubernetes, HTTP, subprocess, and store dependencies.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims
- NO direct status mutation outside transition functions

Design goals:
- Incident IDs are not plain interchangeable strings at type-check boundaries.
- Incident lifecycle transitions are expressed as pure functions.
- Transition outcomes are explicit typed variants.
- Direct status mutation outside this module is discouraged and verifier-detectable.

Allowed lifecycle transitions:
    open -> collecting_evidence
    collecting_evidence -> ready_for_review
    ready_for_review -> investigating
    investigating -> resolved

    open -> suppressed
    collecting_evidence -> suppressed
    ready_for_review -> suppressed
    investigating -> suppressed

    open -> duplicate
    collecting_evidence -> duplicate
    ready_for_review -> duplicate
    investigating -> duplicate

Terminal states:
    - suppressed
    - duplicate
    - resolved

Terminal states reject further lifecycle transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, NewType

# -----------------------------------------------------------------------------
# Branded identifiers
# -----------------------------------------------------------------------------

IncidentId = NewType("IncidentId", str)
"""Typed incident identifier at domain boundaries."""

SourceCandidateId = NewType("SourceCandidateId", str)
"""Typed source candidate identifier at domain boundaries."""

SnapshotBundleId = NewType("SnapshotBundleId", str)
"""Typed snapshot bundle identifier."""

ReviewPacketId = NewType("ReviewPacketId", str)
"""Typed review packet identifier."""

DuplicateOfIncidentId = NewType("DuplicateOfIncidentId", str)
"""Typed duplicate-of incident identifier."""

# -----------------------------------------------------------------------------
# Status literals
# -----------------------------------------------------------------------------

IncidentStatus = Literal[
    "open",
    "collecting_evidence",
    "ready_for_review",
    "investigating",
    "suppressed",
    "duplicate",
    "resolved",
]
"""Closed lifecycle status literals for incident state machine."""

# -----------------------------------------------------------------------------
# Lifecycle view
# -----------------------------------------------------------------------------

TERMINAL_STATUSES: frozenset[IncidentStatus] = frozenset({
    "suppressed",
    "duplicate",
    "resolved",
})
"""Set of terminal (final) statuses that reject further transitions."""


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycle:
    """Minimal domain projection of incident lifecycle state.

    This is a frozen, immutable view of the lifecycle-relevant subset of an incident.
    It is NOT the full persisted incident object.
    """

    incident_id: IncidentId
    """Unique incident identifier."""

    source_candidate_id: SourceCandidateId
    """Source candidate that triggered this incident."""

    status: IncidentStatus
    """Current lifecycle status."""

    first_observed_at: datetime
    """When the incident was first observed."""

    last_observed_at: datetime
    """When the incident was last updated."""

    signal_count: int
    """Number of signals contributing to this incident."""

    evidence_count: int
    """Number of evidence artifacts attached to this incident."""


# -----------------------------------------------------------------------------
# Typed lifecycle events
# -----------------------------------------------------------------------------

IncidentLifecycleEventType = Literal[
    "incident_promoted",
    "incident_marked_collecting_evidence",
    "incident_marked_ready_for_review",
    "incident_marked_investigating",
    "incident_suppressed",
    "incident_marked_duplicate",
    "incident_resolved",
]
"""Event types emitted by lifecycle transitions."""

IncidentLifecycleActor = Literal[
    "system",
    "user",
    "diagnosis_loop",
    "test",
]
"""Actors that can trigger lifecycle transitions."""


@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycleEvent:
    """Immutable lifecycle event emitted by a transition."""

    event_type: IncidentLifecycleEventType
    """Type of lifecycle event."""

    actor: IncidentLifecycleActor
    """Actor that triggered the event."""

    incident_id: IncidentId
    """Incident this event applies to."""

    created_at: datetime
    """When the event was created."""

    detail: str | None = None
    """Optional human-readable detail about the event."""


# -----------------------------------------------------------------------------
# Transition results
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionApplied:
    """Result when a transition was successfully applied."""

    incident: IncidentLifecycle
    """The incident after the transition was applied."""

    events: tuple[IncidentLifecycleEvent, ...]
    """Lifecycle events emitted by this transition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionRejected:
    """Result when a transition was rejected."""

    incident: IncidentLifecycle
    """The incident that was not modified."""

    reason: str
    """Stable reason code for the rejection."""


TransitionResult = TransitionApplied | TransitionRejected
"""Union of possible transition outcomes."""


# -----------------------------------------------------------------------------
# Stable rejection reason codes
# -----------------------------------------------------------------------------

_REJECT_TERMINAL_INCIDENT = "terminal_incident"
"""Incident is in a terminal state and cannot transition."""

_REJECT_INVALID_TRANSITION = "invalid_transition"
"""Requested transition is not allowed from current status."""

_REJECT_MISSING_REVIEW_PACKET = "missing_review_packet"
"""Review packet ID is required but not provided."""

_REJECT_MISSING_SNAPSHOT_BUNDLE = "missing_snapshot_bundle"
"""Snapshot bundle ID is required but not provided."""

_REJECT_DUPLICATE_SELF_REFERENCE = "duplicate_self_reference"
"""Cannot mark an incident as a duplicate of itself."""


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------

def _replace_status(
    incident: IncidentLifecycle,
    *,
    status: IncidentStatus,
    last_observed_at: datetime,
) -> IncidentLifecycle:
    """Replace incident status using dataclasses.replace (pure, no mutation)."""
    return replace(
        incident,
        status=status,
        last_observed_at=last_observed_at,
    )


def _is_terminal(incident: IncidentLifecycle) -> bool:
    """Check if incident is in a terminal state."""
    return incident.status in TERMINAL_STATUSES


def _emit_event(
    incident_id: IncidentId,
    event_type: IncidentLifecycleEventType,
    actor: IncidentLifecycleActor,
    created_at: datetime,
    detail: str | None = None,
) -> IncidentLifecycleEvent:
    """Create a new lifecycle event (pure factory)."""
    return IncidentLifecycleEvent(
        event_type=event_type,
        actor=actor,
        incident_id=incident_id,
        created_at=created_at,
        detail=detail,
    )


# -----------------------------------------------------------------------------
# Pure transition functions
# -----------------------------------------------------------------------------

def mark_collecting_evidence(
    incident: IncidentLifecycle,
    *,
    bundle_id: SnapshotBundleId,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to collecting_evidence status.

    Valid from: open
    Rejected from: collecting_evidence, ready_for_review, investigating, suppressed, duplicate, resolved
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Only valid from 'open'
    if incident.status != "open":
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="collecting_evidence",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_marked_collecting_evidence",
        actor=actor,
        created_at=now,
        detail=f"Evidence collection started with bundle {bundle_id}",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


def mark_ready_for_review(
    incident: IncidentLifecycle,
    *,
    review_packet_id: ReviewPacketId,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to ready_for_review status.

    Valid from: collecting_evidence
    Rejected from: open, ready_for_review, investigating, suppressed, duplicate, resolved
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Only valid from 'collecting_evidence'
    if incident.status != "collecting_evidence":
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="ready_for_review",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_marked_ready_for_review",
        actor=actor,
        created_at=now,
        detail=f"Review packet {review_packet_id} is now available",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


def mark_investigating(
    incident: IncidentLifecycle,
    *,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to investigating status.

    Valid from: ready_for_review
    Rejected from: open, collecting_evidence, investigating, suppressed, duplicate, resolved
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Only valid from 'ready_for_review'
    if incident.status != "ready_for_review":
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="investigating",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_marked_investigating",
        actor=actor,
        created_at=now,
        detail="Investigation started",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


def suppress_incident(
    incident: IncidentLifecycle,
    *,
    reason: str,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to suppressed status.

    Valid from: open, collecting_evidence, ready_for_review, investigating
    Rejected from: suppressed, duplicate, resolved (terminal states)
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Valid from: open, collecting_evidence, ready_for_review, investigating
    valid_from = frozenset({"open", "collecting_evidence", "ready_for_review", "investigating"})
    if incident.status not in valid_from:
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="suppressed",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_suppressed",
        actor=actor,
        created_at=now,
        detail=f"Incident suppressed: {reason}",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


def mark_duplicate(
    incident: IncidentLifecycle,
    *,
    duplicate_of: DuplicateOfIncidentId,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to duplicate status.

    Valid from: open, collecting_evidence, ready_for_review, investigating
    Rejected from: suppressed, duplicate, resolved (terminal states)
    Rejected when: duplicate_of == incident.incident_id
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Check self-reference
    # Compare underlying strings since NewTypes are distinct at type-check time
    if str(duplicate_of) == str(incident.incident_id):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_DUPLICATE_SELF_REFERENCE,
        )

    # Valid from: open, collecting_evidence, ready_for_review, investigating
    valid_from = frozenset({"open", "collecting_evidence", "ready_for_review", "investigating"})
    if incident.status not in valid_from:
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="duplicate",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_marked_duplicate",
        actor=actor,
        created_at=now,
        detail=f"Marked as duplicate of {duplicate_of}",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


def resolve_incident(
    incident: IncidentLifecycle,
    *,
    actor: IncidentLifecycleActor,
    now: datetime,
) -> TransitionResult:
    """Transition incident to resolved status.

    Valid from: investigating
    Rejected from: open, collecting_evidence, ready_for_review, suppressed, duplicate, resolved
    """
    # Check terminal state
    if _is_terminal(incident):
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_TERMINAL_INCIDENT,
        )

    # Only valid from 'investigating'
    if incident.status != "investigating":
        return TransitionRejected(
            incident=incident,
            reason=_REJECT_INVALID_TRANSITION,
        )

    # Create new incident with updated status
    new_incident = _replace_status(
        incident,
        status="resolved",
        last_observed_at=now,
    )

    # Emit event
    event = _emit_event(
        incident_id=incident.incident_id,
        event_type="incident_resolved",
        actor=actor,
        created_at=now,
        detail="Incident resolved",
    )

    return TransitionApplied(
        incident=new_incident,
        events=(event,),
    )


__all__ = [
    # Identifiers
    "IncidentId",
    "SourceCandidateId",
    "SnapshotBundleId",
    "ReviewPacketId",
    "DuplicateOfIncidentId",
    # Status
    "IncidentStatus",
    "TERMINAL_STATUSES",
    # Lifecycle view
    "IncidentLifecycle",
    # Events
    "IncidentLifecycleEvent",
    "IncidentLifecycleEventType",
    "IncidentLifecycleActor",
    # Transition results
    "TransitionApplied",
    "TransitionRejected",
    "TransitionResult",
    # Transition functions
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "mark_investigating",
    "suppress_incident",
    "mark_duplicate",
    "resolve_incident",
]
