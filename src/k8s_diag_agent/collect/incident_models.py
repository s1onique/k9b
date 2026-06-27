"""Data models for incident snapshot collection.

This module contains dataclasses and enums for representing
Kubernetes incident evidence bundles.

Key constraints:
- Read-only: no mutation, no remediation
- Sanitized: secrets, tokens, auth headers redacted
- Bounded: namespace + time-scoped evidence
- Deterministic: consistent bundle layout
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k8s_diag_agent.collect.incident_candidates import IncidentCandidate


class PodHealthStatus(StrEnum):
    """Pod health classification for incident triage."""

    RUNNING = "running"
    PENDING = "pending"
    FAILED = "failed"
    CRASH_LOOP = "crash_loop"
    IMAGE_PULL_ERROR = "image_pull_error"
    READINESS_FAILURE = "readiness_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PodSummary:
    """Minimal pod evidence for incident bundle."""

    name: str
    namespace: str
    phase: str
    health_status: PodHealthStatus
    restart_count: int
    node: str | None
    image_refs: tuple[str, ...]
    reason: str | None
    message: str | None
    is_failing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "phase": self.phase,
            "health_status": self.health_status.value,
            "restart_count": self.restart_count,
            "node": self.node,
            "image_refs": list(self.image_refs),
            "reason": self.reason,
            "message": self.message,
            "is_failing": self.is_failing,
        }


@dataclass(frozen=True)
class EventSummary:
    """Minimal event evidence for incident bundle."""

    namespace: str
    name: str
    type: str
    reason: str
    message: str
    involved_object_kind: str | None
    involved_object_name: str | None
    count: int
    last_timestamp: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "type": self.type,
            "reason": self.reason,
            "message": self.message,
            "involved_object_kind": self.involved_object_kind,
            "involved_object_name": self.involved_object_name,
            "count": self.count,
            "last_timestamp": self.last_timestamp,
        }


@dataclass(frozen=True)
class DeploymentSummary:
    """Minimal deployment evidence for incident bundle."""

    name: str
    namespace: str
    replicas: int
    available_replicas: int
    ready_replicas: int
    updated_replicas: int
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "available_replicas": self.available_replicas,
            "ready_replicas": self.ready_replicas,
            "updated_replicas": self.updated_replicas,
            "available": self.available,
        }


@dataclass(frozen=True)
class IncidentSymptom:
    """Detected incident symptom for triage."""

    symptom_type: str
    pod_name: str | None
    message: str
    severity: str  # warning, error

    def to_dict(self) -> dict[str, Any]:
        return {
            "symptom_type": self.symptom_type,
            "pod_name": self.pod_name,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class IncidentBundleMetadata:
    """Metadata for the incident evidence bundle."""

    bundle_id: str
    captured_at: datetime
    namespace: str
    since_hours: int
    context: str | None
    total_pods: int
    total_events: int
    total_deployments: int
    failing_pods_count: int
    symptoms_count: int
    candidates_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "captured_at": self.captured_at.isoformat(),
            "namespace": self.namespace,
            "since_hours": self.since_hours,
            "context": self.context,
            "total_pods": self.total_pods,
            "total_events": self.total_events,
            "total_deployments": self.total_deployments,
            "failing_pods_count": self.failing_pods_count,
            "symptoms_count": self.symptoms_count,
            "candidates_count": self.candidates_count,
        }


@dataclass
class IncidentEvidenceBundle:
    """Complete incident evidence bundle."""

    metadata: IncidentBundleMetadata
    pods: list[PodSummary]
    events: list[EventSummary]
    deployments: list[DeploymentSummary]
    symptoms: list[IncidentSymptom]
    collection_errors: tuple[str, ...] = field(default_factory=tuple)
    candidates: tuple[IncidentCandidate, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "pods": [p.to_dict() for p in self.pods],
            "events": [e.to_dict() for e in self.events],
            "deployments": [d.to_dict() for d in self.deployments],
            "symptoms": [s.to_dict() for s in self.symptoms],
            "collection_errors": list(self.collection_errors),
            "candidates": [c.to_dict() for c in self.candidates],
        }


__all__ = [
    "IncidentEvidenceBundle",
    "IncidentBundleMetadata",
    "PodSummary",
    "DeploymentSummary",
    "EventSummary",
    "IncidentSymptom",
    "PodHealthStatus",
]
