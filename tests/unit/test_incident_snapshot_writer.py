"""Tests for incident bundle disk writing.

These tests verify that bundles are written with deterministic layout.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_snapshot import (
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    _detect_symptoms,
    _parse_deployment_summary,
    _parse_event_summary,
    _parse_pod_summary,
    write_incident_bundle,
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


class TestBundleWriting(unittest.TestCase):
    """Test incident bundle disk writing."""

    def test_bundle_writes_all_required_files(self) -> None:
        """write_incident_bundle should create all required files."""
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
        deployments = [
            _parse_deployment_summary(FAKE_DEPLOYMENTS_RESPONSE["items"][0])
        ]
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
            write_incident_bundle(bundle, output_dir)

            # Verify directory structure by checking files exist
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
        """IncidentEvidenceBundle.to_dict() should produce valid JSON output."""
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
        self.assertEqual(
            parsed["pods"][0]["name"], "nginx-deployment-7fb96c846b-xk2p9"
        )
