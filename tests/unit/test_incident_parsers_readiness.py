"""Tests for readiness_failure parsing in incident_parsers.

Regression test for: Phase 2 incident discovery fails with
incident_candidate_not_promoted. The parser must set READINESS_FAILURE
health status when a pod is Running but has Ready condition = False.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_models import PodHealthStatus
from k8s_diag_agent.collect.incident_parsers import parse_pod_summary


class TestParsePodSummaryReadiness(unittest.TestCase):
    """Test parse_pod_summary for readiness failure detection."""

    def test_running_pod_with_ready_false_is_readiness_failure(self) -> None:
        """A Running pod with Ready condition False should be parsed as READINESS_FAILURE."""
        pod = {
            "metadata": {
                "name": "test-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "False",
                        "reason": "ReadinessProbeFailed",
                        "message": " Readiness probe failed",
                    }
                ],
                "containerStatuses": [
                    {
                        "ready": False,
                        "restartCount": 0,
                        "state": {"running": {}},
                    }
                ],
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "nginx:v1"}],
            },
        }

        summary = parse_pod_summary(pod)

        self.assertEqual(summary.health_status, PodHealthStatus.READINESS_FAILURE)
        self.assertEqual(summary.phase, "running")
        self.assertEqual(summary.name, "test-pod")
        self.assertEqual(summary.namespace, "default")
        self.assertTrue(summary.is_failing)
        self.assertEqual(summary.reason, "NotReady")

    def test_running_pod_with_multiple_unready_containers(self) -> None:
        """Multiple unready containers should produce READINESS_FAILURE."""
        pod = {
            "metadata": {
                "name": "multi-container-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "False",
                        "reason": "ContainersNotReady",
                        "message": "containers with unready status",
                    }
                ],
                "containerStatuses": [
                    {"ready": False, "restartCount": 0, "state": {"running": {}}},
                    {"ready": False, "restartCount": 0, "state": {"running": {}}},
                ],
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "app:v1"}, {"image": "sidecar:v1"}],
            },
        }

        summary = parse_pod_summary(pod)

        self.assertEqual(summary.health_status, PodHealthStatus.READINESS_FAILURE)
        self.assertTrue(summary.is_failing)

    def test_running_pod_with_ready_true_is_healthy(self) -> None:
        """A Running pod with Ready condition True should be parsed as RUNNING (healthy)."""
        pod = {
            "metadata": {
                "name": "healthy-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "True",
                    }
                ],
                "containerStatuses": [
                    {"ready": True, "restartCount": 0, "state": {"running": {}}},
                ],
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "nginx:v1"}],
            },
        }

        summary = parse_pod_summary(pod)

        self.assertEqual(summary.health_status, PodHealthStatus.RUNNING)
        self.assertEqual(summary.phase, "running")
        self.assertFalse(summary.is_failing)

    def test_crashloop_takes_precedence_over_readiness(self) -> None:
        """CrashLoopBackOff should take precedence over readiness failure."""
        pod = {
            "metadata": {
                "name": "crashloop-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "False",
                    }
                ],
                "containerStatuses": [
                    {
                        "ready": False,
                        "restartCount": 5,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "Back-off 5m40s restarting",
                            }
                        },
                    }
                ],
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "app:v1"}],
            },
        }

        summary = parse_pod_summary(pod)

        # CrashLoop should take precedence
        self.assertEqual(summary.health_status, PodHealthStatus.CRASH_LOOP)
        self.assertTrue(summary.is_failing)

    def test_pending_pod_is_pending_not_readiness_failure(self) -> None:
        """A Pending pod should be parsed as PENDING, not READINESS_FAILURE."""
        pod = {
            "metadata": {
                "name": "pending-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Pending",
                "conditions": [],
                "containerStatuses": [],
            },
            "spec": {
                "nodeName": "",
                "containers": [{"image": "app:v1"}],
            },
        }

        summary = parse_pod_summary(pod)

        self.assertEqual(summary.health_status, PodHealthStatus.PENDING)
        self.assertEqual(summary.phase, "pending")
        self.assertTrue(summary.is_failing)


if __name__ == "__main__":
    unittest.main()
