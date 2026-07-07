"""Tests for serialized IncidentEvidenceBundle deployment projection contract.

This module tests that tool_output_projection metadata for deployments
survives serialization in the IncidentEvidenceBundle.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-DEPLOYMENTS01
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_models import (
    DeploymentSummary,
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
)
from k8s_diag_agent.collect.incident_snapshot import (
    _parse_event_summary,
    _parse_pod_summary,
)

FAKE_SMALL_PODS_RESPONSE = {
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {"name": "test-pod", "namespace": "default"},
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {"restartCount": 0, "state": {"running": {"startedAt": "2024-01-15T10:00:00Z"}}}
                ],
            },
            "spec": {"nodeName": "node-1", "containers": [{"image": "nginx:1.21"}]},
        },
    ],
}

FAKE_SMALL_EVENTS_RESPONSE = {
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {"name": "event-1", "namespace": "default", "lastTimestamp": "2024-01-15T12:00:00Z"},
            "type": "Warning",
            "reason": "BackOff",
            "message": "Back-off restarting container test-pod",
            "involvedObject": {"kind": "Pod", "name": "test-pod"},
            "count": 1,
        },
    ],
}


class TestSerializedBundleDeploymentProjectionMetadata(unittest.TestCase):
    """Tests for serialized bundle containing deployment projection metadata."""

    def test_serialized_bundle_has_tool_output_projection_deployments(self) -> None:
        """Serialized bundle has tool_output_projection["deployments"]."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-005",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=0,
            total_events=0,
            total_deployments=1,
            failing_pods_count=0,
            symptoms_count=0,
        )

        projection_metadata = {
            "deployments": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 1200,
                "llm_visible_size_bytes": 600,
                "content_type": "json",
                "error": None,
                "provenance": {"namespace": "default", "resource": "deployments"},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[],
            events=[],
            deployments=[
                DeploymentSummary(
                    name="test-deployment",
                    namespace="default",
                    replicas=3,
                    ready_replicas=3,
                    available_replicas=3,
                    updated_replicas=3,
                    available=True,
                )
            ],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()

        self.assertIn("deployments", bundle_dict["tool_output_projection"])
        self.assertEqual(
            bundle_dict["tool_output_projection"]["deployments"]["source_tool"],
            "kubectl_get",
        )
        self.assertEqual(
            bundle_dict["tool_output_projection"]["deployments"]["provenance"]["resource"],
            "deployments",
        )

    def test_all_collectors_have_identical_key_sets(self) -> None:
        """Pods, events, and deployments projection metadata have identical key sets."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-006",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=1,
            total_deployments=1,
            failing_pods_count=0,
            symptoms_count=0,
        )

        pods_projection = {
            "schema_version": "1.0",
            "source_tool": "kubectl_get",
            "spill_occurred": False,
            "spill_reason": None,
            "raw_artifact_id": None,
            "raw_size_bytes": 1000,
            "llm_visible_size_bytes": 500,
            "content_type": "json",
            "error": None,
            "provenance": {"resource": "pods"},
        }

        events_projection = {
            "schema_version": "1.0",
            "source_tool": "kubectl_events",
            "spill_occurred": False,
            "spill_reason": None,
            "raw_artifact_id": None,
            "raw_size_bytes": 800,
            "llm_visible_size_bytes": 400,
            "content_type": "json",
            "error": None,
            "provenance": {"resource": "events"},
        }

        deployments_projection = {
            "schema_version": "1.0",
            "source_tool": "kubectl_get",
            "spill_occurred": False,
            "spill_reason": None,
            "raw_artifact_id": None,
            "raw_size_bytes": 1200,
            "llm_visible_size_bytes": 600,
            "content_type": "json",
            "error": None,
            "provenance": {"resource": "deployments"},
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
            deployments=[
                DeploymentSummary(
                    name="test-deployment",
                    namespace="default",
                    replicas=3,
                    ready_replicas=3,
                    available_replicas=3,
                    updated_replicas=3,
                    available=True,
                )
            ],
            symptoms=[],
            tool_output_projection={
                "pods": pods_projection,
                "events": events_projection,
                "deployments": deployments_projection,
            },
        )

        bundle_dict = bundle.to_dict()
        pods_keys = set(bundle_dict["tool_output_projection"]["pods"].keys())
        events_keys = set(bundle_dict["tool_output_projection"]["events"].keys())
        deployments_keys = set(bundle_dict["tool_output_projection"]["deployments"].keys())

        self.assertEqual(pods_keys, events_keys)
        self.assertEqual(events_keys, deployments_keys)

        expected_keys = {
            "schema_version",
            "source_tool",
            "spill_occurred",
            "spill_reason",
            "raw_artifact_id",
            "raw_size_bytes",
            "llm_visible_size_bytes",
            "content_type",
            "error",
            "provenance",
        }
        self.assertEqual(pods_keys, expected_keys)

    def test_deployments_raw_artifact_path_absent_from_serialized_bundle(self) -> None:
        """raw_artifact_path is absent from deployments in serialized bundle JSON."""
        metadata = IncidentBundleMetadata(
            bundle_id="forbid-004",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=0,
            total_events=0,
            total_deployments=1,
            failing_pods_count=0,
            symptoms_count=0,
        )

        projection_metadata = {
            "deployments": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": True,
                "spill_reason": "size_threshold",
                "raw_artifact_id": "artifact-789",
                "raw_size_bytes": 60000,
                "llm_visible_size_bytes": 9000,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[],
            events=[],
            deployments=[
                DeploymentSummary(
                    name="test-deployment",
                    namespace="default",
                    replicas=3,
                    ready_replicas=3,
                    available_replicas=3,
                    updated_replicas=3,
                    available=True,
                )
            ],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        self.assertNotIn("raw_artifact_path", serialized)
        self.assertNotIn(
            "raw_artifact_path",
            bundle_dict.get("tool_output_projection", {}).get("deployments", {}),
        )
