"""Tests for tool_projection_metadata contract.

Reference: ACT-K9B-HOLMESGPT-TOOL-PROJECTION-CONTRACT01

Required coverage:
1. metadata built from non-spill ToolOutputSpillResult has all required keys
2. metadata built from spill ToolOutputSpillResult has artifact reference fields
3. metadata built from error ToolOutputSpillResult preserves bounded error
4. to_dict/from_dict round-trip is stable
5. pods and events metadata use the same schema keys
6. metadata is JSON serializable
7. raw_size_bytes and llm_visible_size_bytes are non-negative integers
8. source_tool is required and non-empty
9. provenance is preserved
10. persisted metadata does not include raw tool output
"""

from __future__ import annotations

import json

import pytest

from k8s_diag_agent.collect.tool_projection_metadata import (
    PROJECTION_METADATA_SCHEMA_VERSION,
    ToolProjectionMetadata,
    build_tool_projection_metadata,
)
from k8s_diag_agent.collect.tool_spill_types import ToolOutputSpillResult


class TestBuildToolProjectionMetadata:
    """Tests for build_tool_projection_metadata function."""

    def test_non_spill_result_has_all_required_keys(self) -> None:
        """Metadata built from non-spill ToolOutputSpillResult has all required keys."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            provenance={"namespace": "default", "resource": "pods"},
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")

        # All required keys present
        assert metadata.schema_version == "1.0"
        assert metadata.source_tool == "kubectl_get"
        assert metadata.spill_occurred is False
        assert metadata.spill_reason is None
        assert metadata.raw_artifact_id is None
        assert metadata.raw_size_bytes == 1000
        assert metadata.llm_visible_size_bytes == 500
        assert metadata.content_type == "json"
        assert metadata.error is None
        assert metadata.provenance == {"namespace": "default", "resource": "pods"}

    def test_spill_result_has_artifact_reference_fields(self) -> None:
        """Metadata built from spill ToolOutputSpillResult has artifact reference fields."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-123",
            raw_artifact_path="/tmp/artifact-123.json",  # Internal path
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_events")

        # Artifact reference fields present
        assert metadata.spill_occurred is True
        assert metadata.spill_reason == "size_threshold"
        assert metadata.raw_artifact_id == "artifact-123"
        # raw_artifact_path is NOT included in metadata (per artifact path policy)
        assert metadata.raw_size_bytes == 50000
        assert metadata.llm_visible_size_bytes == 8000

    def test_error_result_preserves_bounded_error(self) -> None:
        """Metadata built from error ToolOutputSpillResult preserves bounded error."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            error="spill_required_but_no_artifact_dir",
            raw_size_bytes=50000,
            llm_visible_size_bytes=4096,
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")

        assert metadata.error == "spill_required_but_no_artifact_dir"
        assert metadata.spill_occurred is False

    def test_source_tool_required_and_non_empty(self) -> None:
        """source_tool is required and non-empty."""
        spill_result = ToolOutputSpillResult()

        # Valid source tool
        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")
        assert metadata.source_tool == "kubectl_get"

        # Empty string raises
        with pytest.raises(ValueError, match="source_tool must be a non-empty string"):
            build_tool_projection_metadata(spill_result, "")

        # None raises
        with pytest.raises(ValueError, match="source_tool must be a non-empty string"):
            build_tool_projection_metadata(spill_result, None)

    def test_non_negative_size_bytes(self) -> None:
        """raw_size_bytes and llm_visible_size_bytes are non-negative integers."""
        spill_result = ToolOutputSpillResult(
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
        )

        # Valid non-negative
        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")
        assert metadata.raw_size_bytes == 1000
        assert metadata.llm_visible_size_bytes == 500

        # Zero is valid
        spill_result_zero = ToolOutputSpillResult(raw_size_bytes=0, llm_visible_size_bytes=0)
        metadata_zero = build_tool_projection_metadata(spill_result_zero, "kubectl_get")
        assert metadata_zero.raw_size_bytes == 0
        assert metadata_zero.llm_visible_size_bytes == 0


class TestToolProjectionMetadataSchema:
    """Tests for ToolProjectionMetadata schema."""

    def test_required_keys(self) -> None:
        """Metadata has all required schema keys."""
        metadata = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=False,
            spill_reason=None,
            raw_artifact_id=None,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            error=None,
            provenance={},
        )

        # Verify all fields are accessible
        assert metadata.schema_version
        assert metadata.source_tool
        assert isinstance(metadata.spill_occurred, bool)
        assert metadata.spill_reason is None or isinstance(metadata.spill_reason, str)
        assert metadata.raw_artifact_id is None or isinstance(metadata.raw_artifact_id, str)
        assert isinstance(metadata.raw_size_bytes, int)
        assert isinstance(metadata.llm_visible_size_bytes, int)
        assert isinstance(metadata.content_type, str)
        assert metadata.error is None or isinstance(metadata.error, str)
        assert isinstance(metadata.provenance, dict)

    def test_raw_artifact_path_not_in_schema(self) -> None:
        """raw_artifact_path is NOT part of the schema."""
        metadata = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-123",
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
            error=None,
            provenance={},
        )

        # raw_artifact_path should NOT be accessible
        assert not hasattr(metadata, "raw_artifact_path") or getattr(metadata, "raw_artifact_path", None) is None

        # to_dict should NOT include raw_artifact_path
        d = metadata.to_dict()
        assert "raw_artifact_path" not in d

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict round-trip is stable."""
        original = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-123",
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
            error=None,
            provenance={"namespace": "default", "resource": "pods"},
        )

        # Round-trip
        d = original.to_dict()
        restored = ToolProjectionMetadata.from_dict(d)

        assert restored.schema_version == original.schema_version
        assert restored.source_tool == original.source_tool
        assert restored.spill_occurred == original.spill_occurred
        assert restored.spill_reason == original.spill_reason
        assert restored.raw_artifact_id == original.raw_artifact_id
        assert restored.raw_size_bytes == original.raw_size_bytes
        assert restored.llm_visible_size_bytes == original.llm_visible_size_bytes
        assert restored.content_type == original.content_type
        assert restored.error == original.error
        assert restored.provenance == original.provenance

    def test_json_serializable(self) -> None:
        """Metadata is JSON serializable."""
        metadata = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=False,
            spill_reason=None,
            raw_artifact_id=None,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            error=None,
            provenance={"namespace": "default"},
        )

        # Should not raise
        d = metadata.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)

        assert restored["schema_version"] == "1.0"
        assert restored["source_tool"] == "kubectl_get"

    def test_provenance_preserved(self) -> None:
        """Provenance is preserved through to_dict/from_dict."""
        original_provenance = {
            "namespace": "default",
            "resource": "pods",
            "collector_version": "1.0",
            "nested": {"key": "value"},
        }

        metadata = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=False,
            spill_reason=None,
            raw_artifact_id=None,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            error=None,
            provenance=original_provenance,
        )

        d = metadata.to_dict()
        assert d["provenance"] == original_provenance

        restored = ToolProjectionMetadata.from_dict(d)
        assert restored.provenance == original_provenance

    def test_no_raw_tool_output_in_metadata(self) -> None:
        """Persisted metadata does not include raw tool output."""
        metadata = ToolProjectionMetadata(
            schema_version="1.0",
            source_tool="kubectl_get",
            spill_occurred=False,
            spill_reason=None,
            raw_artifact_id=None,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            error=None,
            provenance={},
        )

        d = metadata.to_dict()

        # Should NOT contain raw output fields
        assert "raw_output" not in d
        assert "llm_visible" not in d
        assert "content" not in d
        assert "data" not in d

        # Should only contain metadata fields
        expected_keys = {
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
        }
        assert set(d.keys()) == expected_keys


