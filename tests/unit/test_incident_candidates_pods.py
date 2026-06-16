"""Tests for pod-based incident candidate detection.

Covers: crash_loop, image_pull_error, pending_pod, failed_pod
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
) -> PodSummary:
    """Helper to create test pod summaries."""
    return PodSummary(
        name=name,
        namespace=namespace,
        phase=health_status.value,
        health_status=health_status,
        restart_count=0,
        node="node-1",
        image_refs=("image:v1",),
        reason=reason,
        message=message,
        is_failing=health_status != PodHealthStatus.RUNNING,
    )


class TestCrashLoopDetection(unittest.TestCase):
    """Test crash_loop candidate detection."""

    def test_detects_crashloop_pod(self) -> None:
        """A pod in CrashLoopBackOff should produce a crash_loop candidate."""
        pod = make_pod(
            name="crashloop-pod",
            health_status=PodHealthStatus.CRASH_LOOP,
            reason="CrashLoopBackOff",
            message="Back-off 5m40s restarting",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.CRASH_LOOP)
        self.assertEqual(candidate.object_kind, ObjectKind.POD)
        self.assertEqual(candidate.object_name, "crashloop-pod")
        self.assertEqual(candidate.namespace, "default")
        self.assertEqual(candidate.severity, Severity.ERROR)
        self.assertEqual(len(candidate.signals), 1)
        self.assertEqual(candidate.signals[0].source, "pod")
        self.assertEqual(candidate.signals[0].reason, "CrashLoopBackOff")

    def test_crashloop_candidate_id_is_deterministic(self) -> None:
        """Same pod should produce same candidate_id across calls."""
        pod = make_pod(
            name="crashloop-pod",
            namespace="k9b",
            health_status=PodHealthStatus.CRASH_LOOP,
        )

        result1 = detect_incident_candidates([pod], [], [])
        result2 = detect_incident_candidates([pod], [], [])

        self.assertEqual(result1[0].candidate_id, result2[0].candidate_id)
        self.assertEqual(result1[0].candidate_id, "k9b-pod-crashloop-pod-crash_loop")


class TestImagePullErrorDetection(unittest.TestCase):
    """Test image_pull_error candidate detection."""

    def test_detects_imagepullbackoff_pod(self) -> None:
        """A pod with ImagePullBackOff should produce an image_pull_error candidate."""
        pod = make_pod(
            name="image-pull-pod",
            health_status=PodHealthStatus.IMAGE_PULL_ERROR,
            reason="ImagePullBackOff",
            message="rpc error: failed to pull image",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.IMAGE_PULL_ERROR)
        self.assertEqual(candidate.severity, Severity.ERROR)
        self.assertIn("image_pull_error", candidate.candidate_id)


class TestPendingPodDetection(unittest.TestCase):
    """Test pending_pod candidate detection."""

    def test_detects_pending_pod(self) -> None:
        """A pod stuck in Pending should produce a pending_pod candidate."""
        pod = make_pod(
            name="pending-pod",
            health_status=PodHealthStatus.PENDING,
            message="Pod stuck waiting for resources",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.PENDING_POD)
        self.assertEqual(candidate.severity, Severity.WARNING)


class TestFailedPodDetection(unittest.TestCase):
    """Test failed_pod candidate detection."""

    def test_detects_failed_pod(self) -> None:
        """A failed pod should produce a failed_pod candidate."""
        pod = make_pod(
            name="failed-pod",
            health_status=PodHealthStatus.FAILED,
            reason="Error",
            message="Container terminated with exit code 1",
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.FAILED_POD)
        self.assertEqual(candidate.severity, Severity.ERROR)


class TestHealthyPodsIgnored(unittest.TestCase):
    """Test that healthy pods do not produce candidates."""

    def test_healthy_pod_produces_no_candidate(self) -> None:
        """A healthy running pod should not produce a candidate."""
        pod = make_pod(
            name="healthy-pod",
            health_status=PodHealthStatus.RUNNING,
        )
        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[],
            events=[],
        )

        self.assertEqual(len(candidates), 0)

    def test_empty_namespace_skipped(self) -> None:
        """Pods with empty namespace should be skipped."""
        pod = make_pod(name="test-pod", namespace="", health_status=PodHealthStatus.CRASH_LOOP)
        candidates = detect_incident_candidates([pod], [], [])
        self.assertEqual(len(candidates), 0)


if __name__ == "__main__":
    unittest.main()
