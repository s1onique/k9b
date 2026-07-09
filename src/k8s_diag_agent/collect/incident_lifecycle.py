"""Pure incident lifecycle management without remediation, mutation, or LLM calls.

This module provides the Incident record schema and status enum.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims

State transitions are provided by incident_transitions.py.

Modules:
- incident_evidence.py: EvidenceArtifact, EvidenceLink, EvidenceKind, EvidenceRole
- incident_events.py: IncidentEvent, IncidentEventType, IncidentEventActor
- incident_review_packet_state.py: ReviewPacketState, ReviewPacketStatus
- incident_transitions.py: Pure transition functions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from k8s_diag_agent.domain.incident_lifecycle import (
    IncidentId,
    IncidentLifecycle,
    ReviewPacketId,
    SnapshotBundleId,
    SourceCandidateId,
    TransitionApplied,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_collecting_evidence as domain_mark_collecting_evidence,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    mark_ready_for_review as domain_mark_ready_for_review,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    suppress_incident as domain_suppress_incident,
)

from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_evidence import EvidenceLink, EvidenceRole
from .incident_review_packet_state import ReviewPacketState, ReviewPacketStatus
from .incident_transitions import (
    attach_evidence_artifact,
    merge_candidate_into_incident,
)

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


class IncidentStatus(StrEnum):
    """Lifecycle states for incidents."""

    OPEN = "open"
    COLLECTING_EVIDENCE = "collecting_evidence"
    READY_FOR_REVIEW = "ready_for_review"
    INVESTIGATING = "investigating"
    SUPPRESSED = "suppressed"
    DUPLICATE = "duplicate"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class IncidentSignal:
    """Signal that contributed to the incident."""

    source: str
    reason: str
    message: str
    captured_at: datetime
    run_id: str | None = None
    detector_id: str | None = None
    finding_id: str | None = None
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source": self.source,
            "reason": self.reason,
            "message": self.message,
            "captured_at": self.captured_at.isoformat(),
        }
        for opt in ("run_id", "detector_id", "finding_id", "fingerprint"):
            val = getattr(self, opt)
            if val is not None:
                result[opt] = val
        return result


@dataclass
class Incident:
    """Internal incident record - aggregate root for k9b incident management."""

    incident_id: str
    source_candidate_id: str
    namespace: str
    object_kind: str
    object_name: str
    raw_object_kind: str | None
    candidate_class: str
    severity: str
    status: IncidentStatus
    first_observed_at: datetime
    last_observed_at: datetime
    signals: list[IncidentSignal] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    evidence_links: list[EvidenceLink] = field(default_factory=list)
    latest_snapshot_bundle_id: str | None = None
    review_packet: ReviewPacketState = field(default_factory=ReviewPacketState.not_generated)
    signal_count: int = 0
    evidence_count: int = 0
    events: list[IncidentEvent] = field(default_factory=list)
    suppressed_reason: str | None = None
    duplicate_of: str | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "source_candidate_id": self.source_candidate_id,
            "namespace": self.namespace,
            "object_kind": self.object_kind,
            "object_name": self.object_name,
            "raw_object_kind": self.raw_object_kind,
            "class": self.candidate_class,
            "severity": self.severity,
            "status": self.status.value,
            "first_observed_at": self.first_observed_at.isoformat(),
            "last_observed_at": self.last_observed_at.isoformat(),
            "signals": [s.to_dict() for s in self.signals],
            "evidence_needed": list(self.evidence_needed),
            "evidence_links": [e.to_dict() for e in self.evidence_links],
            "latest_snapshot_bundle_id": self.latest_snapshot_bundle_id,
            "review_packet": self.review_packet.to_dict(),
            "signal_count": self.signal_count,
            "evidence_count": self.evidence_count,
            "events": [e.to_dict() for e in self.events],
            "suppressed_reason": self.suppressed_reason,
            "duplicate_of": self.duplicate_of,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Incident:
        """Reconstruct an Incident from a dict (e.g., loaded from JSON).

        Args:
            data: Dict representation of an incident.

        Returns:
            Reconstructed Incident instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If field values are invalid.
        """
        from datetime import datetime

        from .incident_events import IncidentEvent
        from .incident_evidence import EvidenceLink
        from .incident_review_packet_state import ReviewPacketState

        # Parse datetime fields
        def _parse_datetime(value: str | None) -> datetime | None:
            if value is None:
                return None
            return datetime.fromisoformat(value)

        # Reconstruct signals
        signals = []
        for s in data.get("signals", []):
            captured_at = _parse_datetime(s.get("captured_at"))
            if captured_at is None:
                captured_at = datetime.now(UTC)
            signals.append(IncidentSignal(
                source=s["source"],
                reason=s["reason"],
                message=s["message"],
                captured_at=captured_at,
                run_id=s.get("run_id"),
                detector_id=s.get("detector_id"),
                finding_id=s.get("finding_id"),
                fingerprint=s.get("fingerprint"),
            ))

        # Reconstruct evidence links
        evidence_links = []
        for e in data.get("evidence_links", []):
            # Convert role string to EvidenceRole enum
            role_value = e["role"]
            if isinstance(role_value, str):
                role = EvidenceRole(role_value)
            else:
                role = role_value
            # attached_at is optional, use current time if missing
            attached_at = _parse_datetime(e.get("attached_at"))
            if attached_at is None:
                attached_at = datetime.now(UTC)
            evidence_links.append(EvidenceLink(
                incident_id=e["incident_id"],
                artifact_id=e["artifact_id"],
                role=role,
                attached_at=attached_at,
            ))

        # Reconstruct events
        events = []
        for e in data.get("events", []):
            occurred_at = _parse_datetime(e["occurred_at"])
            if occurred_at is None:
                raise ValueError(f"Event {e.get('event_id', 'unknown')} missing required occurred_at")

            # Handle event_type - may be string or enum
            event_type = e["event_type"]
            if isinstance(event_type, str):
                event_type = IncidentEventType(event_type)

            # Handle actor - may be string or enum
            actor = e["actor"]
            if isinstance(actor, str):
                actor = IncidentEventActor(actor)

            events.append(IncidentEvent(
                event_id=e["event_id"],
                incident_id=e["incident_id"],
                event_type=event_type,
                actor=actor,
                occurred_at=occurred_at,
                message=e["message"],
                actor_id=e.get("actor_id"),
                data=e.get("data"),
            ))

        # Reconstruct review packet state
        review_packet_data = data.get("review_packet", {})
        # Convert status string to ReviewPacketStatus enum
        rp_status_value = review_packet_data.get("status", "not_generated")
        if isinstance(rp_status_value, str):
            rp_status = ReviewPacketStatus(rp_status_value)
        else:
            rp_status = rp_status_value
        review_packet = ReviewPacketState(
            status=rp_status,
            id=review_packet_data.get("id"),
            generated_at=_parse_datetime(review_packet_data.get("generated_at")),
            error_message=review_packet_data.get("error_message"),
        )

        # Convert status string to IncidentStatus enum
        status_value = data["status"]
        if isinstance(status_value, str):
            status = IncidentStatus(status_value)
        else:
            status = status_value

        # Parse required datetime fields - fail if missing
        first_observed_at = _parse_datetime(data["first_observed_at"])
        if first_observed_at is None:
            raise ValueError("Incident missing required first_observed_at field")

        last_observed_at = _parse_datetime(data["last_observed_at"])
        if last_observed_at is None:
            raise ValueError("Incident missing required last_observed_at field")

        return cls(
            incident_id=data["incident_id"],
            source_candidate_id=data["source_candidate_id"],
            namespace=data["namespace"],
            object_kind=data["object_kind"],
            object_name=data["object_name"],
            raw_object_kind=data.get("raw_object_kind"),
            candidate_class=data["class"],
            severity=data["severity"],
            status=status,
            first_observed_at=first_observed_at,
            last_observed_at=last_observed_at,
            signals=signals,
            evidence_needed=list(data.get("evidence_needed", [])),
            evidence_links=evidence_links,
            latest_snapshot_bundle_id=data.get("latest_snapshot_bundle_id"),
            review_packet=review_packet,
            signal_count=data.get("signal_count", len(signals)),
            evidence_count=data.get("evidence_count", len(evidence_links)),
            events=events,
            suppressed_reason=data.get("suppressed_reason"),
            duplicate_of=data.get("duplicate_of"),
            resolved_at=_parse_datetime(data.get("resolved_at")),
            resolution_notes=data.get("resolution_notes"),
        )

    def get_timeline(self) -> list[IncidentEvent]:
        """Get timeline sorted by occurrence time."""
        return sorted(self.events, key=lambda e: e.occurred_at)

    def get_latest_snapshot_bundle_id(self) -> str | None:
        """Get latest snapshot bundle ID."""
        return self.latest_snapshot_bundle_id


def make_incident_id(
    namespace: str,
    object_kind: str,
    object_name: str,
    candidate_class: str,
    raw_object_kind: str | None = None,
) -> str:
    """Create deterministic incident ID from components."""
    kind_value = raw_object_kind.lower() if raw_object_kind else object_kind.lower()
    parts = [namespace.lower(), kind_value, object_name.lower(), candidate_class.lower()]
    raw_id = "-".join(parts)
    return re.sub(r"[^a-z0-9_-]", "-", re.sub(r"-+", "-", raw_id)).strip("-")


def incident_id_from_candidate(candidate: IncidentCandidate) -> str:
    """Generate incident ID from a candidate."""
    return make_incident_id(
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        candidate_class=candidate.candidate_class.value,
        raw_object_kind=candidate.raw_object_kind,
    )


def open_incident_from_candidate(candidate: IncidentCandidate, observed_at: datetime) -> Incident:
    """Create an incident record from a deterministic candidate."""
    incident_id = incident_id_from_candidate(candidate)

    incident_signals = [
        IncidentSignal(
            source=sig.source,
            reason=sig.reason,
            message=sig.message,
            captured_at=observed_at,
        )
        for sig in candidate.signals
    ]

    # Create OPENED event for timeline
    opened_event = IncidentEvent(
        event_id=make_event_id(incident_id, "opened", observed_at),
        incident_id=incident_id,
        event_type=IncidentEventType.OPENED,
        actor=IncidentEventActor.SYSTEM,
        occurred_at=observed_at,
        message="Incident opened from candidate",
        data={"candidate_id": candidate.candidate_id, "signal_count": len(incident_signals)},
    )

    return Incident(
        incident_id=incident_id,
        source_candidate_id=candidate.candidate_id,
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        raw_object_kind=candidate.raw_object_kind,
        candidate_class=candidate.candidate_class.value,
        severity=candidate.severity.value,
        status=IncidentStatus.OPEN,
        first_observed_at=observed_at,
        last_observed_at=observed_at,
        signals=incident_signals,
        evidence_needed=list(candidate.evidence_needed),
        signal_count=len(incident_signals),
        events=[opened_event],
    )


# -----------------------------------------------------------------------------
# Pure adapter functions for status transitions (compatibility surface)
# These delegate to the typed domain core while preserving pure function semantics.
# -----------------------------------------------------------------------------

def _to_lifecycle(incident: Incident) -> IncidentLifecycle:
    """Convert an Incident to the domain IncidentLifecycle type."""
    return IncidentLifecycle(
        incident_id=IncidentId(incident.incident_id),
        source_candidate_id=SourceCandidateId(incident.source_candidate_id),
        status=incident.status.value,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signal_count=incident.signal_count,
        evidence_count=incident.evidence_count,
    )


def _map_transition_result(
    incident: Incident,
    result: TransitionApplied,
    *,
    preserve_last_observed_at: datetime | None = None,
) -> Incident:
    """Map a TransitionApplied result back to the Incident model.

    Args:
        incident: The original incident
        result: The transition result from domain core
        preserve_last_observed_at: If provided, use this timestamp instead of domain's
    """
    from dataclasses import replace

    status_map: dict[str, IncidentStatus] = {
        "open": IncidentStatus.OPEN,
        "collecting_evidence": IncidentStatus.COLLECTING_EVIDENCE,
        "ready_for_review": IncidentStatus.READY_FOR_REVIEW,
        "investigating": IncidentStatus.INVESTIGATING,
        "suppressed": IncidentStatus.SUPPRESSED,
        "duplicate": IncidentStatus.DUPLICATE,
        "resolved": IncidentStatus.RESOLVED,
    }

    new_lifecycle = result.incident
    new_status = status_map.get(new_lifecycle.status, incident.status)

    # Map domain events to incident events
    event_type_map = {
        "incident_promoted": IncidentEventType.OPENED,
        "incident_marked_collecting_evidence": IncidentEventType.EVIDENCE_COLLECTION_STARTED,
        "incident_marked_ready_for_review": IncidentEventType.REVIEW_PACKET_GENERATED,
        "incident_marked_investigating": IncidentEventType.STATUS_CHANGED,
        "incident_suppressed": IncidentEventType.SUPPRESSED,
        "incident_marked_duplicate": IncidentEventType.MARKED_DUPLICATE,
        "incident_resolved": IncidentEventType.CLOSED,
    }

    actor_map = {
        "system": IncidentEventActor.SYSTEM,
        "user": IncidentEventActor.USER,
        "diagnosis_loop": IncidentEventActor.SYSTEM,
        "test": IncidentEventActor.SYSTEM,
    }

    new_events = []
    for event in result.events:
        event_type = event_type_map.get(event.event_type, IncidentEventType.STATUS_CHANGED)
        actor = actor_map.get(event.actor, IncidentEventActor.SYSTEM)
        occurred_at = event.created_at
        new_events.append(IncidentEvent(
            event_id=make_event_id(incident.incident_id, event.event_type, occurred_at),
            incident_id=incident.incident_id,
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            message=event.detail or f"Transition: {event.event_type}",
            data={"lifecycle_event": event.event_type, "detail": event.detail},
        ))

    # Use preserved timestamp if provided, otherwise use domain's timestamp
    effective_last_observed_at = (
        preserve_last_observed_at if preserve_last_observed_at is not None
        else new_lifecycle.last_observed_at
    )

    return replace(
        incident,
        status=new_status,
        last_observed_at=effective_last_observed_at,
        events=incident.events + new_events,
    )


def mark_collecting_evidence(
    incident: Incident,
    bundle_id: str,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to COLLECTING_EVIDENCE state (pure function).

    Args:
        incident: The incident to transition
        bundle_id: ID of the snapshot bundle being collected
        now: Optional timestamp (defaults to current time)

    Returns:
        New incident with updated status
    """
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    result = domain_mark_collecting_evidence(
        lifecycle,
        bundle_id=SnapshotBundleId(bundle_id),
        actor="system",
        now=now,
    )

    match result:
        case TransitionApplied():
            return _map_transition_result(incident, result, preserve_last_observed_at=now)
    # TransitionRejected should not happen for OPEN -> COLLECTING_EVIDENCE
    return incident


