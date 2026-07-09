"""Typed lifecycle transition methods for IncidentStore.

This module contains the lifecycle transition methods that delegate to the typed
domain core in k8s_diag_agent.domain.incident_lifecycle.

These methods are extracted from IncidentStore to keep files under 500 lines
for LLM-friendly checks.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from k8s_diag_agent.domain.incident_lifecycle import (
    DuplicateOfIncidentId,
    ReviewPacketId,
    SnapshotBundleId,
    TransitionApplied,
    TransitionRejected,
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
    suppress_incident as domain_suppress_incident,
)

from .incident_evidence import (
    ArtifactId,
    EvidenceLink,
    EvidenceRole,
    make_artifact_id,
)
from .incident_lifecycle import Incident, IncidentStatus
from .incident_lifecycle_domain_adapter import (
    _apply_lifecycle_transition,
    _to_incident_lifecycle,
)
from .incident_review_packet_state import ReviewPacketState

if TYPE_CHECKING:
    from .incident_store import IncidentStore


def store_mark_collecting_evidence(
    store: IncidentStore,
    incident_id: str,
    bundle_id: str,
    *,
    now: datetime | None = None,
) -> Incident | None:
    """Transition incident to COLLECTING_EVIDENCE state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to transition
        bundle_id: ID of the snapshot bundle being collected
        now: Optional timestamp to use (defaults to current time).
            When promoting candidates, pass the observed_at timestamp
            to preserve deterministic timing.
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Use provided timestamp or current time
    now = now or datetime.now(UTC)

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)

    # Call typed transition
    result = domain_mark_collecting_evidence(
        lifecycle,
        bundle_id=SnapshotBundleId(bundle_id),
        actor="system",
        now=now,
    )

    # Handle result - apply or preserve old behavior for rejections
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            # Preserve store-specific fields that domain doesn't know about
            # Use branded ArtifactId for evidence link
            branded_artifact_id: ArtifactId = make_artifact_id(bundle_id)
            updated = replace(
                updated,
                latest_snapshot_bundle_id=bundle_id,
                evidence_links=incident.evidence_links + [
                    EvidenceLink(
                        incident_id=incident_id,
                        artifact_id=branded_artifact_id,
                        role=EvidenceRole.SNAPSHOT,
                        attached_at=now,
                    )
                ],
                evidence_count=incident.evidence_count + 1,
            )
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


