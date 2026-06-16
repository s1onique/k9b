"""Deterministic incident candidate detector.

This module produces incident candidates from collected cluster evidence.
It does NOT:
- open persistent incidents
- mutate cluster state
- call LLMs
- invoke external tools
- perform remediation

Candidates are deduplicated and use deterministic IDs based on:
- namespace + object_kind + object_name + candidate_class
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .incident_models import DeploymentSummary, EventSummary, PodSummary


class CandidateClass(StrEnum):
    """Incident candidate classification."""

    CRASH_LOOP = "crash_loop"
    IMAGE_PULL_ERROR = "image_pull_error"
    PENDING_POD = "pending_pod"
    FAILED_POD = "failed_pod"
    DEPLOYMENT_UNAVAILABLE = "deployment_unavailable"
    WARNING_EVENT_BURST = "warning_event_burst"
    UNKNOWN = "unknown"


class ObjectKind(StrEnum):
    """Kind of Kubernetes object."""

    POD = "Pod"
    DEPLOYMENT = "Deployment"
    EVENT = "Event"
    NODE = "Node"
    UNKNOWN = "Unknown"


# Known Kubernetes object kinds that map to ObjectKind values
_KNOWN_OBJECT_KINDS: dict[str, ObjectKind] = {
    "Pod": ObjectKind.POD,
    "Deployment": ObjectKind.DEPLOYMENT,
    "Event": ObjectKind.EVENT,
    "Node": ObjectKind.NODE,
}


def _safe_object_kind(kind: str | None) -> ObjectKind:
    """Convert a Kubernetes object kind string to ObjectKind safely.

    Unknown kinds (ReplicaSet, StatefulSet, Job, etc.) map to UNKNOWN.
    This prevents crashes on real cluster events with non-standard kinds.
    """
    if not kind:
        return ObjectKind.UNKNOWN
    return _KNOWN_OBJECT_KINDS.get(kind, ObjectKind.UNKNOWN)


class Severity(StrEnum):
    """Severity level for candidates."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class CandidateSignal:
    """Signal extracted from evidence that contributed to the candidate."""

    source: str  # pod, deployment, event
    reason: str
    message: str  # sanitized


@dataclass(frozen=True)
class IncidentCandidate:
    """A deterministic incident candidate derived from cluster evidence."""

    candidate_id: str
    namespace: str
    object_kind: ObjectKind
    object_name: str
    candidate_class: CandidateClass
    severity: Severity
    signals: tuple[CandidateSignal, ...]
    evidence_needed: tuple[str, ...]  # generic evidence types, not kubectl commands

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "namespace": self.namespace,
            "object_kind": self.object_kind.value,
            "object_name": self.object_name,
            "class": self.candidate_class.value,
            "severity": self.severity.value,
            "signals": [{"source": s.source, "reason": s.reason, "message": s.message} for s in self.signals],
            "evidence_needed": list(self.evidence_needed),
        }


def _sanitize_message(message: str | None, max_length: int = 200) -> str:
    """Sanitize a message for inclusion in a candidate signal.

    - Truncates to max_length
    - Removes potential secret patterns (Bearer tokens, passwords, etc.)
    - Strips excessive whitespace
    """
    if not message:
        return ""

    # Truncate first to avoid regex overhead on huge messages
    truncated = message[:max_length]

    # Remove common secret patterns (but NOT in kubectl command suggestions)
    # These patterns indicate credentials that shouldn't be in candidates
    secret_patterns = [
        r"(?i)(bearer\s+token[:\s]\S+)",
        r"(?i)(password[:\s]\S+)",
        r"(?i)(secret[:\s]\S+)",
        r"(?i)(token[:\s]\S{10,})",
        r"(?i)(api[_-]?key[:\s]\S+)",
        r"eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+",  # JWT
    ]

    sanitized = truncated
    for pattern in secret_patterns:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized)

    # Normalize whitespace
    sanitized = " ".join(sanitized.split())

    return sanitized


