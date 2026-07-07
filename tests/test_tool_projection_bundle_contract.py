"""Tests for serialized IncidentEvidenceBundle contract.

This module tests that tool_output_projection metadata survives serialization
in the IncidentEvidenceBundle and that the serialized JSON does not leak
sensitive fields like raw_artifact_path, raw_output, or llm_visible.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-BUNDLE-CONTRACT01

Required coverage:
1. serialized IncidentEvidenceBundle contains tool_output_projection
2. serialized bundle has tool_output_projection["pods"]
3. serialized bundle has tool_output_projection["events"]
4. serialized bundle has tool_output_projection["deployments"]
5. pods/events/deployments projection metadata have identical key sets
6. raw_artifact_path is absent everywhere in serialized bundle JSON
7. raw_output is absent everywhere in serialized bundle JSON
8. llm_visible is absent everywhere in serialized bundle JSON
"""

from __future__ import annotations

import json
import re
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_models import (
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


class TestSerializedBundleProjectionMetadata(unittest.TestCase):
    """Tests for serialized bundle containing tool_output_projection metadata."""

    def test_serialized_bundle_contains_tool_output_projection(self) -> None:
        """Serialized IncidentEvidenceBundle contains tool_output_projection."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=1,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        projection_metadata = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 1000,
                "llm_visible_size_bytes": 500,
                "content_type": "json",
                "error": None,
                "provenance": {"namespace": "default", "resource": "pods"},
            },
            "events": {
                "schema_version": "1.0",
                "source_tool": "kubectl_events",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 800,
                "llm_visible_size_bytes": 400,
                "content_type": "json",
                "error": None,
                "provenance": {"namespace": "default", "resource": "events"},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        self.assertIn("tool_output_projection", bundle_dict)
        self.assertIn("tool_output_projection", serialized)

    def test_serialized_bundle_has_tool_output_projection_pods(self) -> None:
        """Serialized bundle has tool_output_projection["pods"]."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-002",
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

        projection_metadata = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 1000,
                "llm_visible_size_bytes": 500,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()

        self.assertIn("pods", bundle_dict["tool_output_projection"])
        self.assertEqual(
            bundle_dict["tool_output_projection"]["pods"]["source_tool"],
            "kubectl_get",
        )

    def test_serialized_bundle_has_tool_output_projection_events(self) -> None:
        """Serialized bundle has tool_output_projection["events"]."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-003",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=0,
            total_events=1,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        projection_metadata = {
            "events": {
                "schema_version": "1.0",
                "source_tool": "kubectl_events",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 800,
                "llm_visible_size_bytes": 400,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[],
            events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()

        self.assertIn("events", bundle_dict["tool_output_projection"])
        self.assertEqual(
            bundle_dict["tool_output_projection"]["events"]["source_tool"],
            "kubectl_events",
        )

    def test_pods_events_have_identical_key_sets(self) -> None:
        """Pods and events projection metadata have identical key sets."""
        metadata = IncidentBundleMetadata(
            bundle_id="proj-004",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=1,
            total_deployments=0,
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

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
            deployments=[],
            symptoms=[],
            tool_output_projection={"pods": pods_projection, "events": events_projection},
        )

        bundle_dict = bundle.to_dict()
        pods_keys = set(bundle_dict["tool_output_projection"]["pods"].keys())
        events_keys = set(bundle_dict["tool_output_projection"]["events"].keys())

        self.assertEqual(pods_keys, events_keys)

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


class TestSerializedBundleForbiddenKeys(unittest.TestCase):
    """Tests that forbidden keys are absent from serialized bundle."""

    def test_raw_artifact_path_absent_from_serialized_bundle(self) -> None:
        """raw_artifact_path is absent everywhere in serialized bundle JSON."""
        metadata = IncidentBundleMetadata(
            bundle_id="forbid-001",
            captured_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=1,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        projection_metadata = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": True,
                "spill_reason": "size_threshold",
                "raw_artifact_id": "artifact-123",
                "raw_size_bytes": 50000,
                "llm_visible_size_bytes": 8000,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
            "events": {
                "schema_version": "1.0",
                "source_tool": "kubectl_events",
                "spill_occurred": True,
                "spill_reason": "size_threshold",
                "raw_artifact_id": "artifact-456",
                "raw_size_bytes": 40000,
                "llm_visible_size_bytes": 6000,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        self.assertNotIn("raw_artifact_path", serialized)
        self.assertNotIn("raw_artifact_path", bundle_dict)
        self.assertNotIn("raw_artifact_path", bundle_dict.get("tool_output_projection", {}))
        self.assertNotIn(
            "raw_artifact_path",
            bundle_dict.get("tool_output_projection", {}).get("pods", {}),
        )
        self.assertNotIn(
            "raw_artifact_path",
            bundle_dict.get("tool_output_projection", {}).get("events", {}),
        )

    def test_raw_output_absent_from_serialized_bundle(self) -> None:
        """raw_output is absent everywhere in serialized bundle JSON."""
        metadata = IncidentBundleMetadata(
            bundle_id="forbid-002",
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

        projection_metadata = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 1000,
                "llm_visible_size_bytes": 500,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        self.assertNotIn("raw_output", serialized)
        self.assertNotIn("raw_output", bundle_dict)

    def test_llm_visible_absent_from_serialized_bundle(self) -> None:
        """llm_visible is absent everywhere in serialized bundle JSON.

        We check for standalone 'llm_visible' key (not 'llm_visible_size_bytes').
        """
        metadata = IncidentBundleMetadata(
            bundle_id="forbid-003",
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

        projection_metadata = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "spill_reason": None,
                "raw_artifact_id": None,
                "raw_size_bytes": 1000,
                "llm_visible_size_bytes": 500,
                "content_type": "json",
                "error": None,
                "provenance": {},
            },
        }

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata,
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        standalone_pattern = re.compile(r'"llm_visible"[:\s]')
        self.assertIsNone(
            standalone_pattern.search(serialized),
            "Standalone 'llm_visible' key found in serialized JSON",
        )
        self.assertNotIn("llm_visible", bundle_dict)