class TestPodsEventsSchemaParity:
    """Tests for pods/events metadata schema parity."""

    def test_pods_and_events_have_same_schema_keys(self) -> None:
        """Pods and events metadata use the same schema keys."""
        # Simulate pods collector metadata
        pods_spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            provenance={"namespace": "default", "resource": "pods"},
        )
        pods_metadata = build_tool_projection_metadata(pods_spill_result, "kubectl_get")
        pods_keys = set(pods_metadata.to_dict().keys())

        # Simulate events collector metadata
        events_spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=800,
            llm_visible_size_bytes=400,
            content_type="json",
            provenance={"namespace": "default", "resource": "events"},
        )
        events_metadata = build_tool_projection_metadata(events_spill_result, "kubectl_events")
        events_keys = set(events_metadata.to_dict().keys())

        # Same schema keys
        assert pods_keys == events_keys

        # Both have expected keys
        expected_keys = {
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
        }
        assert pods_keys == expected_keys
        assert events_keys == expected_keys


class TestSchemaVersion:
    """Tests for schema version."""

    def test_schema_version_is_documented(self) -> None:
        """Schema version is a documented constant."""
        assert PROJECTION_METADATA_SCHEMA_VERSION == "1.0"
        assert isinstance(PROJECTION_METADATA_SCHEMA_VERSION, str)

    def test_schema_version_in_metadata(self) -> None:
        """Schema version is included in metadata."""
        metadata = ToolProjectionMetadata(
            schema_version=PROJECTION_METADATA_SCHEMA_VERSION,
            source_tool="kubectl_get",
            spill_occurred=False,
            spill_reason=None,
            raw_artifact_id=None,
            raw_size_bytes=0,
            llm_visible_size_bytes=0,
            content_type="json",
            error=None,
            provenance={},
        )

        assert metadata.schema_version == PROJECTION_METADATA_SCHEMA_VERSION
        assert metadata.to_dict()["schema_version"] == PROJECTION_METADATA_SCHEMA_VERSION


