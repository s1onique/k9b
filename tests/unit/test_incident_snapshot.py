"""Tests for incident snapshot collection.

These tests use mock kubectl responses to verify deterministic behavior
without requiring a real Kubernetes cluster.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.collect.incident_snapshot import (
    IncidentEvidenceBundle,
    IncidentSymptom,
    PodHealthStatus,
    PodSummary,
    DeploymentSummary,
    EventSummary,
    collect_incident_snapshot,
    write_incident_bundle,
    _parse_pod_summary,
    _parse_deployment_summary,
    _parse_event_summary,
    _detect_symptoms,
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


class TestIncidentBundleCollection(unittest.TestCase):
    """Test incident bundle collection with mocked kubectl."""

    @patch("k8s_diag_agent.collect.incident_snapshot._kubectl")
    def test_full_bundle_collection(self, mock_kubectl: unittest.mock.MagicMock) -> None:
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

    @patch("k8s_diag_agent.collect.incident_snapshot._kubectl")
    def test_collection_errors_handled_gracefully(self, mock_kubectl: unittest.mock.MagicMock) -> None:
        """Test that kubectl failures are recorded as errors, not exceptions."""
        mock_kubectl.side_effect = RuntimeError("kubectl not found")

        bundle = collect_incident_snapshot(namespace="default")

        self.assertIn("pods_collection", bundle.collection_errors[0])
        self.assertEqual(bundle.metadata.total_pods, 0)


class TestBundleWriting(unittest.TestCase):
    """Test incident bundle disk writing."""

    def test_bundle_writes_all_required_files(self) -> None:
        """write_incident_bundle should create all required files."""
        # Create a minimal bundle for testing
        from k8s_diag_agent.collect.incident_snapshot import (
            IncidentBundleMetadata,
            IncidentEvidenceBundle,
        )
        from datetime import UTC, datetime

        metadata = IncidentBundleMetadata(
            bundle_id="test-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=2,
            total_events=1,
            total_deployments=1,
            failing_pods_count=1,
            symptoms_count=2,
        )

        pods = [
            _parse_pod_summary(FAKE_PODS_RESPONSE["items"][0]),
            _parse_pod_summary(FAKE_PODS_RESPONSE["items"][1]),
        ]
        deployments = [_parse_deployment_summary(FAKE_DEPLOYMENTS_RESPONSE["items"][0])]
        events = [_parse_event_summary(FAKE_EVENTS_RESPONSE["items"][0])]
        symptoms = _detect_symptoms(pods, events)

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=pods,
            events=events,
            deployments=deployments,
            symptoms=symptoms,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            written = write_incident_bundle(bundle, output_dir)

            # Verify all expected files are written
            self.assertIn("incident.json", written)
            self.assertIn("evidence-index.md", written)
            self.assertIn("objects/pods.json", written)
            self.assertIn("objects/deployments.json", written)
            self.assertIn("objects/events.json", written)
            self.assertIn("summary/symptoms.md", written)

            # Verify files are valid JSON/markdown
            incident_data = json.loads(written["incident.json"].read_text())
            self.assertEqual(incident_data["metadata"]["bundle_id"], "test-001")

            pods_data = json.loads(written["objects/pods.json"].read_text())
            self.assertEqual(len(pods_data), 2)

    def test_bundle_layout_is_deterministic(self) -> None:
        """Bundle file layout should be consistent."""
        from k8s_diag_agent.collect.incident_snapshot import (
            IncidentBundleMetadata,
            IncidentEvidenceBundle,
        )
        from datetime import UTC, datetime

        metadata = IncidentBundleMetadata(
            bundle_id="det-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="test",
            since_hours=1,
            context="test-context",
            total_pods=0,
            total_events=0,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[],
            events=[],
            deployments=[],
            symptoms=[],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            written = write_incident_bundle(bundle, output_dir)

            # Verify directory structure
            self.assertTrue((output_dir / "incident.json").exists())
            self.assertTrue((output_dir / "evidence-index.md").exists())
            self.assertTrue((output_dir / "objects").is_dir())
            self.assertTrue((output_dir / "objects" / "pods.json").exists())
            self.assertTrue((output_dir / "objects" / "deployments.json").exists())
            self.assertTrue((output_dir / "objects" / "events.json").exists())
            self.assertTrue((output_dir / "summary").is_dir())
            self.assertTrue((output_dir / "summary" / "symptoms.md").exists())


class TestBundleToDict(unittest.TestCase):
    """Test that bundles serialize correctly for incident.json."""

    def test_bundle_serializes_to_dict(self) -> None:
        """IncidentEvidenceBundle.to_dict() should produce valid JSON-serializable output."""
        from k8s_diag_agent.collect.incident_snapshot import (
            IncidentBundleMetadata,
            IncidentEvidenceBundle,
        )
        from datetime import UTC, datetime

        metadata = IncidentBundleMetadata(
            bundle_id="serial-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=0,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        pod = _parse_pod_summary(FAKE_PODS_RESPONSE["items"][0])
        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[pod],
            events=[],
            deployments=[],
            symptoms=[],
        )

        # Should not raise
        data = bundle.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        # Verify structure
        self.assertIn("metadata", parsed)
        self.assertIn("pods", parsed)
        self.assertEqual(len(parsed["pods"]), 1)
        self.assertEqual(parsed["pods"][0]["name"], "nginx-deployment-7fb96c846b-xk2p9")


if __name__ == "__main__":
    unittest.main()
