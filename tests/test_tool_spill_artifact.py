"""Unit tests for tool_spill_artifact module.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-SPILL-ARTIFACT01
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from k8s_diag_agent.collect.tool_budget_contract import (
    KUBECTL_GET_BUDGET,
    KUBECTL_LOGS_BUDGET,
    ToolBudget,
)
from k8s_diag_agent.collect.tool_spill_artifact import (
    SPILL_SCHEMA_VERSION,
    RawToolOutputArtifact,
    SpillReason,
    ToolOutputContentType,
    ToolOutputSpillResult,
    compute_size_bytes,
    create_tool_output_result,
    detect_content_type,
    should_spill,
    spill_tool_output,
    write_raw_tool_artifact,
)

# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert SPILL_SCHEMA_VERSION == "1.0"


# =============================================================================
# ToolOutputSpillResult Tests
# =============================================================================


class TestToolOutputSpillResult:
    def test_default_result_is_valid(self) -> None:
        """Default result should have valid structure."""
        result = ToolOutputSpillResult()
        assert result.schema_version == SPILL_SCHEMA_VERSION
        assert result.spill_occurred is False
        assert result.raw_artifact_id is None
        assert result.has_raw_artifact is False

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        result = ToolOutputSpillResult(
            spill_occurred=True,
            spill_reason=SpillReason.SIZE_THRESHOLD.value,
            raw_artifact_id="test-artifact-id",
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            llm_visible={"text": "sample"},
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["spill_occurred"] is True
        assert d["spill_reason"] == SpillReason.SIZE_THRESHOLD.value

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should reconstruct the same result."""
        original = ToolOutputSpillResult(
            spill_occurred=True,
            spill_reason=SpillReason.CONTENT_TYPE.value,
            raw_artifact_id="test-id",
            raw_size_bytes=2000,
            llm_visible_size_bytes=800,
        )
        data = original.to_dict()
        reconstructed = ToolOutputSpillResult.from_dict(data)
        assert reconstructed.spill_occurred == original.spill_occurred
        assert reconstructed.spill_reason == original.spill_reason

    def test_has_raw_artifact(self) -> None:
        """has_raw_artifact should return True when artifact exists."""
        result = ToolOutputSpillResult(raw_artifact_id="some-id")
        assert result.has_raw_artifact is True

        result_no_artifact = ToolOutputSpillResult()
        assert result_no_artifact.has_raw_artifact is False

    def test_spill_ratio(self) -> None:
        """spill_ratio should calculate correctly."""
        result = ToolOutputSpillResult(raw_size_bytes=1000, projected_size_bytes=500)
        assert result.spill_ratio == 2.0

        result_zero = ToolOutputSpillResult(projected_size_bytes=0)
        assert result_zero.spill_ratio == 0.0


# =============================================================================
# RawToolOutputArtifact Tests
# =============================================================================


