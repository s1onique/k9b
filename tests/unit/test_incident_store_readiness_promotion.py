"""Regression test for readiness_failure candidate promotion through IncidentStore.

This test proves that readiness_failure candidates flow through the entire
promotion pipeline (detect → promote → store → API) without requiring
LLM enrichment. This is the regression for the Phase 2 incident discovery
failure where readiness_failure candidates were detected but never promoted.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    detect_incident_candidates,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_models import PodHealthStatus, PodSummary
from k8s_diag_agent.collect.incident_store import IncidentStore


def make_pod(
    name: str,
    namespace: str = "default",
    health_status: PodHealthStatus = PodHealthStatus.RUNNING,
    reason: str | None = None,
    message: str | None = None,
    phase: str | None = None,
) -> PodSummary:
    """Helper to create test pod summaries."""
    # For readiness_failure, phase should be "Running" to match Kubernetes semantics
    # (pod is Running but not Ready due to readiness probe failure)
    computed_phase = phase if phase is not None else (
        "Running" if health_status == PodHealthStatus.READINESS_FAILURE else health_status.value
    )
    return PodSummary(
        name=name,
        namespace=namespace,
        phase=computed_phase,
        health_status=health_status,
        restart_count=0,
        node="node-1",
        image_refs=("image:v1",),
        reason=reason,
        message=message,
        is_failing=health_status != PodHealthStatus.RUNNING,
    )


class TestReadinessFailureStorePromotion(unittest.TestCase):
    """Test that readiness_failure candidates are promoted to incidents via IncidentStore."""

    def test_readiness_failure_candidate_promotes_to_incident(self) -> None:
        """A readiness_failure candidate should be promoted to an incident."""
        # Create a readiness failure pod
        pod = make_pod(
            name="cnpg-lab-failing-app",
            namespace="live-lab",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="NotReady",
            message="Pod is Running but not Ready",
        )

        # Detect candidates
        candidates = detect_incident_candidates(pods=[pod], deployments=[], events=[])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_class, CandidateClass.READINESS_FAILURE)

        # Promote through IncidentStore
        store = IncidentStore()
        observed_at = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
        incidents = store.promote_candidates(candidates, observed_at)

        # Should produce one incident
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].candidate_class, "readiness_failure")
        self.assertEqual(incidents[0].status, IncidentStatus.OPEN)
        self.assertEqual(incidents[0].object_name, "cnpg-lab-failing-app")
        self.assertEqual(incidents[0].namespace, "live-lab")

    def test_readiness_failure_incident_is_listable_via_api_contract(self) -> None:
        """An incident from readiness_failure should be retrievable via list_incidents."""
        pod = make_pod(
            name="unready-pod",
            namespace="test-ns",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="ReadinessFailure",
        )

        candidates = detect_incident_candidates(pods=[pod], deployments=[], events=[])

        store = IncidentStore()
        observed_at = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
        store.promote_candidates(candidates, observed_at)

        # List all incidents
        all_incidents = store.list_incidents()
        self.assertEqual(len(all_incidents), 1)
        self.assertEqual(all_incidents[0].candidate_class, "readiness_failure")

        # Filter by status
        open_incidents = store.list_incidents(status=IncidentStatus.OPEN)
        self.assertEqual(len(open_incidents), 1)
        self.assertEqual(open_incidents[0].candidate_class, "readiness_failure")

        # Filter by different status (should be empty)
        resolved_incidents = store.list_incidents(status=IncidentStatus.RESOLVED)
        self.assertEqual(len(resolved_incidents), 0)

    def test_readiness_failure_incident_has_correct_incident_id(self) -> None:
        """The incident ID should be deterministic based on candidate key."""
        pod = make_pod(
            name="same-pod",
            namespace="same-ns",
            health_status=PodHealthStatus.READINESS_FAILURE,
        )

        candidates = detect_incident_candidates(pods=[pod], deployments=[], events=[])

        # Promote twice
        store1 = IncidentStore()
        store2 = IncidentStore()
        observed_at = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)

        incidents1 = store1.promote_candidates(candidates, observed_at)
        incidents2 = store2.promote_candidates(candidates, observed_at)

        # Same candidate should produce same incident_id
        self.assertEqual(incidents1[0].incident_id, incidents2[0].incident_id)
        self.assertEqual(
            incidents1[0].incident_id,
            "same-ns-pod-same-pod-readiness_failure"
        )

    def test_mixed_candidates_all_promoted(self) -> None:
        """Mixed candidate types should all be promoted."""
        readiness_pod = make_pod(
            name="unready-pod",
            namespace="default",
            health_status=PodHealthStatus.READINESS_FAILURE,
        )
        crash_pod = make_pod(
            name="crash-pod",
            namespace="default",
            health_status=PodHealthStatus.CRASH_LOOP,
            reason="CrashLoopBackOff",
        )

        candidates = detect_incident_candidates(
            pods=[readiness_pod, crash_pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 2)

        store = IncidentStore()
        observed_at = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
        incidents = store.promote_candidates(candidates, observed_at)

        # Both should be promoted
        self.assertEqual(len(incidents), 2)
        candidate_classes = {inc.candidate_class for inc in incidents}
        self.assertIn("readiness_failure", candidate_classes)
        self.assertIn("crash_loop", candidate_classes)

    def test_readiness_failure_without_bundle_id_creates_open_incident(self) -> None:
        """Without bundle_id, readiness_failure should create OPEN incident (not COLLECTING_EVIDENCE)."""
        pod = make_pod(
            name="test-pod",
            namespace="test-ns",
            health_status=PodHealthStatus.READINESS_FAILURE,
        )

        candidates = detect_incident_candidates(pods=[pod], deployments=[], events=[])

        store = IncidentStore()
        observed_at = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
        incidents = store.promote_candidates(candidates, observed_at)

        # Without bundle_id, status should be OPEN
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.OPEN)


if __name__ == "__main__":
    unittest.main()
