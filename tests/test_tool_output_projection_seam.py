"""Unit tests for tool_output_projection production seam.

Tests the integration of budget/spill infrastructure into incident_collectors.

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-PRODUCTION-SEAM01
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from k8s_diag_agent.collect.incident_collectors import (
    _build_projection_metadata,
    collect_pods,
)
from k8s_diag_agent.collect.tool_budget_defaults import KUBECTL_GET_BUDGET
from k8s_diag_agent.collect.tool_budget_registry import get_tool_budget_registry
from k8s_diag_agent.collect.tool_budget_types import ToolBudget
from k8s_diag_agent.collect.tool_output_projection import (
    _UNKNOWN_TOOL_BUDGET,
    project_read_only_tool_output,
)
from k8s_diag_agent.collect.tool_spill_types import ToolOutputSpillResult


class TestProjectReadOnlyToolOutput:
    """Tests for project_read_only_tool_output function."""

    def test_small_output_does_not_spill(self) -> None:
        """Small read-only output does not spill and remains bounded."""
        small_payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [
                {
                    "metadata": {"name": "test-pod", "namespace": "default"},
                    "status": {"phase": "Running"},
                }
            ],
        }

        result = project_read_only_tool_output(
            source_tool="kubectl_get",
            raw_output=small_payload,
            artifact_dir=None,
        )

        assert result.spill_occurred is False
        assert result.error is None
        assert result.raw_size_bytes > 0
        assert result.llm_visible_size_bytes > 0
        # Bounded by llm_visible_bytes
        assert result.llm_visible_size_bytes <= KUBECTL_GET_BUDGET.llm_visible_bytes

    def test_large_output_spills_to_artifact(self) -> None:
        """Large read-only output spills to artifact when artifact_dir provided."""
        # Create large payload that exceeds threshold
        items = []
        for i in range(200):
            items.append({
                "metadata": {
                    "name": f"test-pod-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 10,
                },
                "status": {"phase": "Running"},
                "spec": {"containers": [{"name": "main", "image": f"image-{i}"}]},
            })
        large_payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": items,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            result = project_read_only_tool_output(
                source_tool="kubectl_get",
                raw_output=large_payload,
                artifact_dir=artifact_dir,
            )

            assert result.spill_occurred is True
            assert result.raw_artifact_id is not None
            assert result.raw_artifact_path is not None
            assert result.spill_reason is not None
            # Raw artifact should be written
            assert Path(result.raw_artifact_path).exists()

    def test_large_output_without_artifact_dir_returns_bounded_error(self) -> None:
        """Large output without artifact_dir returns explicit bounded error."""
        # Create large payload that would need to spill
        items = []
        for i in range(200):
            items.append({
                "metadata": {
                    "name": f"test-pod-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 10,
                },
                "status": {"phase": "Running"},
            })
        large_payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": items,
        }

        # No artifact_dir - spill required but impossible
        result = project_read_only_tool_output(
            source_tool="kubectl_get",
            raw_output=large_payload,
            artifact_dir=None,  # Explicitly no artifact dir
        )

        assert result.spill_occurred is False
        assert result.error is not None
        assert "spill_required_but_no_artifact_dir" in result.error
        # Raw size is preserved for reference
        assert result.raw_size_bytes > KUBECTL_GET_BUDGET.artifact_spill_threshold_bytes
        # LLM visible is significantly reduced from raw (reducer limits items/strings)
        assert result.llm_visible_size_bytes < result.raw_size_bytes

    def test_unknown_tool_budget_fails_closed(self) -> None:
        """Unknown tool budget uses documented safe default."""
        unknown_payload = {"data": "test"}

        result = project_read_only_tool_output(
            source_tool="completely_unknown_tool_xyz",
            raw_output=unknown_payload,
            artifact_dir=None,
        )

        # Should not fail, uses safe default
        assert result.error is None or "reduction_failed" not in (result.error or "")
        # Provenance should indicate safe default was used
        assert result.provenance.get("budget_source") == "unknown_tool_safe_default"
        # LLM visible is bounded by safe default budget
        assert result.llm_visible_size_bytes <= _UNKNOWN_TOOL_BUDGET.llm_visible_bytes

    def test_explicit_budget_wins_over_registry(self) -> None:
        """Explicit budget takes precedence over registry lookup."""
        explicit_budget = ToolBudget(
            timeout_seconds=10,
            stdout_bytes=4096,
            stderr_bytes=1024,
            llm_visible_bytes=2048,  # Smaller than default
            artifact_spill_threshold_bytes=4096,
            approval_class="read_only",
            schema_name="custom_budget",
        )

        result = project_read_only_tool_output(
            source_tool="kubectl_get",  # Has registry entry
            raw_output={"data": "test"},
            budget=explicit_budget,
            artifact_dir=None,
        )

        # Provenance should show explicit budget was used
        assert result.provenance.get("budget_source") == "explicit"
        # Should be bounded by explicit budget
        assert result.llm_visible_size_bytes <= explicit_budget.llm_visible_bytes

    def test_llm_visible_significantly_reduced(self) -> None:
        """LLM-visible payload is significantly reduced from raw size."""
        # Very large payload
        items = []
        for i in range(500):
            items.append({
                "metadata": {
                    "name": f"test-pod-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 20,
                    "labels": {f"label-{j}": f"value-{j}" for j in range(10)},
                },
                "status": {"phase": "Running"},
                "spec": {"containers": [{"name": "main", "image": f"image-{i}"}]},
            })
        huge_payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": items,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = project_read_only_tool_output(
                source_tool="kubectl_get",
                raw_output=huge_payload,
                artifact_dir=Path(tmpdir),
            )

            # LLM visible is significantly reduced (spill occurred + reducer limited items)
            assert result.spill_occurred is True
            assert result.llm_visible_size_bytes < result.raw_size_bytes
            # Should be much smaller than the raw size
            assert result.llm_visible_size_bytes < result.raw_size_bytes // 5

    def test_raw_artifact_contains_budget_snapshot(self) -> None:
        """Raw artifact contains budget snapshot and source_tool."""
        payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [{"metadata": {"name": "test"}}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            result = project_read_only_tool_output(
                source_tool="kubectl_get",
                raw_output=payload,
                artifact_dir=artifact_dir,
            )

            if result.has_raw_artifact:
                artifact_path = Path(result.raw_artifact_path)
                assert artifact_path.exists()

                with open(artifact_path) as f:
                    artifact_data = json.load(f)

                assert artifact_data["source_tool"] == "kubectl_get"
                assert artifact_data["budget_snapshot"] is not None
                assert artifact_data["budget_snapshot"]["llm_visible_bytes"] == KUBECTL_GET_BUDGET.llm_visible_bytes

    def test_provenance_includes_required_fields(self) -> None:
        """Provenance includes source_tool, content_type, raw size, and spill schema version."""
        payload = {
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [{"metadata": {"name": "test"}}],
        }

        result = project_read_only_tool_output(
            source_tool="kubectl_get",
            raw_output=payload,
            artifact_dir=None,
        )

        prov = result.provenance
        assert "source_tool" in prov
        assert prov["source_tool"] == "kubectl_get"
        assert "content_type" in prov
        assert "spill_schema_version" in prov
        assert result.raw_size_bytes > 0


class TestBuildProjectionMetadata:
    """Tests for _build_projection_metadata helper."""

    def test_builds_complete_metadata(self) -> None:
        """Metadata contains all required fields."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            provenance={"source_tool": "test"},
        )

        metadata = _build_projection_metadata(spill_result, "kubectl_get")

        assert metadata["source_tool"] == "kubectl_get"
        assert metadata["schema_version"] == "1.0"
        assert metadata["spill_occurred"] is False
        assert metadata["raw_size_bytes"] == 1000
        assert metadata["llm_visible_size_bytes"] == 500
        assert metadata["content_type"] == "json"
        assert "provenance" in metadata

    def test_handles_spill_result(self) -> None:
        """Handles spill_occurred=True case."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-123",
            raw_artifact_path="/tmp/artifact.json",
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
        )

        metadata = _build_projection_metadata(spill_result, "kubectl_get")

        assert metadata["spill_occurred"] is True
        assert metadata["spill_reason"] == "size_threshold"
        assert metadata["raw_artifact_id"] == "artifact-123"
        assert metadata["raw_artifact_path"] == "/tmp/artifact.json"

    def test_handles_error_result(self) -> None:
        """Handles error in spill result."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            error="spill_required_but_no_artifact_dir",
            raw_size_bytes=50000,
        )

        metadata = _build_projection_metadata(spill_result, "kubectl_get")

        assert metadata["error"] == "spill_required_but_no_artifact_dir"


