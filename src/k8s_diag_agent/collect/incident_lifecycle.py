"""Pure incident lifecycle management without remediation, mutation, or LLM calls.

This module provides:
- Incident record schema and state machine
- Deterministic incident ID generation from candidates
- Pure transition functions for lifecycle management

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO autonomous root-cause claims

State transitions implemented for this ACT:
- candidate → open
- open → collecting_evidence
- collecting_evidence → ready_for_review
- open → suppressed
- open → duplicate

Dedupe key: namespace + (object_kind or raw_object_kind) + object_name + candidate_class
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_candidates import IncidentCandidate


class IncidentStatus(StrEnum):
    """Lifecycle states for incidents."""

    # Initial state when candidate is promoted
    OPEN = "open"
    # Evidence collection in progress
    COLLECTING_EVIDENCE = "collecting_evidence"
    # Evidence collection complete, ready for review
    READY_FOR_REVIEW = "ready_for_review"
    # Under active investigation
    INVESTIGATING = "investigating"
    # Suppressed/acknowledged without action
    SUPPRESSED = "suppressed"
    # Marked as duplicate of another incident
    DUPLICATE = "duplicate"
    # Resolved (future ACT)
    RESOLVED = "resolved"


@dataclass(frozen=True)
class IncidentSignal:
    """Signal that contributed to the incident."""

    source: str
    reason: str
    message: str
    captured_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reason": self.reason,
            "message": self.message,
            "captured_at": self.captured_at.isoformat(),
        }


@dataclass
class Incident:
    """Internal incident record representing a k9b-managed incident.

    Incidents are created from deterministic candidates without:
    - Remediation actions
    - Kubernetes mutation
    - LLM calls
    - External tool invocation

    Dedupe key: namespace + (object_kind or raw_object_kind) + object_name + candidate_class
    Same dedupe key produces same incident_id (deterministic).

    State transitions:
    - open: initial state from candidate
    - collecting_evidence: evidence gathering in progress
    - ready_for_review: evidence available for review
    - investigating: under active investigation
    - suppressed: acknowledged without action
    - duplicate: marked as duplicate of another incident
    - resolved: resolved (future)
    """

    # Identity (deterministic from dedupe key)
    incident_id: str
    source_candidate_id: str

    # Object reference
    namespace: str
    object_kind: str  # ObjectKind.value or raw kind
    object_name: str
    raw_object_kind: str | None  # Preserved for UNKNOWN kinds

    # Classification
    candidate_class: str  # CandidateClass.value
    severity: str  # Severity.value
    status: IncidentStatus

    # Timestamps
    first_observed_at: datetime
    last_observed_at: datetime

    # Evidence
    signals: list[IncidentSignal] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    snapshot_bundle_id: str | None = None
    review_packet_available: bool = False
    review_packet_id: str | None = None

    # Suppression/duplicate metadata
    suppressed_reason: str | None = None
    duplicate_of: str | None = None

    # Resolution metadata (future)
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize incident to dictionary."""
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
            "snapshot_bundle_id": self.snapshot_bundle_id,
            "review_packet_available": self.review_packet_available,
            "review_packet_id": self.review_packet_id,
            "suppressed_reason": self.suppressed_reason,
            "duplicate_of": self.duplicate_of,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
        }


def make_incident_id(
    namespace: str,
    object_kind: str,
    object_name: str,
    candidate_class: str,
    raw_object_kind: str | None = None,
) -> str:
    """Create a deterministic incident ID from components.

    The ID is deterministic so repeated candidates produce the same incident ID,
    enabling deduplication at the incident level.

    Dedupe key: namespace + (object_kind or raw_object_kind) + object_name + candidate_class

    When raw_object_kind is provided (for UNKNOWN object kinds), it is used
    in the ID to prevent collision between different kinds (e.g., ReplicaSet/foo
    vs StatefulSet/foo).

    Format: namespace-kind-objectname-class
    """
    # When raw_object_kind is provided, use it for disambiguation
    kind_value: str
    if raw_object_kind:
        kind_value = raw_object_kind.lower()
    else:
        kind_value = object_kind.lower()

    parts = [
        namespace.lower(),
        kind_value,
        object_name.lower(),
        candidate_class.lower(),
    ]
    raw_id = "-".join(parts)
    # Sanitize for use as an ID (replace invalid chars but preserve underscores)
    sanitized = re.sub(r"[^a-z0-9_-]", "-", raw_id)
    # Collapse multiple hyphens
    sanitized = re.sub(r"-+", "-", sanitized)
    # Strip leading/trailing hyphens
    sanitized = sanitized.strip("-")
    return sanitized


def incident_id_from_candidate(candidate: IncidentCandidate) -> str:
    """Generate incident ID from a candidate.

    Preserves the candidate's raw_object_kind for disambiguation when
    the object_kind is UNKNOWN.
    """
    return make_incident_id(
        namespace=candidate.namespace,
        object_kind=candidate.object_kind.value,
        object_name=candidate.object_name,
        candidate_class=candidate.candidate_class.value,
        raw_object_kind=candidate.raw_object_kind,
    )


# =============================================================================
# Lifecycle transition functions (pure, no side effects on cluster)
# =============================================================================


