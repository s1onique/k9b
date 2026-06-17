"""TypedDict payload definitions for incident read models.

This module contains pure data contracts (TypedDict definitions) for the incident
aggregate root read projections. These definitions are the canonical JSON key schemas
for the API serialization layer.

Ownership:
    - TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api_incident_reads.py.

Design notes:
    - IncidentSummaryPayload: lightweight list view with review_packet state object
    - IncidentDetailPayload: full case view with signals, evidence links, timeline
    - Uses latest_snapshot_bundle_id (not snapshot_bundle_id)
    - Uses review_packet object (not review_packet_available + review_packet_id)
"""

from __future__ import annotations

from typing import Any, TypedDict

__all__ = [
    "IncidentSignalPayload",
    "IncidentEvidenceLinkPayload",
    "IncidentReviewPacketPayload",
    "IncidentEventPayload",
    "IncidentSummaryPayload",
    "IncidentDetailPayload",
]


# =============================================================================
# TypedDict Payloads
# =============================================================================


class IncidentSignalPayload(TypedDict, total=False):
    """Signal that contributed to an incident.

    Provenance fields (run_id, detector_id, finding_id, fingerprint) are optional.
    """

    source: str
    reason: str
    message: str
    captured_at: str
    run_id: str | None
    detector_id: str | None
    finding_id: str | None
    fingerprint: str | None


class IncidentEvidenceLinkPayload(TypedDict, total=False):
    """Link between an incident and an evidence artifact.

    Evidence artifacts are external and linked, not embedded.
    """

    incident_id: str
    artifact_id: str
    role: str
    attached_at: str


class IncidentReviewPacketPayload(TypedDict, total=False):
    """Review packet state for an incident.

    Replaces the old pattern of:
        review_packet_available: bool
        review_packet_id: str | None

    This model makes state explicit and prevents drift.
    """

    status: str
    id: str | None
    generated_at: str | None
    error_message: str | None


class IncidentEventPayload(TypedDict, total=False):
    """Append-only timeline event in an incident's lifecycle.

    Events explain how an incident reached its current state.
    """

    event_id: str
    incident_id: str
    event_type: str
    actor: str
    occurred_at: str
    message: str
    actor_id: str | None
    data: dict[str, Any] | None


class IncidentSummaryPayload(TypedDict, total=False):
    """Lightweight incident payload for list views.

    Uses latest_snapshot_bundle_id (not snapshot_bundle_id).
    Uses review_packet object (not review_packet_available + review_packet_id).
    """

    incident_id: str
    namespace: str
    object_kind: str
    object_name: str
    raw_object_kind: str | None
    candidate_class: str
    severity: str
    status: str
    first_observed_at: str
    last_observed_at: str
    signal_count: int
    evidence_count: int
    latest_snapshot_bundle_id: str | None
    review_packet: IncidentReviewPacketPayload
    suppressed_reason: str | None
    duplicate_of: str | None
    resolved_at: str | None
    resolution_notes: str | None


class IncidentDetailPayload(TypedDict, total=False):
    """Full incident payload for detail views.

    Includes signals, evidence links, and timeline.
    Run artifacts remain evidence provenance, not the primary case object.
    """

    # Inherited from summary
    incident_id: str
    namespace: str
    object_kind: str
    object_name: str
    raw_object_kind: str | None
    candidate_class: str
    severity: str
    status: str
    first_observed_at: str
    last_observed_at: str
    signal_count: int
    evidence_count: int
    latest_snapshot_bundle_id: str | None
    review_packet: IncidentReviewPacketPayload
    suppressed_reason: str | None
    duplicate_of: str | None
    resolved_at: str | None
    resolution_notes: str | None
    # Additional detail fields
    source_candidate_id: str
    signals: list[IncidentSignalPayload]
    evidence_needed: list[str]
    evidence_links: list[IncidentEvidenceLinkPayload]
    events: list[IncidentEventPayload]
