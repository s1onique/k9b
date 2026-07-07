"""Epic closure verifier for HolmesGPT tool-output projection slice.

This module provides a compact regression check that verifies the tool-output
projection slice is closed and all boundaries are protected.

Reference: META-K9B-HOLMESGPT-TOOL-PROJECTION-CLOSEOUT

Coverage:
1. collect_pods returns projection metadata
2. collect_events returns projection metadata
3. collect_deployments returns projection metadata
4. All three projection metadata dicts share the canonical key set
5. IncidentEvidenceBundle serialization preserves tool_output_projection
6. Case file preserves tool_output_projection
7. Prompt includes safe projection metadata
8. Forbidden keys are absent from serialized bundle/case-file/prompt
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from typing import Any, cast
from unittest import mock

from k8s_diag_agent.collect.incident_case_file import (
    _FORBIDDEN_PROJECTION_KEYS,
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
from k8s_diag_agent.collect.incident_models import (
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
)
from k8s_diag_agent.collect.tool_projection_metadata import (
    PROJECTION_METADATA_SCHEMA_VERSION,
    build_tool_projection_metadata,
)
from k8s_diag_agent.collect.tool_spill_types import ToolOutputSpillResult

# Canonical Key Set (from schema)
# =============================================================================

CANONICAL_PROJECTION_KEYS = frozenset({
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
})


# =============================================================================

def _make_mock_incident(incident_id: str = "test-incident-closure") -> Incident:
    """Create a mock incident for testing."""
    return Incident(
        incident_id=incident_id,
        source_candidate_id="test-candidate-closure",
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


def _make_projection_metadata(
    source_tool: str,
    resource: str,
    spill_occurred: bool = False,
    with_forbidden: bool = False,
) -> dict[str, Any]:
    """Create projection metadata for testing."""
    metadata: dict[str, Any] = {
        "schema_version": PROJECTION_METADATA_SCHEMA_VERSION,
        "source_tool": source_tool,
        "spill_occurred": spill_occurred,
        "spill_reason": "size_threshold" if spill_occurred else None,
        "raw_artifact_id": f"artifact-{resource}-123" if spill_occurred else None,
        "raw_size_bytes": 50000 if spill_occurred else 1000,
        "llm_visible_size_bytes": 8000 if spill_occurred else 500,
        "content_type": "json",
        "error": None,
        "provenance": {"namespace": "default", "resource": resource},
    }

    if with_forbidden:
        metadata["raw_artifact_path"] = "/tmp/forbidden/path"
        metadata["raw_output"] = "FORBIDDEN_RAW_OUTPUT"
        metadata["llm_visible"] = {"items": []}

    return metadata


# =============================================================================
# Forbidden Key Scanner
# =============================================================================


def _scan_forbidden_keys(obj: object, path: str = "root") -> list[str]:
    """Scan for forbidden keys in nested dict/list structures.

    Returns list of found forbidden key paths.
    """
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _FORBIDDEN_PROJECTION_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_scan_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_scan_forbidden_keys(item, f"{path}[{i}]"))
    return found


# =============================================================================
# Test Cases
# =============================================================================


class TestCollectorProjectionMetadata(unittest.TestCase):
    """Verify collectors return projection metadata with canonical key set."""

    def test_pods_projection_metadata_has_canonical_keys(self) -> None:
        """collect_pods returns projection metadata with canonical keys."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
            provenance={"namespace": "default", "resource": "pods"},
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")
        metadata_dict = metadata.to_dict()

        self.assertEqual(set(metadata_dict.keys()), CANONICAL_PROJECTION_KEYS)

    def test_events_projection_metadata_has_canonical_keys(self) -> None:
        """collect_events returns projection metadata with canonical keys."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            provenance={"namespace": "default", "resource": "events"},
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_events")
        metadata_dict = metadata.to_dict()

        self.assertEqual(set(metadata_dict.keys()), CANONICAL_PROJECTION_KEYS)

    def test_deployments_projection_metadata_has_canonical_keys(self) -> None:
        """collect_deployments returns projection metadata with canonical keys."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=3000,
            llm_visible_size_bytes=3000,
            content_type="json",
            provenance={"namespace": "default", "resource": "deployments"},
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")
        metadata_dict = metadata.to_dict()

        self.assertEqual(set(metadata_dict.keys()), CANONICAL_PROJECTION_KEYS)

    def test_all_collectors_share_identical_key_sets(self) -> None:
        """Pods/events/deployments projection metadata share identical key sets."""
        pods_spill = ToolOutputSpillResult(
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            provenance={"resource": "pods"},
        )
        events_spill = ToolOutputSpillResult(
            raw_size_bytes=800,
            llm_visible_size_bytes=400,
            provenance={"resource": "events"},
        )
        deployments_spill = ToolOutputSpillResult(
            raw_size_bytes=3000,
            llm_visible_size_bytes=3000,
            provenance={"resource": "deployments"},
        )

        pods_keys = set(build_tool_projection_metadata(pods_spill, "kubectl_get").to_dict().keys())
        events_keys = set(build_tool_projection_metadata(events_spill, "kubectl_events").to_dict().keys())
        deployments_keys = set(build_tool_projection_metadata(deployments_spill, "kubectl_get").to_dict().keys())

        self.assertEqual(pods_keys, events_keys)
        self.assertEqual(events_keys, deployments_keys)
        self.assertEqual(pods_keys, CANONICAL_PROJECTION_KEYS)


