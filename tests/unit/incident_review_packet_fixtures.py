"""Test fixtures for incident review packet tests.

This module contains shared test bundle fixtures used by multiple test files.
"""

from __future__ import annotations

from datetime import datetime

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

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=(),
    )


__all__ = ["make_test_bundle"]
