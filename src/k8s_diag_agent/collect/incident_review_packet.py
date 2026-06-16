"""Internal incident review packet generator for k9b's own reviewer pipeline.

This module generates self-contained review packets from incident evidence bundles.
The packet is an internal k9b product artifact used by k9b's incident investigation
workflow - NOT a copy/paste artifact for external tools.

Hard constraint: End-state must be k9b-only and self-contained.
The complete incident investigation workflow must run inside k9b:
- no Cline required
- no manual kubectl required
- no operator exec into pods required
- no local CLI required
- no copy/paste to external tools required
- no external artifact massaging required

Development-time helpers are allowed, but every helper must either:
1. become an internal k9b backend/UI capability, or
2. be explicitly marked as temporary scaffolding and removed before the epic closes.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as DatetimeClass
from typing import Any

from .incident_models import IncidentEvidenceBundle
from .incident_review_packet_markdown import (
    K9B_SELF_CONTAINED_CONSTRAINT,
    REVIEWER_CONSTRAINTS,
    build_constraint_sections,
    build_header,
    join_lines,
)
from .incident_review_packet_sections import (
    build_candidates_section,
    build_collection_errors_section,
    build_deployment_health_section,
    build_evidence_summary,
    build_failing_pods_section,
    build_known_limitations_section,
    build_metadata_section,
    build_next_evidence_questions,
    build_raw_evidence_index,
    build_symptoms_section,
    build_warning_events_section,
)


def generate_incident_review_packet(
    bundle: IncidentEvidenceBundle,
) -> str:
    """Generate a deterministic, bounded, k9b-owned review packet.

    This packet is an internal product artifact used by k9b's incident
    investigation workflow, not a copy/paste artifact for external tools.

    Args:
        bundle: Incident evidence bundle from snapshot capture

    Returns:
        Markdown-formatted review packet

    Required packet contents:
    - metadata
    - evidence summary
    - detected symptoms
    - failing pods
    - deployment health
    - warning events
    - collection errors
    - known limitations
    - reviewer instructions
    - questions for next evidence collection
    - raw evidence index
    """
    sections = [
        build_header(),
        build_metadata_section(bundle),
        build_evidence_summary(bundle),
        build_symptoms_section(bundle),
        build_failing_pods_section(bundle),
        build_deployment_health_section(bundle),
        build_warning_events_section(bundle),
        build_candidates_section(bundle),
        build_collection_errors_section(bundle),
        build_known_limitations_section(),
        build_raw_evidence_index(bundle),
        build_constraint_sections(),
        build_next_evidence_questions(bundle),
    ]

    return join_lines(sections)


def generate_incident_review_packet_from_dict(
    bundle_data: dict[str, Any],
) -> str:
    """Generate review packet from bundle dict (for API responses).

    Args:
        bundle_data: Dictionary representation of IncidentEvidenceBundle

    Returns:
        Markdown-formatted review packet

    Raises:
        ValueError: If required bundle fields are missing
    """

    from .incident_models import (
        DeploymentSummary,
        EventSummary,
        IncidentBundleMetadata,
        IncidentEvidenceBundle,
        IncidentSymptom,
        PodHealthStatus,
        PodSummary,
    )

    # Parse metadata
    meta_data = bundle_data.get("metadata", {})
    metadata = IncidentBundleMetadata(
        bundle_id=meta_data.get("bundle_id", ""),
        captured_at=_parse_datetime(meta_data.get("captured_at")),
        namespace=meta_data.get("namespace", ""),
        since_hours=meta_data.get("since_hours", 2),
        context=meta_data.get("context"),
        total_pods=meta_data.get("total_pods", 0),
        total_events=meta_data.get("total_events", 0),
        total_deployments=meta_data.get("total_deployments", 0),
        failing_pods_count=meta_data.get("failing_pods_count", 0),
        symptoms_count=meta_data.get("symptoms_count", 0),
    )

    # Parse pods
    pods = []
    for pod_data in bundle_data.get("pods", []):
        health_status_str = pod_data.get("health_status", "unknown")
        if isinstance(health_status_str, str):
            try:
                health_status = PodHealthStatus(health_status_str)
            except ValueError:
                health_status = PodHealthStatus.UNKNOWN
        else:
            health_status = health_status_str
        pods.append(PodSummary(
            name=pod_data.get("name", ""),
            namespace=pod_data.get("namespace", ""),
            phase=pod_data.get("phase", ""),
            health_status=health_status,
            restart_count=pod_data.get("restart_count", 0),
            node=pod_data.get("node"),
            image_refs=tuple(pod_data.get("image_refs", [])),
            reason=pod_data.get("reason"),
            message=pod_data.get("message"),
            is_failing=pod_data.get("is_failing", False),
        ))

    # Parse events
    events = []
    for event_data in bundle_data.get("events", []):
        events.append(EventSummary(
            namespace=event_data.get("namespace", ""),
            name=event_data.get("name", ""),
            type=event_data.get("type", ""),
            reason=event_data.get("reason", ""),
            message=event_data.get("message", ""),
            involved_object_kind=event_data.get("involved_object_kind"),
            involved_object_name=event_data.get("involved_object_name"),
            count=event_data.get("count", 0),
            last_timestamp=event_data.get("last_timestamp"),
        ))

    # Parse deployments
    deployments = []
    for deploy_data in bundle_data.get("deployments", []):
        deployments.append(DeploymentSummary(
            name=deploy_data.get("name", ""),
            namespace=deploy_data.get("namespace", ""),
            replicas=deploy_data.get("replicas", 0),
            available_replicas=deploy_data.get("available_replicas", 0),
            ready_replicas=deploy_data.get("ready_replicas", 0),
            updated_replicas=deploy_data.get("updated_replicas", 0),
            available=deploy_data.get("available", False),
        ))

    # Parse symptoms
    symptoms = []
    for symptom_data in bundle_data.get("symptoms", []):
        symptoms.append(IncidentSymptom(
            symptom_type=symptom_data.get("symptom_type", ""),
            pod_name=symptom_data.get("pod_name"),
            message=symptom_data.get("message", ""),
            severity=symptom_data.get("severity", "warning"),
        ))

    # Parse collection errors
    collection_errors = tuple(bundle_data.get("collection_errors", []))

    # Parse candidates - handle both dict and object format
    from .incident_candidates import (
        CandidateClass,
        CandidateSignal,
        IncidentCandidate,
        ObjectKind,
        Severity,
    )
    candidates: list[IncidentCandidate] = []
    for cand_data in bundle_data.get("candidates", []):
        severity_str = cand_data.get("severity", "warning")
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.WARNING

        # Parse object_kind
        kind_str = cand_data.get("object_kind", "Unknown")
        try:
            object_kind = ObjectKind(kind_str)
        except ValueError:
            object_kind = ObjectKind.UNKNOWN

        # Parse candidate_class
        class_str = cand_data.get("class", "unknown")
        try:
            candidate_class = CandidateClass(class_str)
        except ValueError:
            candidate_class = CandidateClass.UNKNOWN

        # Parse signals
        signals: list[CandidateSignal] = []
        for sig_data in cand_data.get("signals", []):
            signals.append(CandidateSignal(
                source=sig_data.get("source", ""),
                reason=sig_data.get("reason", ""),
                message=sig_data.get("message", ""),
            ))

        candidates.append(IncidentCandidate(
            candidate_id=cand_data.get("candidate_id", ""),
            namespace=cand_data.get("namespace", ""),
            object_kind=object_kind,
            object_name=cand_data.get("object_name", ""),
            candidate_class=candidate_class,
            severity=severity,
            signals=tuple(signals),
            evidence_needed=tuple(cand_data.get("evidence_needed", [])),
            raw_object_kind=cand_data.get("raw_object_kind"),
        ))

    # Build bundle
    bundle = IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=collection_errors,
        candidates=tuple(candidates),
    )

    return generate_incident_review_packet(bundle)


def _parse_datetime(value: str | DatetimeClass | None) -> DatetimeClass:
    """Parse datetime string to datetime object."""
    if isinstance(value, DatetimeClass):
        return value
    if not isinstance(value, str):
        return DatetimeClass.now(UTC)
    # Try ISO format with timezone
    try:
        return DatetimeClass.fromisoformat(value)
    except ValueError:
        pass
    # Try parsing without timezone and attach UTC
    try:
        # Handle "+00:00" suffix
        if '+' in value:
            base = value.split('+')[0]
            return DatetimeClass.fromisoformat(base).replace(tzinfo=UTC)
        return DatetimeClass.fromisoformat(value)
    except ValueError:
        return DatetimeClass.now(UTC)


__all__ = [
    "generate_incident_review_packet",
    "generate_incident_review_packet_from_dict",
    "K9B_SELF_CONTAINED_CONSTRAINT",
    "REVIEWER_CONSTRAINTS",
]
