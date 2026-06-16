"""Tests for incident snapshot parsing functions.

These tests verify deterministic parsing of Kubernetes API responses
into incident evidence models without requiring a real cluster.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_snapshot import (
    PodHealthStatus,
    _parse_deployment_summary,
    _parse_event_summary,
    _parse_pod_summary,
)

# =============================================================================
# Fake Kubernetes Response Fixtures
# =============================================================================

FAKE_PODS_RESPONSE = {
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {
                "name": "nginx-deployment-7fb96c846b-xk2p9",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "restartCount": 0,
                        "state": {
                            "running": {"started": "2024-01-15T10:00:00Z"}
                        },
                    }
                ],
            },
            "spec": {
                "nodeName": "node-1",
                "containers": [{"image": "nginx:1.21"}],
            },
        },
        {
            "metadata": {
                "name": "crashloop-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "restartCount": 5,
                        "lastState": {
                            "terminated": {"exitCode": 1, "reason": "Error"}
                        },
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
                "containers": [{"image": "broken-app:v1"}],
            },
        },
        {
            "metadata": {
                "name": "image-pull-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Pending",
                "containerStatuses": [
                    {
                        "restartCount": 0,
                        "state": {
                            "waiting": {
                                "reason": "ImagePullBackOff",
                                "message": "rpc error: code = Unknown desc = failed to pull image",
                            }
                        },
                    }
                ],
            },
            "spec": {
                "containers": [{"image": "nonexistent:v99"}],
            },
        },
        {
            "metadata": {
                "name": "pending-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Pending",
                "containerStatuses": [],
            },
            "spec": {
                "containers": [{"image": "waiting:v1"}],
            },
        },
        {
            "metadata": {
                "name": "healthy-pod",
                "namespace": "default",
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {
                        "restartCount": 0,
                        "state": {"running": {"started": "2024-01-15T10:00:00Z"}},
                    }
                ],
            },
            "spec": {
                "nodeName": "node-2",
                "containers": [
                    {"image": "app:v1"},
                    {"image": "sidecar:v1"},
                ],
            },
        },
    ],
}

FAKE_DEPLOYMENTS_RESPONSE = {
    "apiVersion": "apps/v1",
    "items": [
        {
            "metadata": {"name": "nginx-deployment", "namespace": "default"},
            "spec": {"replicas": 3},
            "status": {
                "availableReplicas": 3,
                "readyReplicas": 3,
                "updatedReplicas": 3,
            },
        },
        {
            "metadata": {"name": "broken-deployment", "namespace": "default"},
            "spec": {"replicas": 2},
            "status": {
                "availableReplicas": 1,
                "readyReplicas": 1,
                "updatedReplicas": 1,
            },
        },
    ],
}

FAKE_EVENTS_RESPONSE = {
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {
                "name": "event-1",
                "namespace": "default",
                "lastTimestamp": "2024-01-15T12:00:00Z",
            },
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting container crashloop-pod",
            "involvedObject": {"kind": "Pod", "name": "crashloop-pod"},
            "count": 3,
        },
        {
            "metadata": {
                "name": "event-2",
                "namespace": "default",
                "lastTimestamp": "2024-01-15T11:30:00Z",
            },
            "type": "Warning",
            "reason": "Failed",
            "message": "Failed to pull image",
            "involvedObject": {"kind": "Pod", "name": "image-pull-pod"},
            "count": 1,
        },
        {
            "metadata": {
                "name": "event-3",
                "namespace": "default",
                "lastTimestamp": "2024-01-15T11:00:00Z",
            },
            "type": "Normal",
            "reason": "Scheduled",
            "message": "Successfully scheduled pod",
            "involvedObject": {"kind": "Pod", "name": "healthy-pod"},
            "count": 1,
        },
    ],
}


# =============================================================================
# Test Cases
# =============================================================================


class TestPodSummaryParsing(unittest.TestCase):
    """Test pod summary parsing from kubectl response."""

    def test_running_pod_parsed_correctly(self) -> None:
        """A healthy running pod should be marked as running and not failing."""
        pod = FAKE_PODS_RESPONSE["items"][0]
        summary = _parse_pod_summary(pod)

        self.assertEqual(summary.name, "nginx-deployment-7fb96c846b-xk2p9")
        self.assertEqual(summary.namespace, "default")
        self.assertEqual(summary.phase, "running")
        self.assertEqual(summary.health_status, PodHealthStatus.RUNNING)
        self.assertEqual(summary.restart_count, 0)
        self.assertEqual(summary.node, "node-1")
        self.assertEqual(summary.image_refs, ("nginx:1.21",))
        self.assertFalse(summary.is_failing)

    def test_crashloop_pod_parsed_correctly(self) -> None:
        """A crashlooping pod should be marked as failing."""
        pod = FAKE_PODS_RESPONSE["items"][1]
        summary = _parse_pod_summary(pod)

        self.assertEqual(summary.name, "crashloop-pod")
        self.assertEqual(summary.health_status, PodHealthStatus.CRASH_LOOP)
        self.assertEqual(summary.restart_count, 5)
        self.assertTrue(summary.is_failing)
        self.assertEqual(summary.reason, "CrashLoopBackOff")

    def test_image_pull_error_parsed_correctly(self) -> None:
        """A pod with image pull error should be marked as failing."""
        pod = FAKE_PODS_RESPONSE["items"][2]
        summary = _parse_pod_summary(pod)

        self.assertEqual(summary.name, "image-pull-pod")
        self.assertEqual(summary.health_status, PodHealthStatus.IMAGE_PULL_ERROR)
        self.assertTrue(summary.is_failing)
        self.assertEqual(summary.reason, "ImagePullBackOff")

    def test_pending_pod_parsed_correctly(self) -> None:
        """A pending pod should be marked as failing."""
        pod = FAKE_PODS_RESPONSE["items"][3]
        summary = _parse_pod_summary(pod)

        self.assertEqual(summary.name, "pending-pod")
        self.assertEqual(summary.health_status, PodHealthStatus.PENDING)
        self.assertTrue(summary.is_failing)

    def test_multiple_images_extracted(self) -> None:
        """Multiple container images should all be extracted."""
        pod = FAKE_PODS_RESPONSE["items"][4]
        summary = _parse_pod_summary(pod)

        self.assertEqual(summary.image_refs, ("app:v1", "sidecar:v1"))


class TestDeploymentSummaryParsing(unittest.TestCase):
    """Test deployment summary parsing."""

    def test_healthy_deployment_parsed_correctly(self) -> None:
        """A healthy deployment should show all replicas available."""
        deployment = FAKE_DEPLOYMENTS_RESPONSE["items"][0]
        summary = _parse_deployment_summary(deployment)

        self.assertEqual(summary.name, "nginx-deployment")
        self.assertEqual(summary.namespace, "default")
        self.assertEqual(summary.replicas, 3)
        self.assertEqual(summary.available_replicas, 3)
        self.assertTrue(summary.available)

    def test_unhealthy_deployment_parsed_correctly(self) -> None:
        """A deployment with fewer available replicas should not be marked available."""
        deployment = FAKE_DEPLOYMENTS_RESPONSE["items"][1]
        summary = _parse_deployment_summary(deployment)

        self.assertEqual(summary.name, "broken-deployment")
        self.assertEqual(summary.replicas, 2)
        self.assertEqual(summary.available_replicas, 1)
        self.assertFalse(summary.available)


class TestEventSummaryParsing(unittest.TestCase):
    """Test event summary parsing."""

    def test_warning_event_parsed_correctly(self) -> None:
        """Warning events should be parsed with all fields."""
        event = FAKE_EVENTS_RESPONSE["items"][0]
        summary = _parse_event_summary(event)

        self.assertEqual(summary.namespace, "default")
        self.assertEqual(summary.type, "Warning")
        self.assertEqual(summary.reason, "BackOff")
        self.assertEqual(summary.involved_object_kind, "Pod")
        self.assertEqual(summary.involved_object_name, "crashloop-pod")

    def test_normal_event_parsed_correctly(self) -> None:
        """Normal events should be parsed correctly."""
        event = FAKE_EVENTS_RESPONSE["items"][2]
        summary = _parse_event_summary(event)

        self.assertEqual(summary.type, "Normal")
        self.assertEqual(summary.reason, "Scheduled")
