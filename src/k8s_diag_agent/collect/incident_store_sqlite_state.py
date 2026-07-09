"""SQLite state transition methods for incident store.

This module provides the state transition methods for SQLite-backed incidents:
- mark_collecting_evidence
- mark_ready_for_review
- suppress
- mark_duplicate
- resolve
- mark_investigating

These methods use SQLiteWriteContext to encapsulate write authority:
- Event append goes through ctx.append_event()
- Cache access goes through ctx.get_cached_incident() and ctx.put_cached_incident()
- Snapshot creation goes through ctx.snapshot_incident()

The store provides _write_context() context manager for thread-safe writes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from k8s_diag_agent.domain.incident_lifecycle import (
    DuplicateOfIncidentId,
    ReviewPacketId,
    SnapshotBundleId,
    TransitionApplied,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_collecting_evidence as domain_mark_collecting_evidence,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_duplicate as domain_mark_duplicate,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_investigating as domain_mark_investigating,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_ready_for_review as domain_mark_ready_for_review,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    resolve_incident as domain_resolve_incident,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    suppress_incident as domain_suppress,
)

from .incident_lifecycle import Incident, IncidentStatus
from .incident_lifecycle_domain_adapter import _apply_lifecycle_transition, _to_incident_lifecycle
from .incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)

if TYPE_CHECKING:
    from .incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


# =============================================================================
# Guard Functions (mirrors domain transition logic)
# =============================================================================
# These guard functions check if a transition is valid without modifying state.
# They mirror the domain layer's TransitionResult logic for the Incident model.
# =============================================================================


def _can_mark_collecting_evidence(incident: Incident) -> bool:
    """Check if incident can transition to COLLECTING_EVIDENCE.

    Valid from: open
    """
    return incident.status == IncidentStatus.OPEN


def _can_suppress(incident: Incident) -> bool:
    """Check if incident can be suppressed.

    Valid from: open, collecting_evidence, ready_for_review, investigating
    Terminal states (suppressed, duplicate, resolved) cannot transition.
    """
    return incident.status not in (
        IncidentStatus.SUPPRESSED,
        IncidentStatus.DUPLICATE,
        IncidentStatus.RESOLVED,
    )


def _can_mark_duplicate(incident: Incident) -> bool:
    """Check if incident can be marked as duplicate.

    Valid from: open, collecting_evidence, ready_for_review, investigating
    Terminal states (suppressed, duplicate, resolved) cannot transition.
    """
    return incident.status not in (
        IncidentStatus.SUPPRESSED,
        IncidentStatus.DUPLICATE,
        IncidentStatus.RESOLVED,
    )


def _can_resolve(incident: Incident) -> bool:
    """Check if incident can be resolved.

    Valid from: investigating only
    """
    return incident.status == IncidentStatus.INVESTIGATING


def _can_mark_investigating(incident: Incident) -> bool:
    """Check if incident can transition to INVESTIGATING.

    Valid from: ready_for_review
    """
    return incident.status == IncidentStatus.READY_FOR_REVIEW


# =============================================================================
# State Transition Methods
# =============================================================================


def mark_collecting_evidence_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    bundle_id: str,
) -> Incident | None:
    """Transition to COLLECTING_EVIDENCE.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_mark_collecting_evidence(
            lifecycle,
            bundle_id=SnapshotBundleId(bundle_id),
            actor="system",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "bundle_id": bundle_id,
                    "status": IncidentStatus.COLLECTING_EVIDENCE.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.COLLECTING_EVIDENCE_STARTED,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot transition %s to collecting_evidence from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


def mark_ready_for_review_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    reviewer_id: str,
) -> Incident | None:
    """Transition to READY_FOR_REVIEW.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_mark_ready_for_review(
            lifecycle,
            review_packet_id=ReviewPacketId(""),
            actor="system",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "reviewer_id": reviewer_id,
                    "status": IncidentStatus.READY_FOR_REVIEW.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.READY_FOR_REVIEW,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot transition %s to ready_for_review from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


def suppress_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    reason: str,
) -> Incident | None:
    """Suppress an incident.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_suppress(
            lifecycle,
            reason=reason,
            actor="user",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "reason": reason,
                    "previous_status": incident.status.value,
                    "status": IncidentStatus.SUPPRESSED.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.SUPPRESSED,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot suppress %s from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


def mark_duplicate_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    duplicate_of_id: str,
) -> Incident | None:
    """Mark an incident as duplicate.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_mark_duplicate(
            lifecycle,
            duplicate_of=DuplicateOfIncidentId(duplicate_of_id),
            actor="user",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "duplicate_of_id": duplicate_of_id,
                    "previous_status": incident.status.value,
                    "status": IncidentStatus.DUPLICATE.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.MARKED_DUPLICATE,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot mark %s as duplicate from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


def resolve_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
    resolution: str,
) -> Incident | None:
    """Resolve an incident.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_resolve_incident(
            lifecycle,
            actor="user",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "resolution": resolution,
                    "previous_status": incident.status.value,
                    "status": IncidentStatus.RESOLVED.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.RESOLVED,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot resolve %s from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


def mark_investigating_impl(
    store: SQLiteIncidentStore,
    incident_id: str,
) -> Incident | None:
    """Transition to INVESTIGATING.

    Thread safety: Uses store._write_context() for thread-safe writes.

    R1 FIX: Domain transition is the authority. Check result BEFORE appending event.
    No durable event should be appended if the transition is rejected.
    """
    with store._write_context() as ctx:
        incident = ctx.get_cached_incident(incident_id)
        if incident is None:
            return None

        # Use the domain transition function for proper status handling
        # This is the authoritative check - must precede any event append
        lifecycle = _to_incident_lifecycle(incident)
        result = domain_mark_investigating(
            lifecycle,
            actor="user",
            now=datetime.now(UTC),
        )

        match result:
            case TransitionApplied():
                # Only append event after domain transition confirmed success
                occurred_at = datetime.now(UTC)
                payload = {
                    "status": IncidentStatus.INVESTIGATING.value,
                }
                ctx.append_event(
                    incident_id=incident_id,
                    event_type=IncidentEventType.INVESTIGATION_STARTED,
                    actor=IncidentEventActor.SYSTEM,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                updated = _apply_lifecycle_transition(incident, result)
                ctx.put_cached_incident(updated)
                return ctx.snapshot_incident(updated)
            case _:
                # Rejection: return current state, append nothing
                _logger.warning(
                    "Cannot transition %s to investigating from status %s",
                    incident_id,
                    incident.status.value,
                )
                return ctx.snapshot_incident(incident)


__all__ = [
    "mark_collecting_evidence_impl",
    "mark_ready_for_review_impl",
    "suppress_impl",
    "mark_duplicate_impl",
    "resolve_impl",
    "mark_investigating_impl",
]
