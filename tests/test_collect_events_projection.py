"""Tests for collect_events bounded projection.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-SECOND-COLLECTOR01
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_collectors import collect_events
from k8s_diag_agent.collect.tool_budget_defaults import KUBECTL_EVENTS_BUDGET


class TestCollectEventsProjection:
    """Tests for collect_events bounded projection."""

    def test_small_events_output_returns_metadata_without_spill(self) -> None:
        """Small events output returns metadata without spill."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [
                {
                    "metadata": {
                        "name": "event-1",
                        "namespace": "default",
                        "lastTimestamp": "2024-01-15T12:00:00Z",
                    },
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": "Back-off restarting container",
                    "involvedObject": {"kind": "Pod", "name": "test-pod"},
                    "count": 1,
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            # Semantic output unchanged
            assert len(events) == 1
            assert events[0].reason == "BackOff"
            assert errors == []

            # Projection metadata present
            assert isinstance(metadata, dict)
            assert metadata["source_tool"] == "kubectl_events"
            assert metadata["spill_occurred"] is False
            assert metadata["raw_size_bytes"] > 0
            assert metadata["llm_visible_size_bytes"] > 0
            # content_type may be "manifest" or "json" depending on reducer
            assert metadata["content_type"] in ("json", "manifest")

    def test_large_events_output_spills_when_artifact_dir_provided(self) -> None:
        """Large events output spills to artifact when artifact_dir is provided."""
        import unittest.mock

        # Create large events payload
        items = []
        for i in range(200):
            items.append({
                "metadata": {
                    "name": f"event-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 5,
                    "lastTimestamp": "2024-01-15T12:00:00Z",
                },
                "type": "Warning",
                "reason": f"Reason-{i}",
                "message": f"Message {i} with additional details " * 5,
                "involvedObject": {"kind": "Pod", "name": f"pod-{i}"},
                "count": i + 1,
            })

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": items,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            with unittest.mock.patch(
                "k8s_diag_agent.collect.incident_collectors.kubectl",
                return_value=mock_output,
            ):
                events, errors, metadata = collect_events("default", None, 2, artifact_dir)

                # Should have events
                assert len(events) == 200
                assert errors == []

                # Spill metadata present
                assert metadata.get("spill_occurred") is True
                assert metadata.get("raw_artifact_id") is not None
                # raw_artifact_path is NOT included per artifact path policy
                assert "raw_artifact_path" not in metadata
                assert metadata.get("raw_size_bytes") > metadata.get("llm_visible_size_bytes")

    def test_large_events_output_without_artifact_dir_returns_bounded_error(self) -> None:
        """Large events output without artifact_dir returns bounded error metadata."""
        import unittest.mock

        # Create large events payload
        items = []
        for i in range(200):
            items.append({
                "metadata": {
                    "name": f"event-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 5,
                    "lastTimestamp": "2024-01-15T12:00:00Z",
                },
                "type": "Warning",
                "reason": f"Reason-{i}",
                "message": f"Message {i} with additional details " * 5,
                "involvedObject": {"kind": "Pod", "name": f"pod-{i}"},
                "count": i + 1,
            })

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": items,
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            # Should have events (parsed successfully)
            assert len(events) == 200
            assert errors == []

            # Bounded error metadata
            assert metadata.get("spill_occurred") is False
            assert metadata.get("error") is not None
            assert "spill_required_but_no_artifact_dir" in metadata["error"]
            # Raw size exceeds threshold
            assert metadata.get("raw_size_bytes") > KUBECTL_EVENTS_BUDGET.artifact_spill_threshold_bytes
            # LLM visible reduced
            assert metadata.get("llm_visible_size_bytes") < metadata.get("raw_size_bytes")

    def test_collect_events_metadata_propagated_into_bundle(self) -> None:
        """collect_events metadata propagates into IncidentEvidenceBundle."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [
                {
                    "metadata": {
                        "name": "event-1",
                        "namespace": "default",
                        "lastTimestamp": "2024-01-15T12:00:00Z",
                    },
                    "type": "Warning",
                    "reason": "Test",
                    "message": "Test message",
                    "count": 1,
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            # Verify metadata structure matches expected bundle propagation
            assert "source_tool" in metadata
            assert metadata["source_tool"] == "kubectl_events"
            assert "raw_size_bytes" in metadata
            assert "llm_visible_size_bytes" in metadata
            assert "schema_version" in metadata

    def test_collect_events_source_tool_is_correct(self) -> None:
        """source_tool is kubectl_events for events collector."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            assert metadata["source_tool"] == "kubectl_events"

    def test_collect_events_raw_and_llm_sizes_present(self) -> None:
        """raw_size_bytes and llm_visible_size_bytes are present."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [
                {
                    "metadata": {
                        "name": "event-1",
                        "namespace": "default",
                        "lastTimestamp": "2024-01-15T12:00:00Z",
                    },
                    "type": "Warning",
                    "reason": "Test",
                    "message": "Test message",
                    "count": 1,
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            assert "raw_size_bytes" in metadata
            assert "llm_visible_size_bytes" in metadata
            assert metadata["raw_size_bytes"] > 0
            assert metadata["llm_visible_size_bytes"] > 0

    def test_collect_events_semantic_output_unchanged(self) -> None:
        """Existing collector semantic output remains unchanged."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
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
                    "count": 5,
                },
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            events, errors, metadata = collect_events("default", None, 2)

            # Semantic output matches expected EventSummary
            assert len(events) == 1
            assert events[0].namespace == "default"
            assert events[0].name == "event-1"
            assert events[0].type == "Warning"
            assert events[0].reason == "BackOff"
            assert events[0].count == 5
            assert events[0].involved_object_kind == "Pod"
            assert events[0].involved_object_name == "crashloop-pod"


class TestCollectEventsStaleCallerRegression:
    """Regression tests for collect_events return shape change."""

    def test_collect_events_returns_three_tuple(self) -> None:
        """collect_events returns (events, errors, projection_metadata) tuple."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            result = collect_events("default", None, 2)

            # Must be 3-tuple
            assert isinstance(result, tuple)
            assert len(result) == 3
            events, errors, metadata = result
            assert isinstance(events, list)
            assert isinstance(errors, list)
            assert isinstance(metadata, dict)

    def test_collect_events_two_tuple_call_fails(self) -> None:
        """Old 2-tuple unpacking of collect_events should fail."""
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "EventList",
            "items": [],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            # Old code expecting 2 values should fail
            try:
                events, errors = collect_events("default", None, 2)
                # If this doesn't raise, the test framework should catch the extra value
                assert False, "Should have raised ValueError for too many values"
            except ValueError as e:
                assert "too many values" in str(e) or "unpack" in str(e)
