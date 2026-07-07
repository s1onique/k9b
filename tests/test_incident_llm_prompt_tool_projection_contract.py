"""Tests for LLM prompt tool_output_projection boundary.

This module tests that tool_output_projection metadata in case files
is correctly handled when building LLM diagnosis prompts.

The prompt contract requires:
- rendered prompt/case JSON includes tool_output_projection summary
- rendered prompt/case JSON excludes raw_artifact_path
- rendered prompt/case JSON excludes raw_output
- rendered prompt/case JSON excludes standalone llm_visible
- prompt keeps artifact IDs, not local paths
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
from k8s_diag_agent.collect.incident_llm_diagnosis import (
    build_diagnosis_prompt,
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


def _make_projection_with_forbidden() -> dict[str, dict[str, Any]]:
    """Create projection metadata with forbidden fields for testing."""
    return {
        "pods": {
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
            # Forbidden fields - should be stripped
            "raw_artifact_path": "/tmp/forbidden/pods",
            "raw_output": "FORBIDDEN_PODS_OUTPUT",
            "llm_visible": {"items": [{"apiVersion": "v1", "kind": "Pod"}]},
        },
        "events": {
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
            # Forbidden fields - should be stripped
            "raw_artifact_path": "/tmp/forbidden/events",
            "raw_output": "FORBIDDEN_EVENTS_OUTPUT",
        },
        "deployments": {
            "schema_version": "1.0",
            "source_tool": "kubectl_get",
            "spill_occurred": False,
            "spill_reason": None,
            "raw_artifact_id": "artifact-deployments-ghi-789",
            "raw_size_bytes": 3000,
            "llm_visible_size_bytes": 3000,
            "content_type": "json",
            "error": None,
            "provenance": {
                "namespace": "default",
                "resource": "deployments",
            },
            # Forbidden fields - should be stripped
            "raw_artifact_path": "/tmp/forbidden/deployments",
        },
    }


# =============================================================================
# Test Cases
# =============================================================================


class TestLLMPromptProjectionContract(unittest.TestCase):
    """Test tool_output_projection handling in LLM prompts."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.projection_with_forbidden = _make_projection_with_forbidden()
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

    def test_prompt_includes_projection_summary(self) -> None:
        """Rendered prompt includes tool_output_projection summary."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # The prompt should include projection metadata in the JSON
        self.assertIn("tool_output_projection", prompt)
        self.assertIn("raw_artifact_id", prompt)
        self.assertIn("artifact-pods-abc-123", prompt)

    def test_prompt_includes_all_source_projections(self) -> None:
        """Prompt includes pods, events, and deployments projections."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # All three sources should be referenced
        self.assertIn("artifact-pods-abc-123", prompt)
        self.assertIn("artifact-events-def-456", prompt)
        self.assertIn("artifact-deployments-ghi-789", prompt)

    def test_prompt_excludes_raw_artifact_path(self) -> None:
        """Rendered prompt excludes raw_artifact_path."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # raw_artifact_path should not appear in the prompt
        self.assertNotIn("raw_artifact_path", prompt)
        self.assertNotIn("/tmp/forbidden", prompt)

    def test_prompt_excludes_raw_output(self) -> None:
        """Rendered prompt excludes raw_output."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # raw_output should not appear in the prompt
        self.assertNotIn("raw_output", prompt)
        self.assertNotIn("FORBIDDEN_PODS_OUTPUT", prompt)
        self.assertNotIn("FORBIDDEN_EVENTS_OUTPUT", prompt)

    def test_prompt_excludes_llm_visible(self) -> None:
        """Rendered prompt excludes standalone llm_visible."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # llm_visible (standalone) should not appear in the prompt
        self.assertNotIn('"llm_visible":', prompt)

    def test_prompt_allows_llm_visible_size_bytes(self) -> None:
        """Prompt allows llm_visible_size_bytes."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # llm_visible_size_bytes should be present (not stripped)
        self.assertIn("llm_visible_size_bytes", prompt)

    def test_prompt_keeps_artifact_ids(self) -> None:
        """Prompt keeps artifact IDs, not local paths."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # Artifact IDs should be present
        self.assertIn("artifact-pods-abc-123", prompt)
        self.assertIn("artifact-events-def-456", prompt)
        self.assertIn("artifact-deployments-ghi-789", prompt)

    def test_prompt_excludes_local_paths(self) -> None:
        """Prompt excludes local filesystem paths."""
        case_file = self._build_case_file_with_projection(self.projection_with_forbidden)
        prompt = build_diagnosis_prompt(case_file)

        # Local paths should not appear
        self.assertNotIn("/tmp/", prompt)
        self.assertNotIn("forbidden", prompt)

    def test_case_file_json_serialization_excludes_forbidden(self) -> None:
        """Case file JSON serialization excludes forbidden fields."""
        projection = _make_projection_with_forbidden()
        case_file = self._build_case_file_with_projection(projection)

        json_str = json.dumps(case_file)

        # Forbidden strings should not appear in serialized case file
        self.assertNotIn("/tmp/forbidden", json_str)
        self.assertNotIn("FORBIDDEN_PODS_OUTPUT", json_str)
        self.assertNotIn('"llm_visible"', json_str)

    def test_case_file_json_includes_safe_fields(self) -> None:
        """Case file JSON includes safe projection fields."""
        projection = _make_projection_with_forbidden()
        case_file = self._build_case_file_with_projection(projection)

        json_str = json.dumps(case_file)

        # Safe fields should appear
        self.assertIn("artifact-pods-abc-123", json_str)
        self.assertIn("llm_visible_size_bytes", json_str)
        self.assertIn("spill_occurred", json_str)


if __name__ == "__main__":
    unittest.main()