def open_incident_from_candidate(candidate: IncidentCandidate, observed_at: datetime) -> Incident:
    """Create an incident record from a deterministic candidate.

    This is the candidate → open transition.

    Args:
        candidate: The deterministic incident candidate to promote
        observed_at: When this candidate was observed

    Returns:
        New incident in OPEN state

    Raises:
        Nothing - pure function with no side effects
    """
    # Import here to avoid circular imports at module level

    incident_id = incident_id_from_candidate(candidate)

    # Convert candidate signals to incident signals
    incident_signals: list[IncidentSignal] = []
    for sig in candidate.signals:
        incident_signals.append(
            IncidentSignal(
                source=sig.source,
                reason=sig.reason,
                message=sig.message,
                captured_at=observed_at,
            )
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
    )


def merge_candidate_into_incident(
    incident: Incident,
    candidate: IncidentCandidate,
    observed_at: datetime,
) -> Incident:
    """Merge a new candidate observation into an existing incident.

    Updates last_observed_at and appends new signals.
    Does NOT create a new incident identity.

    Args:
        incident: Existing incident record
        candidate: New candidate observation
        observed_at: When this candidate was observed

    Returns:
        Updated incident with new signals and updated timestamp
    """
    # Import here to avoid circular imports at module level

    # Convert candidate signals to incident signals
    new_signals: list[IncidentSignal] = []
    for sig in candidate.signals:
        new_signals.append(
            IncidentSignal(
                source=sig.source,
                reason=sig.reason,
                message=sig.message,
                captured_at=observed_at,
            )
        )

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
        last_observed_at=observed_at,
        signals=incident.signals + new_signals,
        evidence_needed=list(incident.evidence_needed),
        snapshot_bundle_id=incident.snapshot_bundle_id,
        review_packet_available=incident.review_packet_available,
        review_packet_id=incident.review_packet_id,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


def mark_collecting_evidence(incident: Incident, bundle_id: str) -> Incident:
    """Transition incident to COLLECTING_EVIDENCE state.

    Records the snapshot bundle ID that will contain evidence.

    Args:
        incident: Existing incident record
        bundle_id: ID of the snapshot bundle being collected

    Returns:
        Updated incident in COLLECTING_EVIDENCE state
    """
    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=IncidentStatus.COLLECTING_EVIDENCE,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signals=list(incident.signals),
        evidence_needed=list(incident.evidence_needed),
        snapshot_bundle_id=bundle_id,
        review_packet_available=incident.review_packet_available,
        review_packet_id=incident.review_packet_id,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


def mark_ready_for_review(incident: Incident, review_packet_id: str | None = None) -> Incident:
    """Transition incident to READY_FOR_REVIEW state.

    Indicates evidence collection is complete and a review packet is available.

    Args:
        incident: Existing incident record
        review_packet_id: Optional ID of the review packet if generated

    Returns:
        Updated incident in READY_FOR_REVIEW state
    """
    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=IncidentStatus.READY_FOR_REVIEW,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signals=list(incident.signals),
        evidence_needed=list(incident.evidence_needed),
        snapshot_bundle_id=incident.snapshot_bundle_id,
        review_packet_available=True,
        review_packet_id=review_packet_id or incident.review_packet_id,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


def suppress_incident(incident: Incident, reason: str) -> Incident:
    """Transition incident to SUPPRESSED state.

    Records suppression reason (e.g., known issue, maintenance window, etc.).

    Args:
        incident: Existing incident record
        reason: Human-readable reason for suppression

    Returns:
        Updated incident in SUPPRESSED state
    """
    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=IncidentStatus.SUPPRESSED,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signals=list(incident.signals),
        evidence_needed=list(incident.evidence_needed),
        snapshot_bundle_id=incident.snapshot_bundle_id,
        review_packet_available=incident.review_packet_available,
        review_packet_id=incident.review_packet_id,
        suppressed_reason=reason,
        duplicate_of=incident.duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


def mark_duplicate(incident: Incident, duplicate_of: str) -> Incident:
    """Transition incident to DUPLICATE state.

    Records the incident_id of the primary incident this is a duplicate of.

    Args:
        incident: Existing incident record
        duplicate_of: incident_id of the primary incident

    Returns:
        Updated incident in DUPLICATE state
    """
    return Incident(
        incident_id=incident.incident_id,
        source_candidate_id=incident.source_candidate_id,
        namespace=incident.namespace,
        object_kind=incident.object_kind,
        object_name=incident.object_name,
        raw_object_kind=incident.raw_object_kind,
        candidate_class=incident.candidate_class,
        severity=incident.severity,
        status=IncidentStatus.DUPLICATE,
        first_observed_at=incident.first_observed_at,
        last_observed_at=incident.last_observed_at,
        signals=list(incident.signals),
        evidence_needed=list(incident.evidence_needed),
        snapshot_bundle_id=incident.snapshot_bundle_id,
        review_packet_available=incident.review_packet_available,
        review_packet_id=incident.review_packet_id,
        suppressed_reason=incident.suppressed_reason,
        duplicate_of=duplicate_of,
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
    )


__all__ = [
    "Incident",
    "IncidentSignal",
    "IncidentStatus",
    "incident_id_from_candidate",
    "make_incident_id",
    "mark_collecting_evidence",
    "mark_duplicate",
    "mark_ready_for_review",
    "merge_candidate_into_incident",
    "open_incident_from_candidate",
    "suppress_incident",
]