class TestRawToolOutputArtifact:
    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        artifact = RawToolOutputArtifact(
            artifact_id="test-id",
            source_tool="kubectl_get",
            content_type=ToolOutputContentType.JSON.value,
            raw_content='{"key": "value"}',
            size_bytes=17,
            timestamp="2024-01-01T00:00:00Z",
        )
        d = artifact.to_dict()
        assert isinstance(d, dict)
        assert d["artifact_id"] == "test-id"
        assert d["source_tool"] == "kubectl_get"

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should reconstruct the same artifact."""
        original = RawToolOutputArtifact(
            artifact_id="test-id",
            source_tool="kubectl_logs",
            content_type=ToolOutputContentType.LOG.value,
            raw_content="log line 1\nlog line 2",
            size_bytes=28,
            timestamp="2024-01-01T00:00:00Z",
        )
        data = original.to_dict()
        reconstructed = RawToolOutputArtifact.from_dict(data)
        assert reconstructed.artifact_id == original.artifact_id
        assert reconstructed.content_type == original.content_type


# =============================================================================
# Content Type Detection Tests
# =============================================================================


class TestDetectContentType:
    def test_detects_json_dict(self) -> None:
        """Should detect JSON dict."""
        result = detect_content_type({"key": "value"})
        assert result == ToolOutputContentType.JSON

    def test_detects_kubernetes_manifest(self) -> None:
        """Should detect Kubernetes manifest."""
        result = detect_content_type({"apiVersion": "v1", "kind": "Pod"})
        assert result == ToolOutputContentType.MANIFEST

    def test_detects_metrics(self) -> None:
        """Should detect metrics output."""
        result = detect_content_type({"metrics": [{"name": "cpu"}]})
        assert result == ToolOutputContentType.METRICS

    def test_detects_event_pattern(self) -> None:
        """Should detect event content in text."""
        result = detect_content_type("LastSeen: 2024-01-01T00:00:00Z event detected")
        assert result == ToolOutputContentType.EVENT

    def test_detects_log_pattern(self) -> None:
        """Should detect log content."""
        result = detect_content_type("2024-01-01 INFO: Application started\nlevel=debug message")
        assert result == ToolOutputContentType.LOG

    def test_detects_manifest_yaml(self) -> None:
        """Should detect YAML manifest markers."""
        result = detect_content_type("---\napiVersion: v1\nkind: ConfigMap")
        assert result == ToolOutputContentType.MANIFEST

    def test_detects_json_string(self) -> None:
        """Should detect JSON string."""
        result = detect_content_type('{"key": "value", "count": 42}')
        assert result == ToolOutputContentType.JSON

    def test_detects_text_fallback(self) -> None:
        """Should detect plain text."""
        result = detect_content_type("This is plain text output")
        assert result == ToolOutputContentType.TEXT

    def test_handles_empty_string(self) -> None:
        """Should handle empty string."""
        result = detect_content_type("")
        assert result == ToolOutputContentType.UNKNOWN


# =============================================================================
# Compute Size Tests
# =============================================================================


class TestComputeSizeBytes:
    def test_computes_string_size(self) -> None:
        """Should compute string size in bytes."""
        size = compute_size_bytes("hello")
        assert size == 5

    def test_computes_unicode_size(self) -> None:
        """Should compute unicode string size."""
        size = compute_size_bytes("héllo")
        assert size == 6  # UTF-8 encoding

    def test_computes_dict_size(self) -> None:
        """Should compute dict size in bytes."""
        size = compute_size_bytes({"key": "value"})
        expected = len(json.dumps({"key": "value"}).encode("utf-8"))
        assert size == expected


# =============================================================================
# Should Spill Tests
# =============================================================================


class TestShouldSpill:
    def test_spills_over_threshold(self) -> None:
        """Should spill when raw size exceeds threshold."""
        budget = ToolBudget(artifact_spill_threshold_bytes=100)
        result, reason = should_spill(200, budget, ToolOutputContentType.TEXT)
        assert result is True
        assert reason == SpillReason.SIZE_THRESHOLD

    def test_no_spill_under_threshold(self) -> None:
        """Should not spill when raw size is under threshold."""
        budget = ToolBudget(artifact_spill_threshold_bytes=100)
        result, reason = should_spill(50, budget, ToolOutputContentType.TEXT)
        assert result is False
        assert reason is None

    def test_spills_manifest_early(self) -> None:
        """Should spill manifest content type earlier."""
        budget = ToolBudget(artifact_spill_threshold_bytes=100)
        # 60 is under 100 but over 50 (half of 100)
        result, reason = should_spill(60, budget, ToolOutputContentType.MANIFEST)
        assert result is True
        assert reason == SpillReason.CONTENT_TYPE

    def test_no_spill_manifest_small(self) -> None:
        """Should not spill small manifest content."""
        budget = ToolBudget(artifact_spill_threshold_bytes=100)
        result, reason = should_spill(30, budget, ToolOutputContentType.MANIFEST)
        assert result is False


# =============================================================================
# Write Artifact Tests
# =============================================================================


class TestWriteRawToolArtifact:
    def test_writes_artifact(self) -> None:
        """Should write artifact to directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            artifact, path = write_raw_tool_artifact(
                artifact_dir=artifact_dir,
                source_tool="kubectl_get",
                raw_content="test content",
                content_type=ToolOutputContentType.TEXT,
            )

            assert artifact.artifact_id is not None
            assert artifact.source_tool == "kubectl_get"
            assert artifact.raw_content == "test content"
            assert path.exists()

            # Verify artifact can be read back
            data = json.loads(path.read_text())
            assert data["source_tool"] == "kubectl_get"


# =============================================================================
# Spill Tool Output Tests
# =============================================================================


