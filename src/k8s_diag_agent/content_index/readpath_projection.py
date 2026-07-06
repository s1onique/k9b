"""Content index projection API conversion helpers.

This module provides typed conversion functions that transform raw index projections
into API-compatible payloads for the k9b UI.

Schema Version: k9b.content_index.v1

Ownership:
    - index_summary_to_api_payload: Convert summary projection to IncidentSummaryPayload
    - index_detail_to_api_payload: Convert detail projection to IncidentDetailPayload
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import cast

from ..ui.api_payloads_incident_reads import (
    AutomaticDiagnosisLoopSummary,
    AutomaticDiagnosisReviewPayload,
    IncidentDetailPayload,
    IncidentReviewPacketPayload,
    IncidentSummaryPayload,
)

_logger = logging.getLogger(__name__)


# =============================================================================
# Default Values for Missing Fields
# =============================================================================

# Default review packet payload for index-provided incidents
# (index doesn't have review_packet from the full incident store)
_DEFAULT_REVIEW_PACKET: IncidentReviewPacketPayload = {
    "status": "unknown",
    "id": None,
    "generated_at": None,
    "error_message": None,
}

# Default automatic diagnosis review for index-provided incidents
# (index doesn't have review data from full incident store)
_DEFAULT_AUTO_DIAGNOSIS_REVIEW: AutomaticDiagnosisReviewPayload = {
    "available": False,
    "unavailable_reason": "no_review_packet",
    "provider_status": None,
}

# Default automatic diagnosis loop summary for index-provided incidents
_DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY: AutomaticDiagnosisLoopSummary = {
    "status": "not_run",
    "latest_started_at": None,
    "latest_completed_at": None,
    "latest_failed_at": None,
    "latest_event_id": None,
    "latest_event_type": None,
    "unavailable_reason": None,
    "checks_requested": None,
    "checks_run": None,
    "checks_rejected": None,
    "review_packet_available": False,
    "review_packet_id": None,
    "read_only": True,
    "review_required_before_any_action": True,
    "no_remediation_attempted": True,
    "pass_count": None,
    "pass_run_ids": None,
    "terminal_decision": None,
}


# =============================================================================
# API Conversion Helpers
# =============================================================================


def index_summary_to_api_payload(
    projection: Mapping[str, object],
) -> IncidentSummaryPayload:
    """Convert an index summary projection to an IncidentSummaryPayload.

    The index provides a minimal projection. This function:
    - Preserves all index-provided fields
    - Adds defaults for missing optional fields that direct path would provide
    - Validates required fields are present

    Args:
        projection: Raw projection dictionary from the index.

    Returns:
        IncidentSummaryPayload compatible with the API response shape.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    # Validate required fields
    required_fields = [
        "incident_id",
        "namespace",
        "object_kind",
        "object_name",
        "candidate_class",
        "severity",
        "status",
    ]

    for field in required_fields:
        if field not in projection:
            raise ValueError(f"Missing required field in summary projection: {field}")

    # Build the payload with index-provided fields
    payload: IncidentSummaryPayload = {
        "incident_id": str(projection["incident_id"]),
        "namespace": str(projection["namespace"]),
        "object_kind": str(projection["object_kind"]),
        "object_name": str(projection["object_name"]),
        "raw_object_kind": str(projection.get("raw_object_kind")) if projection.get("raw_object_kind") is not None else None,
        "candidate_class": str(projection["candidate_class"]),
        "severity": str(projection["severity"]),
        "status": str(projection["status"]),
        # Timestamps - may be missing from index
        "first_observed_at": str(projection.get("first_observed_at", "")),
        "last_observed_at": str(projection.get("last_observed_at", "")),
        # Counts - may be missing from index
        "signal_count": int(cast("int | None", projection.get("signal_count")) or 0),
        "evidence_count": int(cast("int | None", projection.get("evidence_count")) or 0),
        # Snapshot bundle - may be missing
        "latest_snapshot_bundle_id": str(projection.get("latest_snapshot_bundle_id")) if projection.get("latest_snapshot_bundle_id") is not None else None,
        # Review packet - use default (index doesn't have full store data)
        "review_packet": _DEFAULT_REVIEW_PACKET,
        # Suppression - use defaults
        "suppressed_reason": str(projection.get("suppressed_reason")) if projection.get("suppressed_reason") is not None else None,
        "duplicate_of": str(projection.get("duplicate_of")) if projection.get("duplicate_of") is not None else None,
        "resolved_at": str(projection.get("resolved_at")) if projection.get("resolved_at") is not None else None,
        "resolution_notes": str(projection.get("resolution_notes")) if projection.get("resolution_notes") is not None else None,
    }

    return payload


