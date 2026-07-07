"""Unit tests for tool_spill_types module.

Tests schema types and enums for spill artifacts.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations

from k8s_diag_agent.collect.tool_spill_types import (
    SPILL_SCHEMA_VERSION,
    RawToolOutputArtifact,
    SpillReason,
    ToolOutputContentType,
    ToolOutputSpillResult,
)


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert SPILL_SCHEMA_VERSION == "1.0"


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


class TestSpillReason:
    def test_llm_visible_exceeded_member_has_stable_value(self) -> None:
        """LLM_VISIBLE_EXCEEDED should have stable serialized value."""
        assert SpillReason.LLM_VISIBLE_EXCEEDED.value == "llm_visible_exceeded"

    def test_deprecated_llmr_visible_exceeded_alias_is_stable(self) -> None:
        """Deprecated LLMR_VISIBLE_EXCEEDED alias should have stable value."""
        assert SpillReason.LLMR_VISIBLE_EXCEEDED.value == "llm_visible_exceeded"
        assert SpillReason.LLMR_VISIBLE_EXCEEDED is SpillReason.LLM_VISIBLE_EXCEEDED


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