class TestSpillToolOutput:
    def test_small_output_no_spill(self) -> None:
        """Should not spill small outputs."""
        output = "small output"
        result = spill_tool_output(
            raw_output=output,
            budget=KUBECTL_GET_BUDGET,
            source_tool="kubectl_get",
        )

        assert result.spill_occurred is False
        assert result.raw_size_bytes == len(output.encode("utf-8"))
        assert result.error is None

    def test_large_output_spills(self) -> None:
        """Should spill large outputs when directory provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create output that exceeds spill threshold (64KB for KUBECTL_LOGS_BUDGET)
            large_output = "x" * 70000  # 70KB - exceeds 64KB threshold

            result = spill_tool_output(
                raw_output=large_output,
                budget=KUBECTL_LOGS_BUDGET,
                source_tool="kubectl_logs",
                artifact_dir=artifact_dir,
            )

            assert result.spill_occurred is True
            assert result.spill_reason == SpillReason.SIZE_THRESHOLD.value
            assert result.raw_artifact_id is not None
            assert result.raw_size_bytes == 70000
            assert result.has_raw_artifact is True

            # Verify artifact file exists
            artifact_path = Path(result.raw_artifact_path)
            assert artifact_path.exists()

    def test_large_output_without_dir_returns_error(self) -> None:
        """Should return error when spill needed but no directory."""
        # Use output that exceeds spill threshold (64KB for KUBECTL_LOGS_BUDGET)
        large_output = "x" * 70000  # 70KB

        result = spill_tool_output(
            raw_output=large_output,
            budget=KUBECTL_LOGS_BUDGET,
            source_tool="kubectl_logs",
            artifact_dir=None,  # No directory
        )

        assert result.spill_occurred is False
        assert "spill_required_but_no_artifact_dir" in (result.error or "")

    def test_handles_json_dict(self) -> None:
        """Should handle JSON dict input."""
        output = {"items": [{"name": f"item-{i}"} for i in range(10)]}
        result = spill_tool_output(
            raw_output=output,
            budget=KUBECTL_GET_BUDGET,
            source_tool="kubectl_get",
        )

        assert result.spill_occurred is False
        assert result.content_type == ToolOutputContentType.JSON.value

    def test_handles_kubernetes_manifest(self) -> None:
        """Should handle Kubernetes manifest input."""
        output = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "test"}}
        result = spill_tool_output(
            raw_output=output,
            budget=KUBECTL_GET_BUDGET,
            source_tool="kubectl_describe",
        )

        assert result.content_type == ToolOutputContentType.MANIFEST.value

    def test_provenance_tracking(self) -> None:
        """Should track provenance."""
        output = "test output"
        custom_provenance = {"run_id": "test-run", "cluster": "prod"}
        result = spill_tool_output(
            raw_output=output,
            budget=KUBECTL_GET_BUDGET,
            source_tool="kubectl_get",
            provenance=custom_provenance,
        )

        assert result.provenance["run_id"] == "test-run"
        assert result.provenance["source_tool"] == "kubectl_get"

    def test_reducer_applied(self) -> None:
        """Should apply reducer to output."""
        # Create output that exceeds llm_visible_bytes
        lines = ["log line " + "x" * 100 for _ in range(100)]
        output = "\n".join(lines)

        result = spill_tool_output(
            raw_output=output,
            budget=KUBECTL_LOGS_BUDGET,
            source_tool="kubectl_logs",
            reducer_type="line",
        )

        # Should have reduced the output
        assert result.llm_visible_size_bytes <= KUBECTL_LOGS_BUDGET.llm_visible_bytes


# =============================================================================
# Integration Helper Tests
# =============================================================================


class TestCreateToolOutputResult:
    def test_creates_combined_result(self) -> None:
        """Should create both spill result and reduced output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            output = "test output"

            spill_result, reduced_output = create_tool_output_result(
                raw_output=output,
                budget=KUBECTL_GET_BUDGET,
                source_tool="kubectl_get",
                artifact_dir=artifact_dir,
            )

            # Check provenance for source_tool (ToolOutputSpillResult doesn't have source_tool field directly)
            assert spill_result.provenance["source_tool"] == "kubectl_get"
            assert reduced_output.source_tool == "kubectl_get"
            assert reduced_output.schema_version == SPILL_SCHEMA_VERSION

    def test_large_output_spill_and_reduced(self) -> None:
        """Should spill large output and return reduced version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Use output that exceeds spill threshold (64KB for KUBECTL_LOGS_BUDGET)
            large_output = "x" * 70000  # 70KB

            spill_result, reduced_output = create_tool_output_result(
                raw_output=large_output,
                budget=KUBECTL_LOGS_BUDGET,
                source_tool="kubectl_logs",
                artifact_dir=artifact_dir,
            )

            assert spill_result.spill_occurred is True
            assert spill_result.has_raw_artifact is True
            assert reduced_output.raw_artifact_id is not None
            assert reduced_output.truncated is True