def index_detail_to_api_payload(
    projection: Mapping[str, object],
) -> IncidentDetailPayload:
    """Convert an index detail projection to an IncidentDetailPayload.

    The index provides a more complete projection for detail views. This function:
    - Preserves all index-provided fields
    - Adds defaults for missing fields that direct path would populate
    - Includes empty lists for signals/evidence/events/suggested_checks

    Args:
        projection: Raw projection dictionary from the index.

    Returns:
        IncidentDetailPayload compatible with the API response shape.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    # Validate required fields
    required_fields = [
        "incident_id",
        "namespace",
        "object_kind",
        "object_name",
        "candidate_class",
        "severity",
        "status",
        "source_candidate_id",
    ]

    for field in required_fields:
        if field not in projection:
            raise ValueError(f"Missing required field in detail projection: {field}")

    # Build the payload with index-provided fields
    payload: IncidentDetailPayload = {
        # Inherited from summary
        "incident_id": str(projection["incident_id"]),
        "namespace": str(projection["namespace"]),
        "object_kind": str(projection["object_kind"]),
        "object_name": str(projection["object_name"]),
        "raw_object_kind": str(projection.get("raw_object_kind")) if projection.get("raw_object_kind") is not None else None,
        "candidate_class": str(projection["candidate_class"]),
        "severity": str(projection["severity"]),
        "status": str(projection["status"]),
        "first_observed_at": str(projection.get("first_observed_at", "")),
        "last_observed_at": str(projection.get("last_observed_at", "")),
        "signal_count": int(cast("int | None", projection.get("signal_count")) or 0),
        "evidence_count": int(cast("int | None", projection.get("evidence_count")) or 0),
        "latest_snapshot_bundle_id": str(projection.get("latest_snapshot_bundle_id")) if projection.get("latest_snapshot_bundle_id") is not None else None,
        "review_packet": _DEFAULT_REVIEW_PACKET,
        "suppressed_reason": str(projection.get("suppressed_reason")) if projection.get("suppressed_reason") is not None else None,
        "duplicate_of": str(projection.get("duplicate_of")) if projection.get("duplicate_of") is not None else None,
        "resolved_at": str(projection.get("resolved_at")) if projection.get("resolved_at") is not None else None,
        "resolution_notes": str(projection.get("resolution_notes")) if projection.get("resolution_notes") is not None else None,
        # Additional detail fields
        "source_candidate_id": str(projection["source_candidate_id"]),
        # Empty lists for data not in index
        "signals": [],
        "evidence_needed": [],
        "evidence_links": [],
        "events": [],
        "evidence_artifacts": [],
        # Suggested checks not available from index
        "suggested_checks": [],
        # Default diagnosis review (not available from index)
        "automatic_diagnosis_review": _DEFAULT_AUTO_DIAGNOSIS_REVIEW,
        # Default diagnosis loop summary (not available from index)
        "automatic_diagnosis_loop_summary": _DEFAULT_AUTO_DIAGNOSIS_LOOP_SUMMARY,
    }

    return payload


def safe_index_summary_to_api_payload(
    projection: Mapping[str, object],
    fallback_reason: str,
) -> IncidentSummaryPayload | None:
    """Safely convert an index summary projection, returning None on error.

    This function wraps index_summary_to_api_payload with error handling.
    On any error, it logs the issue and returns None to trigger fallback.

    Args:
        projection: Raw projection dictionary from the index.
        fallback_reason: The fallback reason to log if conversion fails.

    Returns:
        IncidentSummaryPayload if conversion succeeds, None otherwise.
    """
    try:
        return index_summary_to_api_payload(projection)
    except (ValueError, TypeError, KeyError) as exc:
        _logger.debug(
            "Failed to convert summary projection to API payload: %s (fallback: %s)",
            exc,
            fallback_reason,
        )
        return None


def safe_index_detail_to_api_payload(
    projection: Mapping[str, object],
    fallback_reason: str,
) -> IncidentDetailPayload | None:
    """Safely convert an index detail projection, returning None on error.

    This function wraps index_detail_to_api_payload with error handling.
    On any error, it logs the issue and returns None to trigger fallback.

    Args:
        projection: Raw projection dictionary from the index.
        fallback_reason: The fallback reason to log if conversion fails.

    Returns:
        IncidentDetailPayload if conversion succeeds, None otherwise.
    """
    try:
        return index_detail_to_api_payload(projection)
    except (ValueError, TypeError, KeyError) as exc:
        _logger.debug(
            "Failed to convert detail projection to API payload: %s (fallback: %s)",
            exc,
            fallback_reason,
        )
        return None