class TestToolBudgetRegistryFacade:
    """Tests that facade imports still work."""

    def test_kubectl_get_budget_available(self) -> None:
        """kubectl_get budget is available from registry."""
        registry = get_tool_budget_registry()
        budget = registry.get("kubectl_get")
        assert budget is not None
        assert budget.llm_visible_bytes == KUBECTL_GET_BUDGET.llm_visible_bytes

    def test_unknown_tool_returns_none(self) -> None:
        """Unknown tool returns None from registry."""
        registry = get_tool_budget_registry()
        budget = registry.get("definitely_not_a_real_tool")
        assert budget is None


class TestBackwardCompatibility:
    """Tests that existing functionality is preserved."""

    def test_collect_pods_returns_three_tuple(self) -> None:
        """collect_pods returns (pods, errors, projection_metadata)."""
        # Mock kubectl to avoid actual K8s calls
        import unittest.mock

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "PodList",
            "items": [
                {
                    "metadata": {
                        "name": "test-pod",
                        "namespace": "default",
                        "uid": "test-uid",
                    },
                    "status": {"phase": "Running"},
                }
            ],
        })

        with unittest.mock.patch(
            "k8s_diag_agent.collect.incident_collectors.kubectl",
            return_value=mock_output,
        ):
            pods, errors, metadata = collect_pods("default", None)

            # Same semantic output as before
            assert len(pods) == 1
            assert pods[0].name == "test-pod"
            assert errors == []

            # New projection metadata
            assert isinstance(metadata, dict)
            assert "source_tool" in metadata
            assert metadata["source_tool"] == "kubectl_get"

    def test_collect_pods_with_artifact_dir(self) -> None:
        """collect_pods with artifact_dir creates spill when needed."""
        import unittest.mock

        # Large payload that should trigger spill
        items = []
        for i in range(100):
            items.append({
                "metadata": {
                    "name": f"test-pod-{i}",
                    "namespace": "default",
                    "uid": f"uid-{i}" * 10,
                },
                "status": {"phase": "Running"},
            })

        mock_output = json.dumps({
            "apiVersion": "v1",
            "kind": "PodList",
            "items": items,
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            with unittest.mock.patch(
                "k8s_diag_agent.collect.incident_collectors.kubectl",
                return_value=mock_output,
            ):
                pods, errors, metadata = collect_pods("default", None, artifact_dir)

                # Should have pods
                assert len(pods) == 100
                assert errors == []

                # Should have spill metadata
                if metadata.get("spill_occurred"):
                    assert metadata.get("raw_artifact_id") is not None
                    assert metadata.get("raw_size_bytes") > metadata.get("llm_visible_size_bytes")