def _make_candidate_id(
    namespace: str,
    object_kind: ObjectKind,
    object_name: str,
    candidate_class: CandidateClass,
) -> str:
    """Create a deterministic candidate ID from components.

    Format: namespace-kind-name-class
    The ID is deterministic so repeated detections produce the same ID,
    enabling dedupe at the candidate level.
    """
    # Use lowercase and hyphens for consistency
    # Note: underscore in candidate_class is preserved (e.g., image_pull_error)
    parts = [
        namespace.lower(),
        object_kind.value.lower(),
        object_name.lower(),
        candidate_class.value.lower(),
    ]
    # Join with hyphen
    raw_id = "-".join(parts)
    # Sanitize for use as an ID (replace invalid chars but preserve underscores)
    sanitized = re.sub(r"[^a-z0-9_-]", "-", raw_id)
    # Collapse multiple hyphens
    sanitized = re.sub(r"-+", "-", sanitized)
    return sanitized


# Threshold for warning event burst detection
_WARNING_EVENT_BURST_THRESHOLD = 3


def detect_incident_candidates(
    pods: list[PodSummary] | tuple[PodSummary, ...],
    deployments: list[DeploymentSummary] | tuple[DeploymentSummary, ...],
    events: list[EventSummary] | tuple[EventSummary, ...],
) -> tuple[IncidentCandidate, ...]:
    """Detect incident candidates from collected cluster evidence.

    This function is pure and deterministic:
    - Same input produces same candidates
    - No side effects
    - No external calls

    Args:
        pods: List of pod summaries from the cluster
        deployments: List of deployment summaries from the cluster
        events: List of event summaries from the cluster

    Returns:
        Tuple of incident candidates, deduplicated and sorted by candidate_id
    """
    candidates: dict[str, IncidentCandidate] = {}

    # Track warning events by involved object for burst detection
    warning_events_by_object: dict[tuple[str, str, str], list[EventSummary]] = {}
    # Format: (namespace, object_kind, object_name) -> list of warning events

    # Phase 1: Process pods for candidate classes
    for pod in pods:
        if pod.namespace == "":
            continue  # Skip pods without namespace

        if pod.health_status.value == "crash_loop":
            candidate = _make_pod_candidate(
                pod=pod,
                candidate_class=CandidateClass.CRASH_LOOP,
                severity=Severity.ERROR,
                reason=pod.reason or "CrashLoopBackOff",
                message=pod.message,
                evidence_needed=("pod_logs", "pod_describe"),
            )
            candidates[candidate.candidate_id] = candidate

        elif pod.health_status.value == "image_pull_error":
            candidate = _make_pod_candidate(
                pod=pod,
                candidate_class=CandidateClass.IMAGE_PULL_ERROR,
                severity=Severity.ERROR,
                reason=pod.reason or "ImagePullBackOff",
                message=pod.message,
                evidence_needed=("pod_describe", "image_pull_status"),
            )
            candidates[candidate.candidate_id] = candidate

        elif pod.health_status.value == "pending":
            candidate = _make_pod_candidate(
                pod=pod,
                candidate_class=CandidateClass.PENDING_POD,
                severity=Severity.WARNING,
                reason="Pending",
                message=pod.message or "Pod stuck in Pending state",
                evidence_needed=("pod_describe", "node_capacity"),
            )
            candidates[candidate.candidate_id] = candidate

        elif pod.health_status.value == "failed":
            candidate = _make_pod_candidate(
                pod=pod,
                candidate_class=CandidateClass.FAILED_POD,
                severity=Severity.ERROR,
                reason=pod.reason or "Failed",
                message=pod.message or "Pod failed",
                evidence_needed=("pod_logs", "pod_events"),
            )
            candidates[candidate.candidate_id] = candidate

        # Track warning events for this pod
        # (We'll deduplicate after processing all events)

    # Phase 2: Process deployments
    for deployment in deployments:
        if deployment.namespace == "":
            continue

        if not deployment.available:
            candidate = _make_deployment_candidate(
                deployment=deployment,
                candidate_class=CandidateClass.DEPLOYMENT_UNAVAILABLE,
                severity=Severity.WARNING,
                reason="replicas_unavailable",
                message=(
                    f"Deployment {deployment.name} has {deployment.available_replicas}/"
                    f"{deployment.replicas} replicas available"
                ),
                evidence_needed=("deployment_describe", "replica_status"),
            )
            candidates[candidate.candidate_id] = candidate

    # Phase 3: Process events for warning event burst detection
    for event in events:
        if event.type != "Warning":
            continue
        if not event.involved_object_kind or not event.involved_object_name:
            continue

        key = (event.namespace, event.involved_object_kind, event.involved_object_name)
        if key not in warning_events_by_object:
            warning_events_by_object[key] = []
        warning_events_by_object[key].append(event)

    # Generate burst candidates from warning event groups
    for (namespace, object_kind_str, object_name), event_list in warning_events_by_object.items():
        if len(event_list) >= _WARNING_EVENT_BURST_THRESHOLD:
            # Deduplicate reasons within this group
            # Note: reasons are used for debugging/logging if needed later
            sorted(set(e.reason for e in event_list))

            # Create a stable ID for this burst
            # Use safe conversion to handle unknown Kubernetes kinds (ReplicaSet, StatefulSet, etc.)
            safe_kind = _safe_object_kind(object_kind_str)
            burst_id = _make_candidate_id(
                namespace=namespace,
                object_kind=safe_kind,
                object_name=object_name,
                candidate_class=CandidateClass.WARNING_EVENT_BURST,
            )

            # Build signals from the events
            signals: list[CandidateSignal] = []
            for event in event_list[:5]:  # Cap at 5 signals per candidate
                signals.append(
                    CandidateSignal(
                        source="event",
                        reason=event.reason,
                        message=_sanitize_message(event.message),
                    )
                )

            candidates[burst_id] = IncidentCandidate(
                candidate_id=burst_id,
                namespace=namespace,
                object_kind=safe_kind,
                object_name=object_name,
                candidate_class=CandidateClass.WARNING_EVENT_BURST,
                severity=Severity.WARNING,
                signals=tuple(signals),
                evidence_needed=("object_events", "object_describe"),
            )

    # Return sorted by candidate_id for deterministic output
    return tuple(sorted(candidates.values(), key=lambda c: c.candidate_id))