def mark_ready_for_review(
    incident: Incident,
    review_packet_id: str,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to READY_FOR_REVIEW state (pure function).

    Args:
        incident: The incident to transition
        review_packet_id: ID of the review packet
        now: Optional timestamp (defaults to current time)

    Returns:
        New incident with updated status
    """
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    result = domain_mark_ready_for_review(
        lifecycle,
        review_packet_id=ReviewPacketId(review_packet_id),
        actor="system",
        now=now,
    )

    match result:
        case TransitionApplied():
            return _map_transition_result(incident, result, preserve_last_observed_at=now)
    # TransitionRejected should not happen for COLLECTING_EVIDENCE -> READY_FOR_REVIEW
    return incident


def suppress_incident(
    incident: Incident,
    reason: str,
    *,
    now: datetime | None = None,
) -> Incident:
    """Transition incident to SUPPRESSED state (pure function).

    Args:
        incident: The incident to suppress
        reason: Human-readable reason for suppression
        now: Optional timestamp (defaults to current time)

    Returns:
        New incident with updated status
    """
    now = now or datetime.now(UTC)
    lifecycle = _to_lifecycle(incident)

    result = domain_suppress_incident(
        lifecycle,
        reason=reason,
        actor="user",
        now=now,
    )

    match result:
        case TransitionApplied():
            return _map_transition_result(incident, result, preserve_last_observed_at=now)
    # TransitionRejected should not happen for valid transitions
    return incident


__all__ = [
    # Core models
    "Incident",
    "IncidentSignal",
    "IncidentStatus",
    "IncidentEvent",
    "IncidentEventType",
    "IncidentEventActor",
    # Evidence models
    "EvidenceLink",
    "EvidenceRole",
    # Review packet state
    "ReviewPacketState",
    "ReviewPacketStatus",
    # Helper functions
    "make_incident_id",
    "incident_id_from_candidate",
    "make_event_id",
    # Incident creation
    "open_incident_from_candidate",
    # Non-status transition functions
    "merge_candidate_into_incident",
    "attach_evidence_artifact",
    # Status transition functions (pure, compatibility surface)
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "suppress_incident",
]