class TestArtifactPathPolicy:
    """Tests for artifact path policy enforcement."""

    def test_spill_result_with_path_does_not_leak_path(self) -> None:
        """Spill result with raw_artifact_path does not leak path to metadata."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-456",
            raw_artifact_path="/var/folders/tmp/xyz/artifact-456.json",  # Local path
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")

        # Path is not in metadata
        d = metadata.to_dict()
        assert "raw_artifact_path" not in d

        # Artifact ID is preserved
        assert metadata.raw_artifact_id == "artifact-456"

    def test_spill_result_without_path_still_works(self) -> None:
        """Spill result without raw_artifact_path still produces valid metadata."""
        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-789",
            raw_artifact_path=None,  # Explicitly None
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
        )

        metadata = build_tool_projection_metadata(spill_result, "kubectl_get")

        assert metadata.spill_occurred is True
        assert metadata.raw_artifact_id == "artifact-789"
        # raw_artifact_path is not part of the schema, so we verify it's absent
        assert "raw_artifact_path" not in metadata.to_dict()


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing _build_projection_metadata."""

    def test_deprecated_wrapper_returns_dict(self) -> None:
        """_build_projection_metadata returns dict for backward compatibility."""
        from k8s_diag_agent.collect.tool_projection_metadata import _build_projection_metadata

        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=False,
            raw_size_bytes=1000,
            llm_visible_size_bytes=500,
            content_type="json",
            provenance={"namespace": "default"},
        )

        # Should return dict (backward compatible)
        metadata_dict = _build_projection_metadata(spill_result, "kubectl_get")
        assert isinstance(metadata_dict, dict)
        assert metadata_dict["source_tool"] == "kubectl_get"
        assert "schema_version" in metadata_dict

    def test_deprecated_wrapper_does_not_include_raw_artifact_path(self) -> None:
        """_build_projection_metadata does not include raw_artifact_path."""
        from k8s_diag_agent.collect.tool_projection_metadata import _build_projection_metadata

        spill_result = ToolOutputSpillResult(
            schema_version="1.0",
            spill_occurred=True,
            spill_reason="size_threshold",
            raw_artifact_id="artifact-123",
            raw_artifact_path="/tmp/artifact-123.json",
            raw_size_bytes=50000,
            llm_visible_size_bytes=8000,
            content_type="json",
        )

        metadata_dict = _build_projection_metadata(spill_result, "kubectl_get")

        # raw_artifact_path should NOT be in the dict
        assert "raw_artifact_path" not in metadata_dict
        # But raw_artifact_id should be
        assert metadata_dict["raw_artifact_id"] == "artifact-123"
