"""Tests for deployment-based incident candidate detection.

Covers: deployment_unavailable
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
    DeploymentSummary,
)


def make_deployment(
    name: str,
    namespace: str = "default",
    replicas: int = 3,
    available_replicas: int = 3,
    ready_replicas: int = 3,
    updated_replicas: int = 3,
    available: bool = True,
) -> DeploymentSummary:
    """Helper to create test deployment summaries."""
    return DeploymentSummary(
        name=name,
        namespace=namespace,
        replicas=replicas,
        available_replicas=available_replicas,
        ready_replicas=ready_replicas,
        updated_replicas=updated_replicas,
        available=available,
    )


class TestDeploymentUnavailableDetection(unittest.TestCase):
    """Test deployment_unavailable candidate detection."""

    def test_detects_unavailable_deployment(self) -> None:
        """A deployment with fewer available replicas should produce a candidate."""
        deployment = make_deployment(
            name="broken-deployment",
            replicas=3,
            available_replicas=1,
            available=False,
        )
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.DEPLOYMENT_UNAVAILABLE)
        self.assertEqual(candidate.object_kind, ObjectKind.DEPLOYMENT)
        self.assertEqual(candidate.object_name, "broken-deployment")
        self.assertEqual(candidate.severity, Severity.WARNING)
        self.assertIn("replicas", candidate.signals[0].message)

    def test_healthy_deployment_produces_no_candidate(self) -> None:
        """A fully available deployment should not produce a candidate."""
        deployment = make_deployment(name="healthy-deployment", available=True)
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[],
        )

        self.assertEqual(len(candidates), 0)

    def test_zero_available_replicas(self) -> None:
        """Deployment with zero available replicas should produce a candidate."""
        deployment = make_deployment(
            name="dead-deployment",
            replicas=2,
            available_replicas=0,
            available=False,
        )
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_class, CandidateClass.DEPLOYMENT_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