def store_mark_ready_for_review(
    store: IncidentStore,
    incident_id: str,
    review_packet_id: str | None = None,
) -> Incident | None:
    """Transition incident to READY_FOR_REVIEW state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to transition
        review_packet_id: Optional ID of the review packet
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)
    now = datetime.now(UTC)

    # Build review packet ID - use provided or existing, coerce to empty string as fallback
    # For legacy compatibility, empty string is acceptable when packet id is unavailable
    existing_review_id = incident.review_packet.id
    effective_review_id = review_packet_id or existing_review_id or ""

    # Call typed transition (domain now accepts OPEN -> READY_FOR_REVIEW)
    result = domain_mark_ready_for_review(
        lifecycle,
        review_packet_id=ReviewPacketId(effective_review_id),
        actor="diagnosis_loop",
        now=now,
    )

    # Handle result
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            # Only update review_packet if we have a non-empty ID
            # When no packet ID is available, preserve the existing review_packet state
            if effective_review_id:
                updated = replace(
                    updated,
                    review_packet=ReviewPacketState.available(
                        id=effective_review_id,
                        generated_at=now,
                    ),
                )
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


def store_mark_ready_for_review_by_bundle_id(
    store: IncidentStore,
    snapshot_bundle_id: str,
    review_packet_id: str | None = None,
) -> tuple[Incident, ...]:
    """Mark all incidents with matching bundle_id as ready_for_review.

    This is called after successful review packet generation to update
    the incident lifecycle state.

    Protected status rule: Does not update SUPPRESSED, DUPLICATE, or RESOLVED
    incidents. These are considered terminal-ish states.

    Args:
        store: The incident store
        snapshot_bundle_id: The bundle ID to match
        review_packet_id: Optional ID of the review packet
    Returns:
        Tuple of updated incidents
    """
    updated: list[Incident] = []
    now = datetime.now(UTC)

    for incident_id, incident in store._incidents.items():
        if incident.latest_snapshot_bundle_id == snapshot_bundle_id:
            # Do not update protected statuses (terminal-ish states)
            if incident.status in (
                IncidentStatus.SUPPRESSED,
                IncidentStatus.DUPLICATE,
                IncidentStatus.RESOLVED,
            ):
                continue

            # Convert to domain type
            lifecycle = _to_incident_lifecycle(incident)
            existing_review_id = incident.review_packet.id
            effective_review_id = review_packet_id if review_packet_id else (
                existing_review_id if existing_review_id else None
            )

            # Call typed transition only if we have a valid review packet ID
            if effective_review_id:
                result = domain_mark_ready_for_review(
                    lifecycle,
                    review_packet_id=ReviewPacketId(effective_review_id),
                    actor="diagnosis_loop",
                    now=now,
                )
            else:
                # No review packet available - skip this incident
                continue

            # Handle result
            match result:
                case TransitionApplied():
                    updated_incident = _apply_lifecycle_transition(incident, result)
                    # Preserve store-specific fields
                    # effective_review_id is guaranteed non-None when transition applied
                    assert effective_review_id is not None, "review packet ID required for READY_FOR_REVIEW"
                    updated_incident = replace(
                        updated_incident,
                        review_packet=ReviewPacketState.available(
                            id=effective_review_id,
                            generated_at=now,
                        ),
                    )
                    store._incidents[incident_id] = updated_incident
                    updated.append(store._snapshot_incident(updated_incident))
                case TransitionRejected():
                    # Skip rejected incidents
                    continue

    return tuple(sorted(updated, key=lambda i: i.incident_id))


def store_suppress(
    store: IncidentStore,
    incident_id: str,
    reason: str,
) -> Incident | None:
    """Transition incident to SUPPRESSED state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to suppress
        reason: Human-readable reason for suppression
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)
    now = datetime.now(UTC)

    # Call typed transition
    result = domain_suppress_incident(
        lifecycle,
        reason=reason,
        actor="user",
        now=now,
    )

    # Handle result
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            # Preserve store-specific fields
            updated = replace(
                updated,
                suppressed_reason=reason,
            )
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


def store_mark_duplicate(
    store: IncidentStore,
    incident_id: str,
    duplicate_of: str,
) -> Incident | None:
    """Transition incident to DUPLICATE state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to mark as duplicate
        duplicate_of: incident_id of the primary incident
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)
    now = datetime.now(UTC)

    # Call typed transition
    result = domain_mark_duplicate(
        lifecycle,
        duplicate_of=DuplicateOfIncidentId(duplicate_of),
        actor="user",
        now=now,
    )

    # Handle result
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            # Preserve store-specific fields
            updated = replace(
                updated,
                duplicate_of=duplicate_of,
            )
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


def store_resolve(
    store: IncidentStore,
    incident_id: str,
) -> Incident | None:
    """Transition incident to RESOLVED state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to resolve
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)
    now = datetime.now(UTC)

    # Call typed transition
    result = domain_resolve_incident(
        lifecycle,
        actor="user",
        now=now,
    )

    # Handle result
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            # Preserve store-specific fields
            updated = replace(
                updated,
                resolved_at=now,
            )
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


def store_mark_investigating(
    store: IncidentStore,
    incident_id: str,
) -> Incident | None:
    """Transition incident to INVESTIGATING state.

    This method delegates to the typed domain core.

    Args:
        store: The incident store
        incident_id: ID of the incident to transition
    Returns:
        Updated incident snapshot, or None if not found
    """
    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Convert to domain type
    lifecycle = _to_incident_lifecycle(incident)
    now = datetime.now(UTC)

    # Call typed transition
    result = domain_mark_investigating(
        lifecycle,
        actor="diagnosis_loop",
        now=now,
    )

    # Handle result
    match result:
        case TransitionApplied():
            updated = _apply_lifecycle_transition(incident, result)
            store._incidents[incident_id] = updated
            return store._snapshot_incident(updated)
        case TransitionRejected():
            # Rejection: return current state (no-op)
            return store._snapshot_incident(incident)
    raise AssertionError("unreachable: all TransitionResult cases handled")


# Re-export for backwards compatibility with IncidentStore methods
__all__ = [
    "store_mark_collecting_evidence",
    "store_mark_ready_for_review",
    "store_mark_ready_for_review_by_bundle_id",
    "store_suppress",
    "store_mark_duplicate",
    "store_resolve",
    "store_mark_investigating",
]