def _make_pod_candidate(
    pod: PodSummary,
    candidate_class: CandidateClass,
    severity: Severity,
    reason: str,
    message: str | None,
    evidence_needed: tuple[str, ...],
) -> IncidentCandidate:
    """Create a pod-based incident candidate."""
    return IncidentCandidate(
        candidate_id=_make_candidate_id(
            namespace=pod.namespace,
            object_kind=ObjectKind.POD,
            object_name=pod.name,
            candidate_class=candidate_class,
        ),
        namespace=pod.namespace,
        object_kind=ObjectKind.POD,
        object_name=pod.name,
        candidate_class=candidate_class,
        severity=severity,
        signals=(
            CandidateSignal(
                source="pod",
                reason=reason,
                message=_sanitize_message(message),
            ),
        ),
        evidence_needed=evidence_needed,
    )


def _make_deployment_candidate(
    deployment: DeploymentSummary,
    candidate_class: CandidateClass,
    severity: Severity,
    reason: str,
    message: str,
    evidence_needed: tuple[str, ...],
) -> IncidentCandidate:
    """Create a deployment-based incident candidate."""
    return IncidentCandidate(
        candidate_id=_make_candidate_id(
            namespace=deployment.namespace,
            object_kind=ObjectKind.DEPLOYMENT,
            object_name=deployment.name,
            candidate_class=candidate_class,
        ),
        namespace=deployment.namespace,
        object_kind=ObjectKind.DEPLOYMENT,
        object_name=deployment.name,
        candidate_class=candidate_class,
        severity=severity,
        signals=(
            CandidateSignal(
                source="deployment",
                reason=reason,
                message=_sanitize_message(message),
            ),
        ),
        evidence_needed=evidence_needed,
    )


__all__ = [
    "CandidateClass",
    "CandidateSignal",
    "IncidentCandidate",
    "ObjectKind",
    "Severity",
    "detect_incident_candidates",
]
