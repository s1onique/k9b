"""In-memory incident store with candidate promotion logic.

This module provides an in-memory incident store that:
- Promotes deterministic incident candidates into k9b-owned incident records
- Manages incident lifecycle transitions via typed domain core
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

Lifecycle transitions are delegated to the typed domain core in:
    k8s_diag_agent.domain.incident_lifecycle
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .incident_events import IncidentEvent
from .incident_evidence import (
    EvidenceLink,
    EvidenceRole,
)
from .incident_lifecycle import (
    Incident,
    IncidentStatus,
)
from .incident_lifecycle_transitions import (
    store_mark_collecting_evidence,
    store_mark_duplicate,
    store_mark_investigating,
    store_mark_ready_for_review,
    store_mark_ready_for_review_by_bundle_id,
    store_resolve,
    store_suppress,
)
from .incident_store_bundle_helpers import (
    attach_evidence_to_incident,
    find_incidents_by_bundle_id_for_store,
)
from .incident_store_diagnosis_loop_helpers import (
    mark_diagnosis_loop_completed_for_store,
    mark_diagnosis_loop_failed_for_store,
    mark_diagnosis_loop_started_for_store,
)
from .incident_store_in_memory_pagination import in_memory_pagination
from .incident_store_promotion_helpers import (
    PromotionOutcome,
)
from .incident_store_promotion_helpers import (
    promote_candidates_with_records as _promote_candidates_with_records,
)

# Import pagination types used in list_incidents_for_diagnosis_page
if TYPE_CHECKING:
    from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
    from .incident_diagnosis_keyset_cursor import (
        DiagnosisPageLimit,
        IncidentDiagnosisCursor,
    )

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


# =============================================================================
# IncidentStore
# =============================================================================

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

    _incidents: dict[str, Incident] = field(default_factory=dict)

    def promote_candidates(
        self,
        candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
    ) -> tuple[Incident, ...]:
        """Promote candidates into incidents.

        R3 contract: the legacy ``promote_candidates`` shape is now a
        thin wrapper around ``promote_candidates_with_records`` so both
        the typed and legacy paths share a single truth source. The
        returned snapshots come straight out of the
        ``PromotionOutcome`` objects emitted by the typed boundary,
        preventing drift between the typed and legacy paths.

        Args:
            candidates: Sequence of incident candidates to promote
            observed_at: When these candidates were observed
            snapshot_bundle_id: Optional ID of the snapshot bundle
                containing evidence.
        Returns:
            Tuple of all incidents (both new and updated), sorted by
            incident_id.
        """
        outcomes = self.promote_candidates_with_records(
            candidates,
            observed_at,
            snapshot_bundle_id,
        )
        all_updated = [
            outcome.incident
            for outcome in outcomes
            if outcome.incident is not None
        ]
        return tuple(sorted(all_updated, key=lambda i: i.incident_id))

    def promote_candidates_from_bundle(
        self,
        bundle_id: str,
        candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
        observed_at: datetime,
    ) -> tuple[Incident, ...]:
        """Promote candidates from a snapshot bundle.

        This is a convenience wrapper around promote_candidates with bundle_id.

        Args:
            bundle_id: ID of the snapshot bundle containing evidence
            candidates: Sequence of incident candidates to promote
            observed_at: When these candidates were observed
        Returns:
            Tuple of all incidents (both new and updated), sorted by incident_id
        """
        return self.promote_candidates(candidates, observed_at, snapshot_bundle_id=bundle_id)

    def promote_candidates_with_records(
        self,
        candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
    ) -> list[PromotionOutcome]:
        """Promote candidates and return typed per-candidate outcomes.

        This is the canonical store-owned promotion boundary. It returns
        a ``list[PromotionOutcome]`` (one per input candidate, in input
        order) so callers do not have to correlate ``candidates`` with
        ``promoted incidents`` via ``zip(..., strict=False)``. Each
        ``PromotionOutcome`` carries the typed ``PromotionRecord``
        alongside the resulting ``Incident`` snapshot so callers can
        consume the canonical ``incident_id`` directly.

        Use this method when you need the per-candidate promotion mapping
        for downstream canonical-id consumption (e.g. automatic
        diagnosis, internal API handlers). Use the simpler
        :meth:`promote_candidates` when you only need the resulting
        incidents.

        Args:
            candidates: Sequence of incident candidates to promote.
            observed_at: When these candidates were observed.
            snapshot_bundle_id: Optional ID of the snapshot bundle
                containing evidence.

        Returns:
            A list of ``PromotionOutcome`` values, one per input candidate,
            in input order. The list may contain entries whose incident
            is ``None`` when the store could not materialize an
            incident; callers should treat those as no-op outcomes.
        """
        return _promote_candidates_with_records(
            self,
            candidates,
            observed_at,
            snapshot_bundle_id,
        )

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

    def add_incident(self, incident: Incident) -> None:
        """Add an incident directly to the store (public seam for alert promotion)."""
        snapshot = self._snapshot_incident(incident)
        self._incidents[snapshot.incident_id] = snapshot

    def get_incident_timeline(self, incident_id: str) -> Sequence[IncidentEvent]:
        """Get the timeline for a specific incident.

        Args:
            incident_id: The incident ID to look up
        Returns:
            Sequence of timeline events sorted by occurrence time, or empty list if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return []
        return incident.get_timeline()

    def get_incident_evidence_links(self, incident_id: str) -> Sequence[EvidenceLink]:
        """Get the evidence links for a specific incident.

        Args:
            incident_id: The incident ID to look up
        Returns:
            Sequence of evidence links, or empty list if not found
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return []
        return list(incident.evidence_links)

    def _snapshot_incident(self, incident: Incident) -> Incident:
        """Create a snapshot copy of an incident."""
        from .incident_snapshot_helpers import snapshot_incident as _snapshot_incident
        return _snapshot_incident(incident)

    def mark_collecting_evidence(self, incident_id: str, bundle_id: str) -> Incident | None:
        """Transition incident to COLLECTING_EVIDENCE state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to transition
            bundle_id: ID of the snapshot bundle being collected
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_mark_collecting_evidence(self, incident_id, bundle_id)

    def mark_ready_for_review(
        self,
        incident_id: str,
        review_packet_id: str | None = None,
    ) -> Incident | None:
        """Transition incident to READY_FOR_REVIEW state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to transition
            review_packet_id: Optional ID of the review packet
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_mark_ready_for_review(self, incident_id, review_packet_id)

    def find_incidents_by_bundle_id(
        self,
        snapshot_bundle_id: str,
    ) -> tuple[Incident, ...]:
        """Find all incidents with matching snapshot_bundle_id.

        This is used to link review packet generation back to incidents.

        Protected status rule: Does not update SUPPRESSED, DUPLICATE, or RESOLVED
        incidents unless explicitly justified. These are considered terminal-ish states.

        Args:
            snapshot_bundle_id: The bundle ID to search for
        Returns:
            Tuple of matching incidents (excluding protected statuses)
        """
        return find_incidents_by_bundle_id_for_store(self, snapshot_bundle_id)

    def mark_ready_for_review_by_bundle_id(
        self,
        snapshot_bundle_id: str,
        review_packet_id: str | None = None,
    ) -> tuple[Incident, ...]:
        """Mark all incidents with matching bundle_id as ready_for_review.

        This is called after successful review packet generation to update
        the incident lifecycle state.

        Protected status rule: Does not update SUPPRESSED, DUPLICATE, or RESOLVED
        incidents. These are considered terminal-ish states.

        Args:
            snapshot_bundle_id: The bundle ID to match
            review_packet_id: Optional ID of the review packet
        Returns:
            Tuple of updated incidents
        """
        return store_mark_ready_for_review_by_bundle_id(
            self, snapshot_bundle_id, review_packet_id
        )

    def suppress(self, incident_id: str, reason: str) -> Incident | None:
        """Transition incident to SUPPRESSED state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to suppress
            reason: Human-readable reason for suppression
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_suppress(self, incident_id, reason)

    def mark_duplicate(self, incident_id: str, duplicate_of: str) -> Incident | None:
        """Transition incident to DUPLICATE state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to mark as duplicate
            duplicate_of: incident_id of the primary incident
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_mark_duplicate(self, incident_id, duplicate_of)

    def resolve(self, incident_id: str) -> Incident | None:
        """Transition incident to RESOLVED state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to resolve
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_resolve(self, incident_id)

    def mark_investigating(self, incident_id: str) -> Incident | None:
        """Transition incident to INVESTIGATING state.

        This method delegates to the typed domain core.

        Args:
            incident_id: ID of the incident to transition
        Returns:
            Updated incident snapshot, or None if not found
        """
        return store_mark_investigating(self, incident_id)

    def attach_evidence(
        self,
        incident_id: str,
        artifact_id: str,
        role: EvidenceRole,
    ) -> Incident | None:
        """Attach an evidence artifact to the incident.

        Args:
            incident_id: ID of the incident to attach evidence to
            artifact_id: ID of the evidence artifact
            role: Role of the evidence
        Returns:
            Updated incident snapshot, or None if not found
        """
        return attach_evidence_to_incident(self, incident_id, artifact_id, role)

    def mark_diagnosis_loop_started(
        self,
        incident_id: str,
        run_id: str,
        collector_run_id: str,
    ) -> Incident | None:
        """Mark that automatic diagnosis loop started for an incident.

        Safe metadata only - no raw packet contents, logs, or stack traces.

        Args:
            incident_id: ID of the incident
            run_id: The run_id for this diagnosis loop pass
            collector_run_id: The batch collector run ID
        Returns:
            Updated incident snapshot, or None if not found
        """
        return mark_diagnosis_loop_started_for_store(self, incident_id, run_id, collector_run_id)

    def mark_diagnosis_loop_completed(
        self,
        incident_id: str,
        run_id: str,
        collector_run_id: str,
        review_packet_name: str | None = None,
        checks_requested: int = 0,
        checks_run: int = 0,
        checks_rejected: int = 0,
        decision: str | None = None,
    ) -> Incident | None:
        """Mark that automatic diagnosis loop completed successfully.

        Safe metadata only - no raw packet contents, logs, or stack traces.

        Args:
            incident_id: ID of the incident
            run_id: The run_id for this diagnosis loop pass
            collector_run_id: The batch collector run ID
            review_packet_name: Optional review packet filename
            checks_requested: Number of checks requested
            checks_run: Number of checks actually run
            checks_rejected: Number of checks rejected
            decision: The terminal decision from the policy-enforced loop pass
                (e.g., "stop_no_checks_proposed", "stop_root_cause_found")
        Returns:
            Updated incident snapshot, or None if not found
        """
        return mark_diagnosis_loop_completed_for_store(
            self, incident_id, run_id, collector_run_id,
            review_packet_name, checks_requested, checks_run, checks_rejected,
            decision=decision,
        )

    def mark_diagnosis_loop_failed(
        self,
        incident_id: str,
        run_id: str | None = None,
        collector_run_id: str | None = None,
        unavailable_reason: str | None = None,
    ) -> Incident | None:
        """Mark that automatic diagnosis loop failed or produced unavailable state.

        Safe metadata only - no raw packet contents, logs, stack traces, or prompts.

        Args:
            incident_id: ID of the incident
            run_id: Optional run_id for the failed pass
            collector_run_id: Optional batch collector run ID
            unavailable_reason: Safe reason code
        Returns:
            Updated incident snapshot, or None if not found
        """
        return mark_diagnosis_loop_failed_for_store(self, incident_id, run_id, collector_run_id, unavailable_reason)

    def list_incidents_for_diagnosis_page(
        self,
        active_only: bool,
        limit: DiagnosisPageLimit,
        after_cursor: IncidentDiagnosisCursor | None,
    ) -> IncidentDiagnosisPage:
        """List incidents for diagnosis with keyset pagination.

        This method provides the page listing capability without exposing
        the raw connection to callers.

        For in-memory store, this returns a fallback page implementation.
        SQLite store provides the full keyset pagination.

        Args:
            active_only: If True, only return incidents in active status
            limit: Maximum number of incidents per page (DiagnosisPageLimit)
            after_cursor: Optional cursor to resume after

        Returns:
            IncidentDiagnosisPage with paginated results
        """
        # Get all incidents sorted by first_observed_at
        incidents = list(self._incidents.values())
        incidents.sort(key=lambda i: (i.first_observed_at or datetime.min, i.incident_id))

        # Use extracted pagination function
        return in_memory_pagination(incidents, active_only, limit, after_cursor)

    def __len__(self) -> int:
        """Return the number of incidents in the store."""
        return len(self._incidents)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"IncidentStore(incidents={len(self._incidents)})"


__all__ = [
    "IncidentStore",
]
