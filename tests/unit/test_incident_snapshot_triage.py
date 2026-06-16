"""Tests for incident snapshot symptom detection.

These tests verify deterministic symptom detection from Kubernetes evidence.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_snapshot import (
    _detect_symptoms,
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


class TestSymptomDetection(unittest.TestCase):
    """Test deterministic symptom detection."""

    def test_crashloop_detected(self) -> None:
        """CrashLoopBackOff pods should generate crash_loop symptoms."""
        pod = _parse_pod_summary(FAKE_PODS_RESPONSE["items"][1])
        symptoms = _detect_symptoms([pod], [])

        self.assertEqual(len(symptoms), 1)
        self.assertEqual(symptoms[0].symptom_type, "crash_loop")
        self.assertEqual(symptoms[0].severity, "error")
        self.assertEqual(symptoms[0].pod_name, "crashloop-pod")

    def test_image_pull_error_detected(self) -> None:
        """ImagePullBackOff pods should generate image_pull_error symptoms."""
        pod = _parse_pod_summary(FAKE_PODS_RESPONSE["items"][2])
        symptoms = _detect_symptoms([pod], [])

        self.assertEqual(len(symptoms), 1)
        self.assertEqual(symptoms[0].symptom_type, "image_pull_error")
        self.assertEqual(symptoms[0].severity, "error")

    def test_pending_pod_detected(self) -> None:
        """Pending pods should generate pending_pod symptoms."""
        pod = _parse_pod_summary(FAKE_PODS_RESPONSE["items"][3])
        symptoms = _detect_symptoms([pod], [])

        self.assertEqual(len(symptoms), 1)
        self.assertEqual(symptoms[0].symptom_type, "pending_pod")
        self.assertEqual(symptoms[0].severity, "warning")

    def test_warning_events_detected(self) -> None:
        """Warning events should generate warning_event symptoms."""
        event = _parse_event_summary(FAKE_EVENTS_RESPONSE["items"][0])
        symptoms = _detect_symptoms([], [event])

        self.assertEqual(len(symptoms), 1)
        self.assertEqual(symptoms[0].symptom_type, "warning_event")
        self.assertEqual(symptoms[0].severity, "warning")

    def test_healthy_pod_no_symptoms(self) -> None:
        """Healthy pods should not generate symptoms."""
        pod = _parse_pod_summary(FAKE_PODS_RESPONSE["items"][4])
        symptoms = _detect_symptoms([pod], [])

        self.assertEqual(len(symptoms), 0)

    def test_multiple_symptoms_from_multiple_pods(self) -> None:
        """Multiple failing pods should generate multiple symptoms."""
        pods = [
            _parse_pod_summary(FAKE_PODS_RESPONSE["items"][1]),
            _parse_pod_summary(FAKE_PODS_RESPONSE["items"][2]),
            _parse_pod_summary(FAKE_PODS_RESPONSE["items"][3]),
        ]
        symptoms = _detect_symptoms(pods, [])

        self.assertEqual(len(symptoms), 3)
        symptom_types = {s.symptom_type for s in symptoms}
        self.assertEqual(symptom_types, {"crash_loop", "image_pull_error", "pending_pod"})
