"""Incident snapshot helpers.

This module provides pure functions for creating incident snapshots.
Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_lifecycle import Incident


def snapshot_incident(incident: Incident) -> Incident:
    """Create a snapshot copy of an incident.

    This ensures internal mutable state is not exposed.
    ``diagnosis_loop`` is deep-copied because it is a
    ``dict[str, Any]`` projection field that may legitimately
    contain nested mutable structures; aliasing would allow
    callers to bypass the canonical event store and mutate
    the cached aggregate without a hash-chain entry.

    Extracted from IncidentStore to reduce file sizes.
    """
    from .incident_lifecycle import Incident

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
        evidence_links=list(incident.evidence_links),
        latest_snapshot_bundle_id=incident.latest_snapshot_bundle_id,
        review_packet=incident.review_packet,
        signal_count=incident.signal_count,
        evidence_count=incident.evidence_count,
        events=list(incident.events),
        # R4-4: round-trip the typed diagnosis-loop projection state
        # so detail reads and snapshots expose lifecycle data.
        # R5-1: deep-copy the projection dict so mutations on the
        # returned snapshot cannot reach back into the cached
        # aggregate and bypass the canonical event writer.
        diagnosis_loop=(
            deepcopy(incident.diagnosis_loop)
            if incident.diagnosis_loop is not None
            else None
        ),
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


__all__ = [
    "snapshot_incident",
]
