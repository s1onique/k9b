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
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from .incident_evidence import EvidenceLink, EvidenceRole
from .incident_review_packet_state import ReviewPacketState, ReviewPacketStatus
from .incident_transitions import (
    attach_evidence_artifact,
    mark_collecting_evidence,
    mark_duplicate,
    mark_ready_for_review,
    merge_candidate_into_incident,
    suppress_incident,
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
    # Transition functions
    "open_incident_from_candidate",
    "merge_candidate_into_incident",
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "suppress_incident",
    "mark_duplicate",
    "attach_evidence_artifact",
]
