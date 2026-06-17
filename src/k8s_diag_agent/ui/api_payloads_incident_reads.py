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

from typing import Any, Literal, TypedDict

__all__ = [
    "IncidentSignalPayload",
    "IncidentEvidenceLinkPayload",
    "IncidentReviewPacketPayload",
    "IncidentEventPayload",
    "IncidentSuggestedCheckPayload",
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


class IncidentSuggestedCheckPayload(TypedDict, total=False):
    """Read-only suggested-check compatibility projection for incident detail views.

    This payload provides a read-only view of suggested checks that may be
    associated with an incident. It is NOT a fully implemented persistence object.

    The status field indicates the mapping reliability:
    - "suggested": Next-check artifact successfully mapped to incident
    - "compatibility": Legacy artifact without reliable incident mapping
    - "unknown": No mapping attempted or mapping failed

    Hard constraints:
    - NO check execution
    - NO manual promotion
    - NO remediation actions
    - NO Kubernetes mutation
    - NO LLM calls
    """

    check_id: str  # Unique identifier for this suggested check
    title: str  # Human-readable check title
    rationale: str  # Why this check is suggested
    source: str  # Origin of suggestion (e.g., "next-check-planning", "diagnostic-pack")
    risk_level: str | None  # Risk assessment (LOW, MEDIUM, HIGH) or null
    status: Literal["suggested", "compatibility", "unknown"]  # Mapping status
    artifact_id: str | None  # Source artifact ID if available
    run_id: str | None  # Associated run ID if available


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

    Includes signals, evidence links, timeline, and suggested checks.
    Run artifacts remain evidence provenance, not the primary case object.

    Note: suggested_checks is a read-only compatibility projection.
    Currently returns empty list as no reliable next-check-to-incident mapping exists.
    See docs/data-model/next-checks.md for target direction.
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
    # Suggested checks - read-only compatibility projection
    # Returns empty list when no next-check-to-incident mapping exists
    suggested_checks: list[IncidentSuggestedCheckPayload]