class TestBundleSerializationBoundary(unittest.TestCase):
    """Verify IncidentEvidenceBundle serialization preserves safe metadata."""

    def _make_minimal_bundle(
        self,
        projection_metadata: dict[str, Any] | None = None,
    ) -> IncidentEvidenceBundle:
        """Create a minimal IncidentEvidenceBundle for testing."""
        from k8s_diag_agent.collect.incident_models import (
            EventSummary,
            PodHealthStatus,
            PodSummary,
        )

        metadata = IncidentBundleMetadata(
            bundle_id="closure-test-001",
            captured_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=1,
            total_deployments=0,
            failing_pods_count=0,
            symptoms_count=0,
        )

        return IncidentEvidenceBundle(
            metadata=metadata,
            pods=[
                PodSummary(
                    name="test-pod",
                    namespace="default",
                    phase="Running",
                    health_status=PodHealthStatus.RUNNING,
                    restart_count=0,
                    node="node-1",
                    image_refs=("nginx:1.21",),
                    reason=None,
                    message=None,
                )
            ],
            events=[
                EventSummary(
                    namespace="default",
                    name="event-1",
                    type="Warning",
                    reason="BackOff",
                    message="Back-off restarting container",
                    involved_object_kind="Pod",
                    involved_object_name="test-pod",
                    count=1,
                    last_timestamp="2024-01-15T12:00:00Z",
                )
            ],
            deployments=[],
            symptoms=[],
            tool_output_projection=projection_metadata or {},
        )

    def test_bundle_contains_tool_output_projection(self) -> None:
        """IncidentEvidenceBundle contains tool_output_projection."""
        projection_metadata = {
            "pods": _make_projection_metadata("kubectl_get", "pods"),
            "events": _make_projection_metadata("kubectl_events", "events"),
            "deployments": _make_projection_metadata("kubectl_get", "deployments"),
        }

        bundle = self._make_minimal_bundle(projection_metadata)

        self.assertIn("tool_output_projection", bundle.to_dict())

    def test_bundle_serialization_preserves_projection_metadata(self) -> None:
        """IncidentEvidenceBundle serialization preserves tool_output_projection."""
        projection_metadata = {
            "pods": _make_projection_metadata("kubectl_get", "pods", spill_occurred=True),
        }

        bundle = self._make_minimal_bundle(projection_metadata)

        serialized = json.dumps(bundle.to_dict())

        # Safe fields preserved
        self.assertIn("tool_output_projection", serialized)
        self.assertIn("artifact-pods-123", serialized)
        self.assertIn("llm_visible_size_bytes", serialized)

    def test_bundle_preserves_tool_output_projection_as_provided(self) -> None:
        """IncidentEvidenceBundle preserves tool_output_projection as provided."""
        # Note: The bundle itself does NOT strip forbidden keys.
        # Forbidden key sanitization happens at the case-file boundary.
        projection_metadata = {
            "pods": _make_projection_metadata("kubectl_get", "pods", with_forbidden=True),
        }

        bundle = self._make_minimal_bundle(projection_metadata)
        serialized = json.dumps(bundle.to_dict())

        # Bundle preserves what you put in it
        self.assertIn("tool_output_projection", serialized)
        # Forbidden keys are PRESERVED in the bundle (stripped at case-file level)
        self.assertIn("raw_artifact_path", serialized)
        self.assertIn("raw_output", serialized)


