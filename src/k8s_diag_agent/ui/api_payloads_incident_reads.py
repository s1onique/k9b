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
    "AutomaticDiagnosisReviewPayload",
    "AutomaticDiagnosisReviewHandoffPayload",
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


class AutomaticDiagnosisReviewPayload(TypedDict, total=False):
    """Bounded automatic diagnosis review packet summary for incident detail views.

    This payload provides a safe, read-only summary of the latest automatic
    diagnosis loop review packet for an incident. It exposes metadata only
    and does NOT include raw packet contents, paths, or secrets.

    Safety constraints enforced:
    - artifact_name is filename only (no path)
    - All string fields are bounded (max lengths enforced at serialization)
    - read_only is always True
    - review_required_before_any_action is always True
    - no_remediation_attempted is always True

    Hard constraints:
    - NO remediation actions
    - NO raw packet contents
    - NO absolute paths
    - NO secrets, tokens, or kubeconfig
    """

    # Availability state
    available: bool  # True if a review packet exists and is loadable

    # When available=True: bounded summary fields
    artifact_type: str | None  # Always "diagnosis-loop-review-packet" when available
    artifact_name: str | None  # Filename only, no path (max 240 chars)
    run_id: str | None  # Collector run ID (max 160 chars)
    collector_run_id: str | None  # Batch collector run ID (max 160 chars)
    generated_at: str | None  # ISO timestamp (max 80 chars)
    decision: str | None  # Loop decision (max 120 chars)
    checks_requested: int | None  # Number of checks requested
    checks_run: int | None  # Number of checks actually run
    checks_rejected: int | None  # Number of checks rejected
    eligible: bool | None  # Whether incident was eligible
    eligibility_reason: str | None  # Reason for eligibility (max 160 chars)
    read_only: bool | None  # Always True
    review_required_before_any_action: bool | None  # Always True
    no_remediation_attempted: bool | None  # Always True

    # When available=False: reason for unavailability
    unavailable_reason: str | None  # "no_review_packet" or "malformed_review_packet"


class AutomaticDiagnosisReviewHandoffPayload(TypedDict, total=False):
    """Bounded handoff payload for automatic diagnosis review packets.

    This payload provides a safe, read-only markdown handoff for the latest
    automatic diagnosis loop review packet. The handoff is suitable for
    human/ChatGPT review and does NOT include raw packet contents, paths, or secrets.

    Safety constraints enforced:
    - artifact_name is filename only (no path)
    - All string fields are bounded (max lengths enforced)
    - content is bounded to 16 KiB max
    - content includes explicit read-only/review-required/no-remediation language
    - read_only is always True
    - review_required_before_any_action is always True
    - no_remediation_attempted is always True

    Hard constraints:
    - NO remediation actions
    - NO raw packet contents beyond bounded summary fields
    - NO absolute paths
    - NO secrets, tokens, or kubeconfig
    """

    # Availability state
    available: bool  # True if a review packet exists and is loadable

    # When available=True: handoff fields
    incident_id: str | None  # The incident ID (max 160 chars)
    artifact_type: str | None  # Always "diagnosis-loop-review-packet" when available
    artifact_name: str | None  # Filename only, no path (max 240 chars)
    run_id: str | None  # Collector run ID (max 160 chars)
    collector_run_id: str | None  # Batch collector run ID (max 160 chars)
    generated_at: str | None  # ISO timestamp (max 80 chars)
    format: str | None  # Always "markdown" when available
    content: str | None  # Bounded markdown content (max 16 KiB)
    content_sha256: str | None  # SHA256 of content (first 16 chars)
    read_only: bool | None  # Always True
    review_required_before_any_action: bool | None  # Always True
    no_remediation_attempted: bool | None  # Always True

    # When available=False: reason for unavailability
    unavailable_reason: str | None  # "no_review_packet" or "malformed_review_packet"


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

    Includes signals, evidence links, timeline, suggested checks, and
    automatic diagnosis review summary.

    Run artifacts remain evidence provenance, not the primary case object.

    Note: suggested_checks is a read-only compatibility projection.
    Currently returns empty list as no reliable next-check-to-incident mapping exists.
    See docs/data-model/next-checks.md for target direction.

    Note: automatic_diagnosis_review provides a bounded summary of the latest
    automatic diagnosis loop review packet. Raw packet contents are not exposed.
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
    # Automatic diagnosis review - bounded summary only
    # Returns unavailable state when no packet exists or packet is malformed
    automatic_diagnosis_review: AutomaticDiagnosisReviewPayload