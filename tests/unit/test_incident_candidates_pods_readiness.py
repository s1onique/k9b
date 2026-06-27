"""Tests for readiness_failure incident candidate detection.

Regression test for: Phase 2 incident discovery fails with
incident_candidate_not_promoted. A pod can be Running while still
unhealthy from the application's point of view due to readiness probe
failure. This test ensures readiness_failure candidates are properly
detected and promoted.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    ObjectKind,
    Severity,
    detect_incident_candidates,
)
from k8s_diag_agent.collect.incident_models import (
    PodHealthStatus,
    PodSummary,
)


def make_pod(
    name: str,
    namespace: str = "default",
    health_status: PodHealthStatus = PodHealthStatus.RUNNING,
    reason: str | None = None,
    message: str | None = None,
    phase: str | None = None,
) -> PodSummary:
    """Helper to create test pod summaries."""
    return PodSummary(
        name=name,
        namespace=namespace,
        phase=phase or health_status.value,
        health_status=health_status,
        restart_count=0,
        node="node-1",
        image_refs=("image:v1",),
        reason=reason,
        message=message,
        is_failing=health_status != PodHealthStatus.RUNNING,
    )


class TestReadinessFailureDetection(unittest.TestCase):
    """Test readiness_failure candidate detection."""

    def test_detects_readiness_failure_pod(self) -> None:
        """A pod with readiness_failure health status should produce a readiness_failure candidate."""
        pod = make_pod(
            name="readiness-failing-pod",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="NotReady",
            message="Pod is Running but not Ready",
            phase="Running",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.READINESS_FAILURE)
        self.assertEqual(candidate.object_kind, ObjectKind.POD)
        self.assertEqual(candidate.object_name, "readiness-failing-pod")
        self.assertEqual(candidate.namespace, "default")
        self.assertEqual(candidate.severity, Severity.WARNING)
        self.assertEqual(len(candidate.signals), 1)
        self.assertEqual(candidate.signals[0].source, "pod")
        self.assertEqual(candidate.signals[0].reason, "NotReady")

    def test_readiness_failure_candidate_id_is_deterministic(self) -> None:
        """Same pod should produce same candidate_id across calls."""
        pod = make_pod(
            name="cnpg-lab-failing-app",
            namespace="live-lab",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="NotReady",
            phase="Running",
        )

        result1 = detect_incident_candidates([pod], [], [])
        result2 = detect_incident_candidates([pod], [], [])

        self.assertEqual(result1[0].candidate_id, result2[0].candidate_id)
        self.assertEqual(result1[0].candidate_id, "live-lab-pod-cnpg-lab-failing-app-readiness_failure")

    def test_readiness_failure_evidence_needed(self) -> None:
        """Readiness failure candidates should include appropriate evidence types."""
        pod = make_pod(
            name="unready-pod",
            namespace="default",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="ReadinessFailure",
            phase="Running",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertIn("pod_describe", candidate.evidence_needed)
        self.assertIn("readiness_probe_status", candidate.evidence_needed)

    def test_readiness_failure_different_from_crash_loop(self) -> None:
        """Readiness failure is distinct from crash_loop."""
        readiness_pod = make_pod(
            name="unready-pod",
            namespace="default",
            health_status=PodHealthStatus.READINESS_FAILURE,
            phase="Running",
        )
        crash_pod = make_pod(
            name="crash-pod",
            namespace="default",
            health_status=PodHealthStatus.CRASH_LOOP,
            reason="CrashLoopBackOff",
            phase="Running",
        )

        readiness_candidates = detect_incident_candidates([readiness_pod], [], [])
        crash_candidates = detect_incident_candidates([crash_pod], [], [])

        self.assertEqual(readiness_candidates[0].candidate_class, CandidateClass.READINESS_FAILURE)
        self.assertEqual(crash_candidates[0].candidate_class, CandidateClass.CRASH_LOOP)
        self.assertNotEqual(
            readiness_candidates[0].candidate_id,
            crash_candidates[0].candidate_id,
        )


class TestReadinessFailurePromotionIntegration(unittest.TestCase):
    """Integration tests for readiness_failure candidate to incident promotion.

    These tests verify that readiness_failure candidates can flow through
    the entire promotion pipeline without requiring LLM enrichment.
    """

    def test_readiness_failure_passes_through_candidate_detection(self) -> None:
        """Readiness failure pod should produce exactly one candidate."""
        pod = make_pod(
            name="test-pod",
            namespace="test-ns",
            health_status=PodHealthStatus.READINESS_FAILURE,
            reason="NotReady",
            phase="Running",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        # Should produce exactly one candidate
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_class, CandidateClass.READINESS_FAILURE)

    def test_mixed_failure_types_produce_all_candidates(self) -> None:
        """Mixed pod failures should each produce their respective candidates."""
        readiness_pod = make_pod(
            name="unready-pod",
            namespace="default",
            health_status=PodHealthStatus.READINESS_FAILURE,
            phase="Running",
        )
        crash_pod = make_pod(
            name="crash-pod",
            namespace="default",
            health_status=PodHealthStatus.CRASH_LOOP,
            reason="CrashLoopBackOff",
            phase="Running",
        )
        image_pod = make_pod(
            name="image-pod",
            namespace="default",
            health_status=PodHealthStatus.IMAGE_PULL_ERROR,
            reason="ImagePullBackOff",
            phase="Pending",
        )

        candidates = detect_incident_candidates(
            pods=[readiness_pod, crash_pod, image_pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 3)
        candidate_classes = {c.candidate_class for c in candidates}
        self.assertIn(CandidateClass.READINESS_FAILURE, candidate_classes)
        self.assertIn(CandidateClass.CRASH_LOOP, candidate_classes)
        self.assertIn(CandidateClass.IMAGE_PULL_ERROR, candidate_classes)


if __name__ == "__main__":
    unittest.main()
