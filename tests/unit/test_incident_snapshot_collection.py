"""Tests for incident bundle collection with mocked kubectl.

These tests verify that all evidence types are collected and bundled correctly
without requiring a real Kubernetes cluster.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from k8s_diag_agent.collect.incident_snapshot import collect_incident_snapshot

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


class TestIncidentBundleCollection(unittest.TestCase):
    """Test incident bundle collection with mocked kubectl."""

    @patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_full_bundle_collection(
        self, mock_kubectl: unittest.mock.MagicMock
    ) -> None:
        """Test that all evidence types are collected and bundled correctly."""
        # Configure mock to return different responses based on command
        def kubectl_side_effect(*args: str) -> str:
            if "pods" in args and "-o" in args:
                return json.dumps(FAKE_PODS_RESPONSE)
            if "deployments" in args and "-o" in args:
                return json.dumps(FAKE_DEPLOYMENTS_RESPONSE)
            if "events" in args and "-o" in args:
                return json.dumps(FAKE_EVENTS_RESPONSE)
            return "{}"

        mock_kubectl.side_effect = kubectl_side_effect

        bundle = collect_incident_snapshot(namespace="default")

        # Verify bundle metadata
        self.assertEqual(bundle.metadata.namespace, "default")
        self.assertEqual(bundle.metadata.total_pods, 5)
        self.assertEqual(bundle.metadata.total_deployments, 2)
        self.assertEqual(bundle.metadata.total_events, 3)
        self.assertEqual(bundle.metadata.failing_pods_count, 3)
        self.assertGreater(bundle.metadata.symptoms_count, 0)

    @patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_collection_errors_handled_gracefully(
        self, mock_kubectl: unittest.mock.MagicMock
    ) -> None:
        """Test that kubectl failures are recorded as errors, not exceptions."""
        mock_kubectl.side_effect = RuntimeError("kubectl not found")

        bundle = collect_incident_snapshot(namespace="default")

        self.assertIn("pods_collection", bundle.collection_errors[0])
        self.assertEqual(bundle.metadata.total_pods, 0)
