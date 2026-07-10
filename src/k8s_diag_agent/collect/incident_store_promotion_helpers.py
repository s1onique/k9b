"""Candidate promotion helpers for incident store.

Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate
    from .incident_lifecycle import Incident


def promote_candidates_for_store(
    store: IncidentStore,
    candidates: list[IncidentCandidate] | tuple[IncidentCandidate, ...],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> tuple[Incident, ...]:
    """Promote candidates into incidents.

    For each candidate:
    - If no matching incident exists, opens a new incident
      - With bundle_id provided: COLLECTING_EVIDENCE state
      - Without bundle_id: OPEN state (current behavior)
    - If matching incident exists (same dedupe key), merges signals into it
      - Status transitions based on terminal-ish status rules:
        - SUPPRESSED/DUPLICATE/RESOLVED: no status change
        - READY_FOR_REVIEW: no status change (no downgrade)
        - OPEN/COLLECTING_EVIDENCE/INVESTIGATING: transitions to COLLECTING_EVIDENCE
      - latest_snapshot_bundle_id updates to latest bundle ID when transitioning

    Args:
        store: The incident store
        candidates: Sequence of incident candidates to promote
        observed_at: When these candidates were observed
        snapshot_bundle_id: Optional ID of the snapshot bundle containing evidence.
    Returns:
        Tuple of all incidents (both new and updated), sorted by incident_id
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


# Import type alias for type checking
if TYPE_CHECKING:
    from .incident_store import IncidentStore


__all__ = [
    "promote_candidates_for_store",
]
