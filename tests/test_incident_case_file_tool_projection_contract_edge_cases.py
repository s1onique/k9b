"""Edge cases and serialization tests for tool_output_projection contract.

This module contains:
- Edge case tests for tool_output_projection in case files
- Serialization tests for case files with projection
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from typing import Any, cast
from unittest import mock

from k8s_diag_agent.collect.incident_case_file import (
    build_incident_case_file,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def _make_mock_incident(incident_id: str = "test-incident-123") -> Incident:
    """Create a mock incident for testing."""
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate-123",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind="Pod",
        candidate_class="PodNotReady",
        severity="high",
        status=IncidentStatus.INVESTIGATING,
        first_observed_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        last_observed_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        signals=[
            IncidentSignal(
                source="test",
                reason="PodNotReady",
                message="Pod is not ready",
                captured_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )
        ],
        evidence_links=[],
        signal_count=1,
        evidence_count=0,
    )


def _make_pods_projection(with_forbidden: bool = False) -> dict[str, Any]:
    """Create pods projection metadata for testing."""
    projection: dict[str, Any] = {
        "schema_version": "1.0",
        "source_tool": "kubectl_get",
        "spill_occurred": True,
        "spill_reason": "size_threshold",
        "raw_artifact_id": "artifact-pods-abc-123",
        "raw_size_bytes": 50000,
        "llm_visible_size_bytes": 8000,
        "content_type": "json",
        "error": None,
        "provenance": {
            "namespace": "default",
            "resource": "pods",
        },
    }
    if with_forbidden:
        projection["raw_artifact_path"] = "/tmp/forbidden/path"
        projection["raw_output"] = "FORBIDDEN_RAW_OUTPUT"
        projection["llm_visible"] = {"items": [{"apiVersion": "v1", "kind": "Pod"}]}
    return projection


def _make_events_projection(with_forbidden: bool = False) -> dict[str, Any]:
    """Create events projection metadata for testing."""
    projection: dict[str, Any] = {
        "schema_version": "1.0",
        "source_tool": "kubectl_events",
        "spill_occurred": False,
        "spill_reason": None,
        "raw_artifact_id": "artifact-events-def-456",
        "raw_size_bytes": 5000,
        "llm_visible_size_bytes": 5000,
        "content_type": "json",
        "error": None,
        "provenance": {
            "namespace": "default",
            "resource": "events",
        },
    }
    if with_forbidden:
        projection["raw_artifact_path"] = "/tmp/forbidden/events"
        projection["raw_output"] = "FORBIDDEN_EVENTS_OUTPUT"
    return projection


# =============================================================================
# Forbidden Key Scanner
# =============================================================================


def _assert_forbidden_keys_absent(obj: object, path: str = "root") -> None:
    """Recursively assert forbidden keys are absent from nested dict/list structures."""
    FORBIDDEN_KEYS = {"raw_artifact_path", "raw_output", "llm_visible"}

    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_KEYS:
                raise AssertionError(
                    f"Forbidden key '{key}' found at {path}.{key}"
                )
            _assert_forbidden_keys_absent(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _assert_forbidden_keys_absent(item, f"{path}[{i}]")


# =============================================================================
# Test Cases
# =============================================================================


class TestCaseFileProjectionEdgeCases(unittest.TestCase):
    """Test edge cases for tool_output_projection in case files."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _build_case_file_with_projection(
        self,
        projection: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Helper to build case file with mocked incident and optional projection."""
        with mock.patch(
            "k8s_diag_agent.collect.incident_case_file.get_incident_store"
        ) as mock_store:
            mock_store.return_value.get_incident.return_value = self.mock_incident
            result = build_incident_case_file(
                incident_id=self.mock_incident.incident_id,
                now=self.fixed_now,
                tool_output_projection=projection,
            )
            assert result is not None
            return cast("dict[str, Any]", result)

    def test_empty_projection_not_included(self) -> None:
        """Empty projection dict is not included in case file."""
        projection: dict[str, dict[str, Any]] = {}
        case_file = self._build_case_file_with_projection(projection)

        self.assertNotIn("tool_output_projection", case_file)

    def test_projection_with_none_metadata_not_included(self) -> None:
        """Projection entries with None metadata are not included."""
        projection: dict[str, dict[str, Any]] = {
            "pods": None,  # type: ignore
        }
        case_file = self._build_case_file_with_projection(projection)

        self.assertNotIn("tool_output_projection", case_file)

    def test_nested_forbidden_fields_stripped(self) -> None:
        """Forbidden fields nested inside metadata values are stripped."""
        projection = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": False,
                "nested_data": {
                    "raw_artifact_path": "/tmp/forbidden/nested",
                    "safe_field": "allowed",
                },
            }
        }
        case_file = self._build_case_file_with_projection(projection)

        nested = case_file["tool_output_projection"]["pods"]["nested_data"]
        self.assertNotIn("raw_artifact_path", nested)
        self.assertEqual(nested["safe_field"], "allowed")

    def test_multiple_forbidden_keys_stripped(self) -> None:
        """Multiple forbidden keys are all stripped."""
        projection = {
            "pods": {
                "schema_version": "1.0",
                "source_tool": "kubectl_get",
                "spill_occurred": True,
                "raw_artifact_path": "/tmp/forbidden/path",
                "raw_output": "FORBIDDEN_RAW_OUTPUT",
                "llm_visible": {"key": "value"},
                "error": "test_error",
            }
        }
        case_file = self._build_case_file_with_projection(projection)

        pods_meta = case_file["tool_output_projection"]["pods"]
        self.assertNotIn("raw_artifact_path", pods_meta)
        self.assertNotIn("raw_output", pods_meta)
        self.assertNotIn("llm_visible", pods_meta)
        # Allowed fields should remain
        self.assertEqual(pods_meta["schema_version"], "1.0")
        self.assertEqual(pods_meta["error"], "test_error")


class TestCaseFileProjectionSerialization(unittest.TestCase):
    """Test serialized form of case file with tool_output_projection."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.pods_projection = _make_pods_projection()
        self.events_projection = _make_events_projection()
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _build_case_file_with_projection(
        self,
        projection: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Helper to build case file with mocked incident and optional projection."""
        with mock.patch(
            "k8s_diag_agent.collect.incident_case_file.get_incident_store"
        ) as mock_store:
            mock_store.return_value.get_incident.return_value = self.mock_incident
            result = build_incident_case_file(
                incident_id=self.mock_incident.incident_id,
                now=self.fixed_now,
                tool_output_projection=projection,
            )
            assert result is not None
            return cast("dict[str, Any]", result)

    def test_case_file_serializes_to_json(self) -> None:
        """Case file with projection serializes to JSON correctly."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        # Should serialize without errors
        json_str = json.dumps(case_file, indent=2)
        self.assertIn("tool_output_projection", json_str)
        self.assertIn("raw_artifact_id", json_str)

    def test_serialized_case_file_excludes_forbidden_strings(self) -> None:
        """Serialized case file excludes forbidden string patterns."""
        projection = {
            "pods": {
                **self.pods_projection,
                "raw_artifact_path": "/tmp/absolute/path",
                "raw_output": "FULL RAW OUTPUT HERE",
                "llm_visible": {"data": "LLM VISIBLE"},
            }
        }
        case_file = self._build_case_file_with_projection(projection)

        json_str = json.dumps(case_file)

        # Forbidden strings should not appear
        self.assertNotIn("/tmp/absolute/path", json_str)
        self.assertNotIn("FULL RAW OUTPUT", json_str)
        self.assertNotIn('"llm_visible"', json_str)

    def test_case_file_round_trip(self) -> None:
        """Case file survives JSON round-trip with projection."""
        projection = {
            "pods": self.pods_projection,
            "events": self.events_projection,
        }
        case_file = self._build_case_file_with_projection(projection)

        # Serialize and deserialize
        json_str = json.dumps(case_file)
        restored = json.loads(json_str)

        # Verify projection survived
        self.assertIn("tool_output_projection", restored)
        self.assertEqual(
            restored["tool_output_projection"]["pods"]["raw_artifact_id"],
            "artifact-pods-abc-123",
        )

    def test_forbidden_keys_absent_after_round_trip(self) -> None:
        """Forbidden keys remain absent after JSON round-trip."""
        projection = {
            "pods": {
                **self.pods_projection,
                "raw_artifact_path": "/tmp/forbidden",
                "raw_output": "RAW",
            }
        }
        case_file = self._build_case_file_with_projection(projection)

        # Serialize and deserialize
        json_str = json.dumps(case_file)
        restored = json.loads(json_str)

        # Forbidden keys should still be absent
        _assert_forbidden_keys_absent(restored.get("tool_output_projection", {}))


if __name__ == "__main__":
    unittest.main()
