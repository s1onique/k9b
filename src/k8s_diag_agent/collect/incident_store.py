"""In-memory incident store with candidate promotion logic.

This module provides an in-memory incident store that:
- Promotes deterministic incident candidates into k9b-owned incident records
- Manages incident lifecycle transitions
- Returns copies/snapshots to avoid exposing internal mutable state

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only for this ACT)

Promotion semantics:
- New candidate → new incident in OPEN state
- Repeated same candidate (same dedupe key) → merges into existing incident
- last_observed_at updates on merge
- first_observed_at remains stable
- Signals append on merge
- raw_object_kind-aware ID ensures ReplicaSet/foo ≠ StatefulSet/foo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .incident_lifecycle import (
    Incident,
    IncidentStatus,
    incident_id_from_candidate,
    merge_candidate_into_incident,
    open_incident_from_candidate,
)
from .incident_lifecycle import (
    mark_collecting_evidence as _mark_collecting_evidence,
)
from .incident_lifecycle import (
    mark_duplicate as _mark_duplicate,
)
from .incident_lifecycle import (
    mark_ready_for_review as _mark_ready_for_review,
)
from .incident_lifecycle import (
    suppress_incident as _suppress_incident,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


@dataclass
class IncidentStore:
    """In-memory incident store with candidate promotion logic.

    The store manages a collection of Incident records derived from
    deterministic candidates. It provides:
    - Candidate promotion (new → open, repeated → merge)
    - Lifecycle transitions (collecting_evidence, ready_for_review, suppress, duplicate)
    - Query operations (list, get)
    - Immutable snapshots on return

    Store discipline:
    - Returns copies/snapshots, not internal mutable state
    - Deterministic ordering for list operations
    - No side effects on Kubernetes, LLMs, or external systems
    """

    # Internal mutable storage - private to enforce snapshot discipline
    _incidents: dict[str, Incident] = field(default_factory=dict)

    def promote_candidates(
        self,
        candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
        observed_at: datetime,
    ) -> tuple[Incident, ...]:
        """Promote candidates into incidents.

        For each candidate:
        - If no matching incident exists, opens a new incident in OPEN state
        - If matching incident exists (same dedupe key), merges signals into it

        Args:
            candidates: Sequence of incident candidates to promote
            observed_at: When these candidates were observed

        Returns:
            Tuple of all incidents (both new and updated), sorted by incident_id
        """
        updated_incidents: dict[str, Incident] = {}

        for candidate in candidates:
            incident_id = incident_id_from_candidate(candidate)

            if incident_id in self._incidents:
                # Merge into existing incident
                existing = self._incidents[incident_id]
                updated = merge_candidate_into_incident(existing, candidate, observed_at)
                self._incidents[incident_id] = updated
                updated_incidents[incident_id] = updated
            else:
                # Open new incident
                new_incident = open_incident_from_candidate(candidate, observed_at)
                self._incidents[incident_id] = new_incident
                updated_incidents[incident_id] = new_incident

        # Return snapshot copies to avoid exposing internal state
        all_updated = [self._snapshot_incident(i) for i in updated_incidents.values()]
        return tuple(sorted(all_updated, key=lambda i: i.incident_id))

    def list_incidents(
        self,
        status: IncidentStatus | None = None,
    ) -> tuple[Incident, ...]:
        """List incidents, optionally filtered by status.

        Returns a tuple (snapshot) of incidents sorted by incident_id.

        Args:
            status: Optional status filter. If None, returns all incidents.

        Returns:
            Tuple of incidents sorted by incident_id
        """
        incidents = list(self._incidents.values())

        if status is not None:
            incidents = [i for i in incidents if i.status == status]

        # Return snapshot copies to avoid exposing internal state
        snapshots = [self._snapshot_incident(i) for i in incidents]
        # Sort by incident_id for deterministic ordering
        return tuple(sorted(snapshots, key=lambda i: i.incident_id))

    def get_incident(self, incident_id: str) -> Incident | None:
        """Get a specific incident by ID.

        Returns a snapshot copy of the incident to avoid exposing internal state.

        Args:
            incident_id: The incident ID to look up

        Returns:
            Snapshot copy of the incident, or None if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        # Return a snapshot copy
        return self._snapshot_incident(incident)

    def _snapshot_incident(self, incident: Incident) -> Incident:
        """Create a snapshot copy of an incident.

        This ensures internal mutable lists are not exposed.
        """
        return Incident(
            incident_id=incident.incident_id,
            source_candidate_id=incident.source_candidate_id,
            namespace=incident.namespace,
            object_kind=incident.object_kind,
            object_name=incident.object_name,
            raw_object_kind=incident.raw_object_kind,
            candidate_class=incident.candidate_class,
            severity=incident.severity,
            status=incident.status,
            first_observed_at=incident.first_observed_at,
            last_observed_at=incident.last_observed_at,
            signals=list(incident.signals),
            evidence_needed=list(incident.evidence_needed),
            snapshot_bundle_id=incident.snapshot_bundle_id,
            review_packet_available=incident.review_packet_available,
            review_packet_id=incident.review_packet_id,
            suppressed_reason=incident.suppressed_reason,
            duplicate_of=incident.duplicate_of,
            resolved_at=incident.resolved_at,
            resolution_notes=incident.resolution_notes,
        )

    def mark_collecting_evidence(self, incident_id: str, bundle_id: str) -> Incident | None:
        """Transition incident to COLLECTING_EVIDENCE state.

        Args:
            incident_id: ID of the incident to transition
            bundle_id: ID of the snapshot bundle being collected

        Returns:
            Updated incident snapshot, or None if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        updated = _mark_collecting_evidence(incident, bundle_id)
        self._incidents[incident_id] = updated
        return self._snapshot_incident(updated)

    def mark_ready_for_review(
        self,
        incident_id: str,
        review_packet_id: str | None = None,
    ) -> Incident | None:
        """Transition incident to READY_FOR_REVIEW state.

        Args:
            incident_id: ID of the incident to transition
            review_packet_id: Optional ID of the review packet

        Returns:
            Updated incident snapshot, or None if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        updated = _mark_ready_for_review(incident, review_packet_id)
        self._incidents[incident_id] = updated
        return self._snapshot_incident(updated)

    def suppress(self, incident_id: str, reason: str) -> Incident | None:
        """Transition incident to SUPPRESSED state.

        Args:
            incident_id: ID of the incident to suppress
            reason: Human-readable reason for suppression

        Returns:
            Updated incident snapshot, or None if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        updated = _suppress_incident(incident, reason)
        self._incidents[incident_id] = updated
        return self._snapshot_incident(updated)

    def mark_duplicate(self, incident_id: str, duplicate_of: str) -> Incident | None:
        """Transition incident to DUPLICATE state.

        Args:
            incident_id: ID of the incident to mark as duplicate
            duplicate_of: incident_id of the primary incident

        Returns:
            Updated incident snapshot, or None if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None

        updated = _mark_duplicate(incident, duplicate_of)
        self._incidents[incident_id] = updated
        return self._snapshot_incident(updated)

    def __len__(self) -> int:
        """Return the number of incidents in the store."""
        return len(self._incidents)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"IncidentStore(incidents={len(self._incidents)})"


__all__ = [
    "IncidentStore",
]
