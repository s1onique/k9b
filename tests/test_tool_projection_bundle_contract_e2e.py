"""End-to-end tests for serialized IncidentEvidenceBundle contract.

This module tests the full integration of tool_output_projection metadata
through the collectors and into written incident.json files.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-BUNDLE-CONTRACT01
"""

from __future__ import annotations

import json
import tempfile
import unittest.mock
from pathlib import Path

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

FAKE_LARGE_PODS_RESPONSE = {
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {"name": f"pod-{i}", "namespace": "default", "uid": f"uid-{i}" * 10},
            "status": {
                "phase": "Running",
                "containerStatuses": [
                    {"restartCount": i, "state": {"running": {"startedAt": "2024-01-15T10:00:00Z"}}}
                ],
            },
            "spec": {"nodeName": "node-1", "containers": [{"image": f"image-{i}:v1"}]},
        }
        for i in range(200)
    ],
}


class TestSpillMetadataSurvivesSerialization:
    """Tests that spill metadata survives serialization."""

    def test_spilled_output_keeps_raw_artifact_id(self) -> None:
        """Spilled output keeps raw_artifact_id after serialization."""
        metadata = IncidentBundleMetadata(
            bundle_id="spill-001",
            captured_at=__import__("datetime").datetime(2024, 1, 15, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=200,
            total_events=0,
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
                "raw_artifact_id": "artifact-abc-123",
                "raw_size_bytes": 50000,
                "llm_visible_size_bytes": 8000,
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
        restored = json.loads(serialized)

        assert restored["tool_output_projection"]["pods"]["raw_artifact_id"] == "artifact-abc-123"
        assert "artifact-abc-123" in serialized

    def test_no_artifact_dir_spill_error_preserved(self) -> None:
        """No-artifact-dir spill error keeps bounded error string."""
        metadata = IncidentBundleMetadata(
            bundle_id="spill-002",
            captured_at=__import__("datetime").datetime(2024, 1, 15, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=200,
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
                "raw_size_bytes": 50000,
                "llm_visible_size_bytes": 4096,
                "content_type": "json",
                "error": "spill_required_but_no_artifact_dir",
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
        restored = json.loads(serialized)

        assert restored["tool_output_projection"]["pods"]["error"] == "spill_required_but_no_artifact_dir"
        assert "spill_required_but_no_artifact_dir" in serialized

    def test_projection_metadata_is_json_serializable(self) -> None:
        """Projection metadata is JSON serializable without custom encoders."""
        metadata = IncidentBundleMetadata(
            bundle_id="serial-001",
            captured_at=__import__("datetime").datetime(2024, 1, 15, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
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
        restored = json.loads(serialized)

        assert restored["tool_output_projection"]["pods"]["raw_artifact_id"] == "artifact-123"
        assert restored["tool_output_projection"]["pods"]["spill_occurred"] is True

    def test_bundle_to_dict_with_empty_projection(self) -> None:
        """Bundle with empty tool_output_projection serializes correctly."""
        metadata = IncidentBundleMetadata(
            bundle_id="empty-001",
            captured_at=__import__("datetime").datetime(2024, 1, 15, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=0,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[_parse_pod_summary(FAKE_SMALL_PODS_RESPONSE["items"][0])],
            events=[],
            deployments=[],
            symptoms=[],
            tool_output_projection={},
        )

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)
        restored = json.loads(serialized)

        assert restored["tool_output_projection"] == {}


class TestEndToEndBundleSerialization:
    """End-to-end tests for bundle serialization with real collector behavior."""

    @unittest.mock.patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_bundle_from_collectors_has_projection_metadata(
        self, mock_kubectl: unittest.mock.MagicMock
    ) -> None:
        """Bundle from collect_incident_snapshot has projection metadata."""
        def kubectl_side_effect(*args: str, **kwargs: object) -> str:
            if "pods" in args and "-o" in args:
                return json.dumps(FAKE_SMALL_PODS_RESPONSE)
            if "deployments" in args and "-o" in args:
                return "{}"
            if "events" in args and "-o" in args:
                return json.dumps(FAKE_SMALL_EVENTS_RESPONSE)
            return "{}"

        mock_kubectl.side_effect = kubectl_side_effect

        from k8s_diag_agent.collect.incident_snapshot import collect_incident_snapshot

        bundle = collect_incident_snapshot(namespace="default")

        bundle_dict = bundle.to_dict()
        serialized = json.dumps(bundle_dict)

        assert "tool_output_projection" in bundle_dict
        assert "pods" in bundle_dict["tool_output_projection"]
        assert "events" in bundle_dict["tool_output_projection"]

        pods_meta = bundle_dict["tool_output_projection"]["pods"]
        assert "source_tool" in pods_meta
        assert "raw_size_bytes" in pods_meta
        assert "llm_visible_size_bytes" in pods_meta

        events_meta = bundle_dict["tool_output_projection"]["events"]
        assert "source_tool" in events_meta
        assert "raw_size_bytes" in events_meta
        assert "llm_visible_size_bytes" in events_meta

        assert "raw_artifact_path" not in serialized
        assert "raw_output" not in serialized

    @unittest.mock.patch("k8s_diag_agent.collect.incident_collectors.kubectl")
    def test_large_output_bundle_spill_preserves_artifact_id(
        self, mock_kubectl: unittest.mock.MagicMock
    ) -> None:
        """Large output bundle spill preserves raw_artifact_id."""
        from k8s_diag_agent.collect.incident_collectors import collect_pods
        from k8s_diag_agent.collect.incident_snapshot import _detect_symptoms
        from k8s_diag_agent.datetime_utils import now_utc

        def kubectl_side_effect(*args: str, **kwargs: object) -> str:
            if "pods" in args and "-o" in args:
                return json.dumps(FAKE_LARGE_PODS_RESPONSE)
            if "deployments" in args and "-o" in args:
                return "{}"
            if "events" in args and "-o" in args:
                return json.dumps(FAKE_SMALL_EVENTS_RESPONSE)
            return "{}"

        mock_kubectl.side_effect = kubectl_side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            pods, errors, pod_projection = collect_pods("default", None, artifact_dir)

            metadata = IncidentBundleMetadata(
                bundle_id="spill-test",
                captured_at=now_utc(),
                namespace="default",
                since_hours=2,
                context=None,
                total_pods=len(pods),
                total_events=1,
                total_deployments=0,
                failing_pods_count=0,
                symptoms_count=0,
            )

            bundle = IncidentEvidenceBundle(
                metadata=metadata,
                pods=pods,
                events=[_parse_event_summary(FAKE_SMALL_EVENTS_RESPONSE["items"][0])],
                deployments=[],
                symptoms=_detect_symptoms(pods, []),
                tool_output_projection={"pods": pod_projection},
            )

            bundle_dict = bundle.to_dict()
            serialized = json.dumps(bundle_dict)

            if bundle_dict["tool_output_projection"]["pods"].get("spill_occurred"):
                assert "raw_artifact_id" in bundle_dict["tool_output_projection"]["pods"]
                artifact_id = bundle_dict["tool_output_projection"]["pods"]["raw_artifact_id"]
                assert artifact_id is not None
                assert artifact_id in serialized

            assert "raw_artifact_path" not in serialized
