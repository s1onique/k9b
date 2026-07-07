"""Tests for written incident.json file contract.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-BUNDLE-CONTRACT01
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_models import (
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
)
from k8s_diag_agent.collect.incident_snapshot import (
    _parse_event_summary,
    _parse_pod_summary,
)
from k8s_diag_agent.collect.incident_writer import write_incident_bundle

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


def test_written_incident_json_contains_projection_metadata() -> None:
    """Written incident.json contains tool_output_projection."""
    metadata = IncidentBundleMetadata(
        bundle_id="write-001",
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
            "provenance": {},
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

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        written = write_incident_bundle(bundle, output_dir)

        incident_path = written["incident.json"]
        incident_data = json.loads(incident_path.read_text())

        assert "tool_output_projection" in incident_data
        assert "pods" in incident_data["tool_output_projection"]
        assert "events" in incident_data["tool_output_projection"]

        incident_text = incident_path.read_text()
        assert "raw_artifact_path" not in incident_text
        assert "raw_output" not in incident_text


def test_written_incident_json_forbidden_keys_comprehensive() -> None:
    """Comprehensive check: no forbidden keys anywhere in written incident.json."""
    metadata = IncidentBundleMetadata(
        bundle_id="forbid-write-001",
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
            "raw_artifact_id": "artifact-xyz-789",
            "raw_size_bytes": 50000,
            "llm_visible_size_bytes": 8000,
            "content_type": "json",
            "error": None,
            "provenance": {},
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

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        written = write_incident_bundle(bundle, output_dir)

        incident_path = written["incident.json"]
        incident_text = incident_path.read_text()

        assert "raw_artifact_path" not in incident_text
        assert "raw_output" not in incident_text

        standalone_llm_visible = re.compile(r'"llm_visible"[:\s]')
        assert standalone_llm_visible.search(incident_text) is None, \
            "Standalone 'llm_visible' key found in incident.json"

        assert "artifact-xyz-789" in incident_text
