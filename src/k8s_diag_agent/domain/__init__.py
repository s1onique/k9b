"""Typed incident lifecycle domain core.

This package provides a typed, pure domain layer for incident lifecycle transitions.
It is isolated from IO, Kubernetes, HTTP, subprocess, and store dependencies.

Modules:
- incident_lifecycle: Typed identifiers, status literals, lifecycle view, events,
  transition results, and pure transition functions.

Exports:
- IncidentId, SourceCandidateId, SnapshotBundleId, ReviewPacketId, DuplicateOfIncidentId
- IncidentStatus, IncidentLifecycle, IncidentLifecycleEvent
- IncidentLifecycleEventType, IncidentLifecycleActor
- TransitionApplied, TransitionRejected, TransitionRejectionReason, TransitionResult
- mark_collecting_evidence, mark_ready_for_review, mark_investigating
- suppress_incident, mark_duplicate, resolve_incident
"""

from __future__ import annotations

from k8s_diag_agent.domain.identifiers import (
    AlertSignalBatchId,
    AlertSignalId,
    AutomaticDiagnosisCollectorRunId,
    HealthRunId,
)
from k8s_diag_agent.domain.incident_lifecycle import (
    DuplicateOfIncidentId,
    # Identifiers
    IncidentId,
    # Lifecycle view
    IncidentLifecycle,
    IncidentLifecycleActor,
    # Events
    IncidentLifecycleEvent,
    IncidentLifecycleEventType,
    # Status
    IncidentStatus,
    ReviewPacketId,
    SnapshotBundleId,
    SourceCandidateId,
    # Transition results
    TransitionApplied,
    TransitionRejected,
    TransitionRejectionReason,
    TransitionResult,
    # Transition functions
    mark_collecting_evidence,
    mark_duplicate,
    mark_investigating,
    mark_ready_for_review,
    resolve_incident,
    suppress_incident,
)

__all__ = [
    # Identifiers
    "HealthRunId",
    "AlertSignalId",
    "AlertSignalBatchId",
    "AutomaticDiagnosisCollectorRunId",
    "IncidentId",
    "SourceCandidateId",
    "SnapshotBundleId",
    "ReviewPacketId",
    "DuplicateOfIncidentId",
    # Status
    "IncidentStatus",
    # Lifecycle view
    "IncidentLifecycle",
    # Events
    "IncidentLifecycleEvent",
    "IncidentLifecycleEventType",
    "IncidentLifecycleActor",
    # Transition results
    "TransitionApplied",
    "TransitionRejected",
    "TransitionRejectionReason",
    "TransitionResult",
    # Transition functions
    "mark_collecting_evidence",
    "mark_ready_for_review",
    "mark_investigating",
    "suppress_incident",
    "mark_duplicate",
    "resolve_incident",
]
