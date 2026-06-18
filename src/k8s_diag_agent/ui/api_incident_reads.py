"""Read-only serializers for the incident aggregate root.

This module provides serialization functions for incident read payloads.
Incident is the central lifecycle aggregate root; artifacts remain evidence provenance.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only for this module)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .api_payloads_incident_reads import (
    IncidentDetailPayload,
    IncidentEventPayload,
    IncidentEvidenceLinkPayload,
    IncidentReviewPacketPayload,
    IncidentSignalPayload,
    IncidentSuggestedCheckPayload,
    IncidentSummaryPayload,
)
from .incident_suggested_checks import build_suggested_checks_from_next_check_plan_payload

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from ..collect.incident_events import IncidentEvent
    from ..collect.incident_evidence import EvidenceLink
    from ..collect.incident_lifecycle import Incident, IncidentSignal
    from ..collect.incident_review_packet_state import ReviewPacketState


__all__ = [
    "build_incident_signal_payload",
    "build_incident_evidence_link_payload",
    "build_incident_review_packet_payload",
    "build_incident_event_payload",
    "build_incident_summary_payload",
    "build_incident_detail_payload",
]


# =============================================================================
# Serializer Functions
# =============================================================================


def build_incident_signal_payload(signal: IncidentSignal) -> IncidentSignalPayload:
    """Build IncidentSignalPayload from IncidentSignal model."""
    result: IncidentSignalPayload = {
        "source": signal.source,
        "reason": signal.reason,
        "message": signal.message,
        "captured_at": signal.captured_at.isoformat(),
    }
    for opt in ("run_id", "detector_id", "finding_id", "fingerprint"):
        val = getattr(signal, opt)
        if val is not None:
            result[opt] = val
    return result


def build_incident_evidence_link_payload(link: EvidenceLink) -> IncidentEvidenceLinkPayload:
    """Build IncidentEvidenceLinkPayload from EvidenceLink model."""
    return {
        "incident_id": link.incident_id,
        "artifact_id": link.artifact_id,
        "role": link.role.value,
        "attached_at": link.attached_at.isoformat(),
    }


def build_incident_review_packet_payload(state: ReviewPacketState) -> IncidentReviewPacketPayload:
    """Build IncidentReviewPacketPayload from ReviewPacketState model.

    Replaces old review_packet_available + review_packet_id pattern.
    """
    result: IncidentReviewPacketPayload = {
        "status": state.status.value,
    }
    if state.id is not None:
        result["id"] = state.id
    if state.generated_at is not None:
        result["generated_at"] = state.generated_at.isoformat()
    if state.error_message is not None:
        result["error_message"] = state.error_message
    return result


def build_incident_event_payload(event: IncidentEvent) -> IncidentEventPayload:
    """Build IncidentEventPayload from IncidentEvent model."""
    result: IncidentEventPayload = {
        "event_id": event.event_id,
        "incident_id": event.incident_id,
        "event_type": event.event_type.value,
        "actor": event.actor.value,
        "occurred_at": event.occurred_at.isoformat(),
        "message": event.message,
    }
    if event.actor_id is not None:
        result["actor_id"] = event.actor_id
    if event.data is not None:
        result["data"] = event.data
    return result


def build_incident_summary_payload(incident: Incident) -> IncidentSummaryPayload:
    """Build IncidentSummaryPayload from Incident model.

    Lightweight list view payload.
    Uses latest_snapshot_bundle_id (not snapshot_bundle_id).
    Uses review_packet object (not review_packet_available + review_packet_id).
    """
    return {
        "incident_id": incident.incident_id,
        "namespace": incident.namespace,
        "object_kind": incident.object_kind,
        "object_name": incident.object_name,
        "raw_object_kind": incident.raw_object_kind,
        "candidate_class": incident.candidate_class,
        "severity": incident.severity,
        "status": incident.status.value,
        "first_observed_at": incident.first_observed_at.isoformat(),
        "last_observed_at": incident.last_observed_at.isoformat(),
        "signal_count": incident.signal_count,
        "evidence_count": incident.evidence_count,
        "latest_snapshot_bundle_id": incident.latest_snapshot_bundle_id,
        "review_packet": build_incident_review_packet_payload(incident.review_packet),
        "suppressed_reason": incident.suppressed_reason,
        "duplicate_of": incident.duplicate_of,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "resolution_notes": incident.resolution_notes,
    }


def build_incident_detail_payload(
    incident: Incident,
    *,
    next_check_plan_payloads: Iterable[Mapping[str, object]] | None = None,
    # Legacy single-payload parameter for backward compatibility
    next_check_plan_payload: Mapping[str, object] | None = None,
) -> IncidentDetailPayload:
    """Build IncidentDetailPayload from Incident model.

    Full case view with signals, evidence links, timeline, and suggested checks.
    Run artifacts remain evidence provenance, not the primary case object.

    Args:
        incident: The incident model to serialize
        next_check_plan_payloads: Optional iterable of pre-loaded next-check plan
            artifact payloads. When provided, suggested_checks will be populated
            from candidates where linkage_status="linked" and incident_id matches.
        next_check_plan_payload: Legacy single-payload parameter. If provided and
            next_check_plan_payloads is None, this is used for backward compatibility.

    Note: suggested_checks is a read-only compatibility projection.
    When no plan payloads provided, returns empty list.
    When provided, extracts only SAFE linked candidates.
    """
    # Build suggested checks from plan payloads if available
    # Handle both new iterable parameter and legacy single-payload parameter
    if next_check_plan_payloads is None and next_check_plan_payload is not None:
        # Legacy backward-compatible path
        next_check_plan_payloads = (next_check_plan_payload,)

    if next_check_plan_payloads is not None:
        suggested_checks: list[IncidentSuggestedCheckPayload] = []
        for plan_payload in next_check_plan_payloads:
            checks = build_suggested_checks_from_next_check_plan_payload(
                incident.incident_id,
                plan_payload,
            )
            suggested_checks.extend(checks)
    else:
        suggested_checks = []

    # Build the payload explicitly to avoid type: ignore
    result: IncidentDetailPayload = {
        "incident_id": incident.incident_id,
        "namespace": incident.namespace,
        "object_kind": incident.object_kind,
        "object_name": incident.object_name,
        "raw_object_kind": incident.raw_object_kind,
        "candidate_class": incident.candidate_class,
        "severity": incident.severity,
        "status": incident.status.value,
        "first_observed_at": incident.first_observed_at.isoformat(),
        "last_observed_at": incident.last_observed_at.isoformat(),
        "signal_count": incident.signal_count,
        "evidence_count": incident.evidence_count,
        "latest_snapshot_bundle_id": incident.latest_snapshot_bundle_id,
        "review_packet": build_incident_review_packet_payload(incident.review_packet),
        "suppressed_reason": incident.suppressed_reason,
        "duplicate_of": incident.duplicate_of,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "resolution_notes": incident.resolution_notes,
        # Detail-only fields
        "source_candidate_id": incident.source_candidate_id,
        "signals": [build_incident_signal_payload(s) for s in incident.signals],
        "evidence_needed": list(incident.evidence_needed),
        "evidence_links": [build_incident_evidence_link_payload(e) for e in incident.evidence_links],
        "events": [build_incident_event_payload(e) for e in incident.get_timeline()],
        # Suggested checks - read-only compatibility projection
        # Populated from next-check plan artifacts with SAFE linkage
        "suggested_checks": suggested_checks,
    }
    return result
