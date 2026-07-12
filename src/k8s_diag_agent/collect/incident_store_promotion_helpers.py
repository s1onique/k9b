"""Candidate promotion helpers for incident store.

Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.

The helpers in this module provide a typed promotion boundary so that
callers can correlate ``IncidentCandidate`` -> ``PromotionRecord`` ->
``Incident`` without post-hoc ``zip`` inference, addressing the
ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R1 regression concern.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
    PROMOTION_OUTCOME_UPDATED,
    PromotionRecord,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate
    from .incident_lifecycle import Incident
    from .incident_store import IncidentStore


@dataclass(frozen=True)
class PromotionOutcome:
    """Bundled per-candidate promotion outcome.

    Carries the typed ``PromotionRecord`` alongside the resulting
    ``Incident`` so callers do not have to correlate candidate and
    incident lists post-hoc via ``zip(..., strict=False)``. The list
    returned by ``promote_candidates_with_records`` is in the same
    order as the input candidates, and many candidates MAY collapse
    into a single canonical incident (e.g. duplicate candidates sharing
    the same correlation key); the ``incident_id`` field on the record
    is the authoritative source for that mapping.
    """

    record: PromotionRecord
    incident: Incident | None

    @property
    def canonical_incident_id(self) -> str | None:
        return self.record.canonical_incident_id

    @property
    def source_candidate_id(self) -> str:
        return self.record.source_candidate_id


def _outcome_name(opening: bool, updated: bool) -> str:
    """Map a per-candidate promotion action into a PromotionOutcome string."""
    if opening:
        return PROMOTION_OUTCOME_OPENED
    if updated:
        return PROMOTION_OUTCOME_UPDATED
    return PROMOTION_OUTCOME_SKIPPED_DUPLICATE


def promote_candidates_for_store(
    store: IncidentStore,
    candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> tuple[Incident, ...]:
    """Promote candidates into incidents. Return the resulting incidents.

    Use :func:`promote_candidates_with_records` if you need the typed
    ``PromotionRecord`` mapping for downstream canonical-id consumption.
    """
    from .incident_bundle_promotion import merge_candidate_into_incident_with_bundle
    from .incident_lifecycle import (
        incident_id_from_candidate,
        merge_candidate_into_incident,
        open_incident_from_candidate,
    )
    from .incident_lifecycle_transitions import store_mark_collecting_evidence

    updated_incidents: dict[str, Incident] = {}

    for candidate in candidates:
        incident_id = incident_id_from_candidate(candidate)

        if incident_id in store._incidents:
            # Merge into existing incident
            existing = store._incidents[incident_id]
            if snapshot_bundle_id is not None:
                updated = merge_candidate_into_incident_with_bundle(
                    existing, candidate, observed_at, snapshot_bundle_id
                )
            else:
                updated = merge_candidate_into_incident(existing, candidate, observed_at)
            store._incidents[incident_id] = updated
            updated_incidents[incident_id] = updated
        else:
            # Open new incident
            if snapshot_bundle_id is not None:
                # Create incident without bundle metadata - store_mark_collecting_evidence
                # will add the bundle attachment as part of the typed transition
                new_incident = open_incident_from_candidate(candidate, observed_at)
                store._incidents[incident_id] = new_incident
                # Transition to COLLECTING_EVIDENCE via typed store path
                # This also adds the bundle evidence link
                transitioned = store_mark_collecting_evidence(
                    store, incident_id, snapshot_bundle_id, now=observed_at
                )
                if transitioned is not None:
                    new_incident = transitioned
            else:
                new_incident = open_incident_from_candidate(candidate, observed_at)
                store._incidents[incident_id] = new_incident
            updated_incidents[incident_id] = new_incident

    # Return snapshot copies to avoid exposing internal state
    all_updated = [store._snapshot_incident(i) for i in updated_incidents.values()]
    return tuple(sorted(all_updated, key=lambda i: i.incident_id))


def promote_candidates_with_records(
    store: IncidentStore,
    candidates: Iterable[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> list[PromotionOutcome]:
    """Promote candidates and return typed per-candidate outcomes.

    The returned list is in the same order as the input candidates. Each
    ``PromotionOutcome`` carries the typed ``PromotionRecord`` and the
    resulting ``Incident`` so the caller can:

    * feed canonical incident IDs into automatic diagnosis without
      re-deriving them from labels, correlation keys, or store state;
    * handle ``many candidates -> one canonical incident`` collapse
      explicitly via the ``record.canonical_incident_id`` mapping;
    * avoid post-hoc ``zip(candidates, incidents)`` inference that
      silently breaks when the lists do not align.

    Candidate-level input order is preserved; canonical incident IDs MAY
    repeat across outputs (one canonical incident, many candidates).
    """
    from .incident_bundle_promotion import merge_candidate_into_incident_with_bundle
    from .incident_lifecycle import (
        incident_id_from_candidate,
        merge_candidate_into_incident,
        open_incident_from_candidate,
    )
    from .incident_lifecycle_transitions import store_mark_collecting_evidence

    outcomes: list[PromotionOutcome] = []
    for candidate in candidates:
        incident_id = incident_id_from_candidate(candidate)
        opened = False
        incident: Incident | None = None
        if incident_id in store._incidents:
            existing = store._incidents[incident_id]
            if snapshot_bundle_id is not None:
                updated = merge_candidate_into_incident_with_bundle(
                    existing, candidate, observed_at, snapshot_bundle_id
                )
            else:
                updated = merge_candidate_into_incident(existing, candidate, observed_at)
            store._incidents[incident_id] = updated
            incident = updated
        else:
            if snapshot_bundle_id is not None:
                new_incident = open_incident_from_candidate(candidate, observed_at)
                store._incidents[incident_id] = new_incident
                transitioned = store_mark_collecting_evidence(
                    store, incident_id, snapshot_bundle_id, now=observed_at
                )
                incident = transitioned or new_incident
            else:
                new_incident = open_incident_from_candidate(candidate, observed_at)
                store._incidents[incident_id] = new_incident
                incident = new_incident
            opened = True
        snapshot = store._snapshot_incident(incident) if incident is not None else None
        # The promotion outcome is OPENED if we just created the incident,
        # UPDATED if we merged into an existing one, and SKIPPED_DUPLICATE
        # if the candidate was effectively a duplicate (no-op merge).
        promotion_outcome = _outcome_name(opened, updated=not opened)
        record = PromotionRecord(
            source_candidate_id=candidate.candidate_id,
            canonical_incident_id=(
                snapshot.incident_id if snapshot is not None else incident_id
            ),
            promotion_outcome=promotion_outcome,
        )
        outcomes.append(
            PromotionOutcome(record=record, incident=snapshot)
        )
    return outcomes


# Import type alias for type checking
if TYPE_CHECKING:
    from .incident_store import IncidentStore  # noqa: F401  (re-export)


__all__ = [
    "PromotionOutcome",
    "promote_candidates_for_store",
    "promote_candidates_with_records",
]
