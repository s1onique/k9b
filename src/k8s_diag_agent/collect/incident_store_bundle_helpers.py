"""Bundle-related helpers for incident store.

Extracted from incident_store.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_lifecycle import Incident


def find_incidents_by_bundle_id_for_store(
    store: IncidentStore,
    snapshot_bundle_id: str,
) -> tuple[Incident, ...]:
    """Find all incidents with matching snapshot_bundle_id.

    This is used to link review packet generation back to incidents.

    Protected status rule: Does not update SUPPRESSED, DUPLICATE, or RESOLVED
    incidents unless explicitly justified. These are considered terminal-ish states.

    Args:
        store: The incident store
        snapshot_bundle_id: The bundle ID to search for
    Returns:
        Tuple of matching incidents (excluding protected statuses)
    """
    from .incident_lifecycle import IncidentStatus

    matching: list[Incident] = []
    for incident in store._incidents.values():
        if incident.latest_snapshot_bundle_id == snapshot_bundle_id:
            # Do not include protected statuses (terminal-ish states)
            if incident.status in (
                IncidentStatus.SUPPRESSED,
                IncidentStatus.DUPLICATE,
                IncidentStatus.RESOLVED,
            ):
                continue
            matching.append(store._snapshot_incident(incident))

    return tuple(sorted(matching, key=lambda i: i.incident_id))


def attach_evidence_to_incident(
    store: IncidentStore,
    incident_id: str,
    artifact_id: str,
    role: EvidenceRole,
) -> Incident | None:
    """Attach an evidence artifact to the incident.

    Args:
        store: The incident store
        incident_id: ID of the incident to attach evidence to
        artifact_id: ID of the evidence artifact
        role: Role of the evidence
    Returns:
        Updated incident snapshot, or None if not found
    """
    from .incident_evidence import make_artifact_id
    from .incident_lifecycle import attach_evidence_artifact as _attach_evidence_artifact

    incident = store._incidents.get(incident_id)
    if incident is None:
        return None

    # Use branded ID at the construction seam
    branded_artifact_id = make_artifact_id(artifact_id)
    updated = _attach_evidence_artifact(incident, branded_artifact_id, role)
    store._incidents[incident_id] = updated
    return store._snapshot_incident(updated)


# Import type alias for type checking
if TYPE_CHECKING:
    from .incident_evidence import EvidenceRole
    from .incident_store import IncidentStore


__all__ = [
    "find_incidents_by_bundle_id_for_store",
    "attach_evidence_to_incident",
]