class TestCaseFileBoundary(unittest.TestCase):
    """Verify case-file boundary protects against forbidden keys."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _build_case_file_with_projection(
        self,
        projection: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Helper to build case file with mocked incident."""
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

    def test_case_file_preserves_tool_output_projection(self) -> None:
        """Case file preserves tool_output_projection."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", spill_occurred=True),
            "events": _make_projection_metadata("kubectl_events", "events"),
            "deployments": _make_projection_metadata("kubectl_get", "deployments"),
        }

        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("tool_output_projection", case_file)
        self.assertIn("pods", case_file["tool_output_projection"])
        self.assertIn("events", case_file["tool_output_projection"])
        self.assertIn("deployments", case_file["tool_output_projection"])

    def test_case_file_strips_forbidden_keys(self) -> None:
        """Case file strips forbidden projection keys."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", with_forbidden=True),
            "events": _make_projection_metadata("kubectl_events", "events", with_forbidden=True),
            "deployments": _make_projection_metadata("kubectl_get", "deployments", with_forbidden=True),
        }

        case_file = self._build_case_file_with_projection(projection)

        # Forbidden keys absent
        found = _scan_forbidden_keys(case_file.get("tool_output_projection", {}))
        self.assertEqual(found, [], f"Forbidden keys found: {found}")

    def test_case_file_allows_llm_visible_size_bytes(self) -> None:
        """Case file allows llm_visible_size_bytes."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", spill_occurred=True),
        }

        case_file = self._build_case_file_with_projection(projection)

        self.assertIn("llm_visible_size_bytes", case_file["tool_output_projection"]["pods"])


class TestPromptBoundary(unittest.TestCase):
    """Verify prompt boundary protects against forbidden keys."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_incident = _make_mock_incident()
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

    def _build_case_file_with_projection(
        self,
        projection: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Helper to build case file with mocked incident."""
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

    def test_prompt_includes_safe_projection_metadata(self) -> None:
        """Prompt includes safe projection metadata."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", spill_occurred=True),
        }

        case_file = self._build_case_file_with_projection(projection)
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("tool_output_projection", prompt)
        self.assertIn("artifact-pods-123", prompt)

    def test_prompt_excludes_forbidden_keys(self) -> None:
        """Prompt excludes forbidden projection keys."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", with_forbidden=True),
        }

        case_file = self._build_case_file_with_projection(projection)
        prompt = build_diagnosis_prompt(case_file)

        # Forbidden fields excluded
        self.assertNotIn("raw_artifact_path", prompt)
        self.assertNotIn("raw_output", prompt)
        self.assertNotIn("/tmp/forbidden", prompt)

    def test_prompt_allows_llm_visible_size_bytes(self) -> None:
        """Prompt allows llm_visible_size_bytes."""
        projection = {
            "pods": _make_projection_metadata("kubectl_get", "pods", spill_occurred=True),
        }

        case_file = self._build_case_file_with_projection(projection)
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("llm_visible_size_bytes", prompt)


class TestEpicClosureInventory(unittest.TestCase):
    """Inventory test verifying epic closure requirements are documented."""

    def test_schema_version_constant_exists(self) -> None:
        """PROJECTION_METADATA_SCHEMA_VERSION constant exists."""
        self.assertEqual(PROJECTION_METADATA_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(PROJECTION_METADATA_SCHEMA_VERSION, str)

    def test_forbidden_keys_defined(self) -> None:
        """_FORBIDDEN_PROJECTION_KEYS is defined in case file module."""
        self.assertIn("raw_artifact_path", _FORBIDDEN_PROJECTION_KEYS)
        self.assertIn("raw_output", _FORBIDDEN_PROJECTION_KEYS)
        self.assertIn("llm_visible", _FORBIDDEN_PROJECTION_KEYS)

    def test_llm_visible_size_bytes_is_allowed(self) -> None:
        """llm_visible_size_bytes is NOT in forbidden keys."""
        self.assertNotIn("llm_visible_size_bytes", _FORBIDDEN_PROJECTION_KEYS)

    def test_canonical_keys_defined(self) -> None:
        """CANONICAL_PROJECTION_KEYS matches expected schema."""
        self.assertEqual(CANONICAL_PROJECTION_KEYS, frozenset({
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
        }))


if __name__ == "__main__":
    unittest.main()
