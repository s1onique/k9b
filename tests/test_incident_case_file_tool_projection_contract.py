"""Tests for LLM case-file tool_output_projection boundary.

This module tests that tool_output_projection metadata survives the journey from
IncidentEvidenceBundle through the case-file generation into LLM-facing prompts.

Required coverage:
1. case file includes tool_output_projection when bundle contains it
2. case file includes pods projection metadata
3. case file includes events projection metadata
4. case file includes deployments projection metadata
5. pods/events/deployments projection metadata have identical key sets in case file
6. raw_artifact_id is preserved
7. spill_required_but_no_artifact_dir bounded error is preserved
8. raw_artifact_path is absent
9. raw_output is absent
10. standalone llm_visible is absent
11. raw Kubernetes list payloads are absent from projection metadata
12. projection metadata is JSON serializable without custom encoders
13. prompt builder does not inject forbidden fields from projection metadata
14. existing parsed summaries remain available to the case file
15. read_only remains true and allowed_actions remains empty
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


def _make_deployments_projection(with_forbidden: bool = False) -> dict[str, Any]:
    """Create deployments projection metadata for testing."""
    projection: dict[str, Any] = {
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
    }
    if with_forbidden:
        projection["raw_artifact_path"] = "/tmp/forbidden/deployments"
    return projection


def _make_error_projection() -> dict[str, Any]:
    """Create error projection metadata for testing."""
    return {
        "schema_version": "1.0",
        "source_tool": "kubectl_get",
        "spill_occurred": True,
        "spill_reason": "size_threshold",
        "raw_artifact_id": "artifact-error-xyz",
        "raw_size_bytes": 0,
        "llm_visible_size_bytes": 0,
        "content_type": "json",
        "error": "spill_required_but_no_artifact_dir",
        "provenance": {
            "namespace": "default",
            "resource": "pods",
        },
    }


# =============================================================================
# Forbidden Key Scanner
# =============================================================================


def _assert_forbidden_keys_absent(obj: object, path: str = "root") -> None:
    """Recursively assert forbidden keys are absent from nested dict/list structures.

    Fails on:
    - raw_artifact_path
    - raw_output
    - llm_visible (standalone - llm_visible_size_bytes is allowed)

    Does not fail on:
    - llm_visible_size_bytes
    """
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


class TestCaseFileProjectionContract(unittest.TestCase):
    """Test tool_output_projection integration in case files."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.pods_projection = _make_pods_projection()
        self.events_projection = _make_events_projection()
        self.deployments_projection = _make_deployments_projection()
        self.error_projection = _make_error_projection()
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

    # -------------------------------------------------------------------------
    # 1. case file includes tool_output_projection when bundle contains it
    # -------------------------------------------------------------------------
    def test_case_file_includes_projection_when_provided(self) -> None:
        """Case file includes tool_output_projection when bundle contains it."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("tool_output_projection", case_file)
        self.assertIn("pods", case_file["tool_output_projection"])

    def test_case_file_excludes_projection_when_not_provided(self) -> None:
        """Case file excludes tool_output_projection when not provided."""
        case_file = self._build_case_file_with_projection(None)

        self.assertNotIn("tool_output_projection", case_file)

    # -------------------------------------------------------------------------
    # 2-4. case file includes pods/events/deployments projection metadata
    # -------------------------------------------------------------------------
    def test_case_file_includes_pods_projection_metadata(self) -> None:
        """Case file includes pods projection metadata."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("pods", case_file["tool_output_projection"])
        pods_meta = case_file["tool_output_projection"]["pods"]
        self.assertEqual(pods_meta["schema_version"], "1.0")
        self.assertEqual(pods_meta["source_tool"], "kubectl_get")
        self.assertEqual(pods_meta["spill_occurred"], True)

    def test_case_file_includes_events_projection_metadata(self) -> None:
        """Case file includes events projection metadata."""
        projection = {"events": self.events_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("events", case_file["tool_output_projection"])
        events_meta = case_file["tool_output_projection"]["events"]
        self.assertEqual(events_meta["schema_version"], "1.0")
        self.assertEqual(events_meta["source_tool"], "kubectl_events")

    def test_case_file_includes_deployments_projection_metadata(self) -> None:
        """Case file includes deployments projection metadata."""
        projection = {"deployments": self.deployments_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("deployments", case_file["tool_output_projection"])
        deploy_meta = case_file["tool_output_projection"]["deployments"]
        self.assertEqual(deploy_meta["schema_version"], "1.0")
        self.assertEqual(deploy_meta["source_tool"], "kubectl_get")

    # -------------------------------------------------------------------------
    # 5. pods/events/deployments projection metadata have identical key sets
    # -------------------------------------------------------------------------
    def test_projection_metadata_key_sets_match(self) -> None:
        """Pods/events/deployments projection metadata have identical key sets."""
        projection = {
            "pods": self.pods_projection,
            "events": self.events_projection,
            "deployments": self.deployments_projection,
        }
        case_file = self._build_case_file_with_projection(projection)

        pods_keys = set(case_file["tool_output_projection"]["pods"].keys())
        events_keys = set(case_file["tool_output_projection"]["events"].keys())
        deployments_keys = set(case_file["tool_output_projection"]["deployments"].keys())

        self.assertEqual(pods_keys, events_keys)
        self.assertEqual(events_keys, deployments_keys)

    # -------------------------------------------------------------------------
    # 6. raw_artifact_id is preserved
    # -------------------------------------------------------------------------
    def test_raw_artifact_id_preserved(self) -> None:
        """raw_artifact_id is preserved in case file."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertEqual(
            case_file["tool_output_projection"]["pods"]["raw_artifact_id"],
            "artifact-pods-abc-123",
        )

    # -------------------------------------------------------------------------
    # 7. bounded error states preserved
    # -------------------------------------------------------------------------
    def test_error_projection_preserved(self) -> None:
        """spill_required_but_no_artifact_dir bounded error is preserved."""
        projection = {"pods": self.error_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertEqual(
            case_file["tool_output_projection"]["pods"]["error"],
            "spill_required_but_no_artifact_dir",
        )

    # -------------------------------------------------------------------------
    # 8. raw_artifact_path is absent
    # -------------------------------------------------------------------------
    def test_raw_artifact_path_absent(self) -> None:
        """raw_artifact_path is absent from serialized case file."""
        projection = {
            "pods": _make_pods_projection(with_forbidden=True),
            "events": _make_events_projection(with_forbidden=True),
            "deployments": _make_deployments_projection(with_forbidden=True),
        }
        case_file = self._build_case_file_with_projection(projection)

        # Assert raw_artifact_path is absent
        for source in ("pods", "events", "deployments"):
            self.assertNotIn("raw_artifact_path", case_file["tool_output_projection"][source])

    # -------------------------------------------------------------------------
    # 9. raw_output is absent
    # -------------------------------------------------------------------------
    def test_raw_output_absent(self) -> None:
        """raw_output is absent from serialized case file."""
        projection = {
            "pods": _make_pods_projection(with_forbidden=True),
            "events": _make_events_projection(with_forbidden=True),
        }
        case_file = self._build_case_file_with_projection(projection)

        # Assert raw_output is absent
        self.assertNotIn("raw_output", case_file["tool_output_projection"]["pods"])
        self.assertNotIn("raw_output", case_file["tool_output_projection"]["events"])

    # -------------------------------------------------------------------------
    # 10. standalone llm_visible is absent
    # -------------------------------------------------------------------------
    def test_llm_visible_absent(self) -> None:
        """standalone llm_visible is absent from serialized case file."""
        projection = {
            "pods": _make_pods_projection(with_forbidden=True),
        }
        case_file = self._build_case_file_with_projection(projection)

        # Assert llm_visible is absent
        self.assertNotIn("llm_visible", case_file["tool_output_projection"]["pods"])

    def test_llm_visible_size_bytes_allowed(self) -> None:
        """llm_visible_size_bytes is allowed (not stripped)."""
        projection = {
            "pods": self.pods_projection,
        }
        case_file = self._build_case_file_with_projection(projection)

        # llm_visible_size_bytes should be preserved
        self.assertIn("llm_visible_size_bytes", case_file["tool_output_projection"]["pods"])
        self.assertEqual(
            case_file["tool_output_projection"]["pods"]["llm_visible_size_bytes"],
            8000,
        )

    # -------------------------------------------------------------------------
    # 11. raw Kubernetes list payloads absent from projection metadata
    # -------------------------------------------------------------------------
    def test_raw_kubernetes_list_payloads_absent(self) -> None:
        """Raw Kubernetes list payloads are absent from projection metadata."""
        projection = {
            "pods": _make_pods_projection(with_forbidden=True),
        }
        case_file = self._build_case_file_with_projection(projection)

        # Assert no raw Kubernetes list payloads
        serialized = json.dumps(case_file["tool_output_projection"])
        self.assertNotIn("apiVersion", serialized)
        self.assertNotIn('"kind": "PodList"', serialized)
        self.assertNotIn('"kind": "EventList"', serialized)
        self.assertNotIn('"kind": "DeploymentList"', serialized)
        self.assertNotIn('"items":', serialized)

    # -------------------------------------------------------------------------
    # 12. projection metadata is JSON serializable
    # -------------------------------------------------------------------------
    def test_projection_json_serializable(self) -> None:
        """Projection metadata is JSON serializable without custom encoders."""
        projection = {
            "pods": self.pods_projection,
            "events": self.events_projection,
            "deployments": self.deployments_projection,
        }
        case_file = self._build_case_file_with_projection(projection)

        # Should not raise
        json_str = json.dumps(case_file["tool_output_projection"])
        self.assertIsInstance(json_str, str)

        # Should deserialize correctly
        restored = json.loads(json_str)
        self.assertEqual(restored["pods"]["raw_artifact_id"], "artifact-pods-abc-123")

    # -------------------------------------------------------------------------
    # 13. prompt builder does not inject forbidden fields
    # -------------------------------------------------------------------------
    def test_forbidden_keys_recursively_absent(self) -> None:
        """Recursively assert forbidden keys are absent from projection."""
        projection = {
            "pods": _make_pods_projection(with_forbidden=True),
            "events": _make_events_projection(with_forbidden=True),
            "deployments": _make_deployments_projection(with_forbidden=True),
        }
        case_file = self._build_case_file_with_projection(projection)

        # Should not raise - means no forbidden keys found
        _assert_forbidden_keys_absent(case_file["tool_output_projection"])

    # -------------------------------------------------------------------------
    # 14. existing parsed summaries remain available
    # -------------------------------------------------------------------------
    def test_parsed_summaries_available(self) -> None:
        """Existing parsed evidence summaries remain available in case file."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        # Incident should still be available
        self.assertIn("incident", case_file)
        self.assertEqual(case_file["incident"]["incident_id"], self.mock_incident.incident_id)

        # Signals should still be available
        self.assertIn("signals", case_file)
        self.assertIsInstance(case_file["signals"], list)

        # Events should still be available
        self.assertIn("events", case_file)
        self.assertIsInstance(case_file["events"], list)

    # -------------------------------------------------------------------------
    # 15. read_only remains true and allowed_actions remains empty
    # -------------------------------------------------------------------------
    def test_safety_boundary_preserved(self) -> None:
        """read_only remains true and allowed_actions remains empty."""
        projection = {"pods": self.pods_projection}
        case_file = self._build_case_file_with_projection(projection)

        self.assertTrue(case_file["read_only"])
        self.assertEqual(case_file["allowed_actions"], [])
        self.assertIsInstance(case_file["disallowed_actions"], list)


if __name__ == "__main__":
    unittest.main()
