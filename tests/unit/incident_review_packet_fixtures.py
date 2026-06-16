"""Test fixtures for incident review packet tests.

This module contains shared test bundle fixtures used by multiple test files.
"""

from __future__ import annotations

from datetime import datetime

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_models import (
    DeploymentSummary,
    EventSummary,
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    IncidentSymptom,
    PodHealthStatus,
    PodSummary,
)


def make_test_bundle() -> IncidentEvidenceBundle:
    """Create a test bundle with crashloop pod."""
    metadata = IncidentBundleMetadata(
        bundle_id="test-bundle-001",
        captured_at=datetime(2024, 1, 15, 12, 0, 0),
        namespace="default",
        since_hours=2,
        context=None,
        total_pods=5,
        total_events=3,
        total_deployments=2,
        failing_pods_count=2,
        symptoms_count=3,
    )

    pods = [
        PodSummary(
            name="healthy-pod",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.RUNNING,
            restart_count=0,
            node="node-1",
            image_refs=("nginx:1.21",),
            reason=None,
            message=None,
            is_failing=False,
        ),
        PodSummary(
            name="crashloop-pod",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.CRASH_LOOP,
            restart_count=5,
            node="node-1",
            image_refs=("broken:v1",),
            reason="CrashLoopBackOff",
            message="Back-off 5m40s restarting",
            is_failing=True,
        ),
    ]

    events = [
        EventSummary(
            namespace="default",
            name="event-1",
            type="Warning",
            reason="BackOff",
            message="Back-off restarting container crashloop-pod",
            involved_object_kind="Pod",
            involved_object_name="crashloop-pod",
            count=3,
            last_timestamp="2024-01-15T12:00:00Z",
        ),
    ]

    deployments = [
        DeploymentSummary(
            name="nginx-deployment",
            namespace="default",
            replicas=3,
            available_replicas=3,
            ready_replicas=3,
            updated_replicas=3,
            available=True,
        ),
    ]

    symptoms = [
        IncidentSymptom(
            symptom_type="crash_loop",
            pod_name="crashloop-pod",
            message="Pod crashloop-pod in CrashLoopBackOff",
            severity="error",
        ),
    ]

    # Include a crashloop candidate
    candidates = (
        IncidentCandidate(
            candidate_id="cand-001",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="crashloop-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(source="pod", reason="CrashLoopBackOff", message="Pod crashloop-pod in CrashLoopBackOff"),
                CandidateSignal(source="event", reason="BackOff", message="Warning event for crashloop-pod"),
            ),
            evidence_needed=("container_logs",),
            raw_object_kind=None,
        ),
    )

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=(),
        candidates=candidates,
    )


def make_test_bundle_with_unknown_kind() -> IncidentEvidenceBundle:
    """Create a test bundle with a candidate that has unknown object kind (e.g., ReplicaSet)."""
    metadata = IncidentBundleMetadata(
        bundle_id="test-bundle-002",
        captured_at=datetime(2024, 1, 15, 12, 0, 0),
        namespace="default",
        since_hours=2,
        context=None,
        total_pods=3,
        total_events=5,
        total_deployments=1,
        failing_pods_count=1,
        symptoms_count=1,
    )

    pods = [
        PodSummary(
            name="rs-pod-xyz",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.RUNNING,
            restart_count=0,
            node="node-1",
            image_refs=("nginx:1.21",),
            reason=None,
            message=None,
            is_failing=False,
        ),
    ]

    events = [
        EventSummary(
            namespace="default",
            name="burst-event-1",
            type="Warning",
            reason="Warning",
            message="Warning event burst detected",
            involved_object_kind="ReplicaSet",
            involved_object_name="my-replicaset-abc123",
            count=10,
            last_timestamp="2024-01-15T12:00:00Z",
        ),
    ]

    deployments = [
        DeploymentSummary(
            name="my-deployment",
            namespace="default",
            replicas=3,
            available_replicas=3,
            ready_replicas=3,
            updated_replicas=3,
            available=True,
        ),
    ]

    symptoms = [
        IncidentSymptom(
            symptom_type="warning_event_burst",
            pod_name="rs-pod-xyz",
            message="Warning event burst for ReplicaSet my-replicaset-abc123",
            severity="warning",
        ),
    ]

    # Include candidates with raw_object_kind preserved for unknown kinds
    candidates = (
        IncidentCandidate(
            candidate_id="cand-002",
            namespace="default",
            object_kind=ObjectKind.UNKNOWN,
            object_name="my-replicaset-abc123",
            candidate_class=CandidateClass.WARNING_EVENT_BURST,
            severity=Severity.WARNING,
            signals=(
                CandidateSignal(source="event", reason="Warning", message="Warning event burst for ReplicaSet my-replicaset-abc123"),
            ),
            evidence_needed=("recent_events",),
            raw_object_kind="ReplicaSet",
        ),
    )

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=(),
        candidates=candidates,
    )


def make_test_bundle_no_candidates() -> IncidentEvidenceBundle:
    """Create a test bundle with no incident candidates."""
    metadata = IncidentBundleMetadata(
        bundle_id="test-bundle-003",
        captured_at=datetime(2024, 1, 15, 12, 0, 0),
        namespace="default",
        since_hours=2,
        context=None,
        total_pods=3,
        total_events=1,
        total_deployments=1,
        failing_pods_count=0,
        symptoms_count=0,
    )

    pods = [
        PodSummary(
            name="healthy-pod",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.RUNNING,
            restart_count=0,
            node="node-1",
            image_refs=("nginx:1.21",),
            reason=None,
            message=None,
            is_failing=False,
        ),
    ]

    events = [
        EventSummary(
            namespace="default",
            name="normal-event",
            type="Normal",
            reason="Scheduled",
            message="Successfully scheduled pod",
            involved_object_kind="Pod",
            involved_object_name="healthy-pod",
            count=1,
            last_timestamp="2024-01-15T12:00:00Z",
        ),
    ]

    deployments = [
        DeploymentSummary(
            name="web",
            namespace="default",
            replicas=2,
            available_replicas=2,
            ready_replicas=2,
            updated_replicas=2,
            available=True,
        ),
    ]

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=[],
        collection_errors=(),
        candidates=(),
    )


__all__ = ["make_test_bundle", "make_test_bundle_with_unknown_kind", "make_test_bundle_no_candidates"]
