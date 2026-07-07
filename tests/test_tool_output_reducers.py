"""Unit tests for tool_output_reducers module.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-OUTPUT-REDUCERS01
"""
from __future__ import annotations

import json

from k8s_diag_agent.collect.tool_output_reducers import (
    REDUCER_SCHEMA_VERSION,
    JsonTreeReducer,
    ToolReducedOutput,
    get_default_reducer,
)

# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    def test_schema_version_is_defined(self) -> None:
        """Schema version should be a non-empty string."""
        assert REDUCER_SCHEMA_VERSION == "1.0"


# =============================================================================
# ToolReducedOutput Tests
# =============================================================================


class TestToolReducedOutput:
    def test_default_output_is_valid(self) -> None:
        """Default output should have valid structure."""
        output = ToolReducedOutput()
        assert output.schema_version == REDUCER_SCHEMA_VERSION
        assert output.counts["raw_items"] == 0
        assert output.counts["visible_items"] == 0
        assert output.counts["omitted_items"] == 0

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce serializable output."""
        output = ToolReducedOutput(
            source_tool="kubectl_get",
            reduction_policy="json_tree",
            counts={"raw_items": 10, "visible_items": 5, "omitted_items": 5},
            truncated=True,
            llm_visible={"text": "hello"},
        )
        d = output.to_dict()
        assert isinstance(d, dict)
        assert d["source_tool"] == "kubectl_get"
        assert d["truncated"] is True

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should reconstruct the same output."""
        original = ToolReducedOutput(
            source_tool="kubectl_logs",
            reduction_policy="json_tree",
            counts={"raw_items": 20, "visible_items": 15, "omitted_items": 5},
            truncated=True,
        )
        data = original.to_dict()
        reconstructed = ToolReducedOutput.from_dict(data)
        assert reconstructed.source_tool == original.source_tool
        assert reconstructed.counts == original.counts

    def test_is_error(self) -> None:
        """is_error should return True when error is set."""
        output = ToolReducedOutput(error="Something went wrong")
        assert output.is_error is True

        output_ok = ToolReducedOutput()
        assert output_ok.is_error is False

    def test_has_omissions(self) -> None:
        """has_omissions should return True when items were omitted."""
        output = ToolReducedOutput(counts={"raw_items": 10, "visible_items": 5, "omitted_items": 5})
        assert output.has_omissions is True

        output_no_omit = ToolReducedOutput(counts={"raw_items": 10, "visible_items": 10, "omitted_items": 0})
        assert output_no_omit.has_omissions is False

    def test_omission_ratio(self) -> None:
        """omission_ratio should calculate correctly."""
        output = ToolReducedOutput(counts={"raw_items": 10, "visible_items": 5, "omitted_items": 5})
        assert output.omission_ratio == 0.5

        output_zero = ToolReducedOutput(counts={"raw_items": 0, "visible_items": 0, "omitted_items": 0})
        assert output_zero.omission_ratio == 0.0


# =============================================================================
# JsonTreeReducer Tests
# =============================================================================


class TestJsonTreeReducer:
    def test_reduces_json_list(self) -> None:
        """Should reduce JSON list to max items."""
        reducer = JsonTreeReducer(max_items_per_array=3)
        data = {"items": [1, 2, 3, 4, 5]}
        result = reducer.reduce(data, max_bytes=1000, source_tool="test")

        assert result.source_tool == "test"
        assert result.counts["raw_items"] > result.counts["visible_items"]
        assert result.truncated is True

    def test_reduces_long_strings(self) -> None:
        """Should truncate long strings."""
        reducer = JsonTreeReducer(max_string_length=10)
        data = {"description": "This is a very long string that should be truncated"}
        result = reducer.reduce(data, max_bytes=1000, source_tool="test")

        assert result.llm_visible["data"]["description"].endswith("...")

    def test_handles_string_json(self) -> None:
        """Should parse JSON string input."""
        reducer = JsonTreeReducer()
        data = '{"key": "value", "count": 42}'
        result = reducer.reduce(data, max_bytes=1000, source_tool="test")

        assert result.llm_visible["data"]["key"] == "value"
        assert result.llm_visible["data"]["count"] == 42

    def test_handles_invalid_json(self) -> None:
        """Should fall back for invalid JSON."""
        reducer = JsonTreeReducer()
        data = "not valid json {"
        result = reducer.reduce(data, max_bytes=1000, source_tool="test")

        assert result.reduction_policy == "string_fallback"

    def test_respects_max_bytes(self) -> None:
        """Should truncate to fit max_bytes."""
        reducer = JsonTreeReducer()
        # Create large data
        data = {"large": "x" * 10000}
        max_bytes = 500
        result = reducer.reduce(data, max_bytes=max_bytes, source_tool="test")

        data_bytes = json.dumps(result.llm_visible["data"]).encode("utf-8")
        assert len(data_bytes) <= max_bytes


# =============================================================================
# get_default_reducer Tests
# =============================================================================


class TestGetDefaultReducer:
    def test_returns_json_reducer(self) -> None:
        """Should return JsonTreeReducer for 'json' type."""
        reducer = get_default_reducer("json")
        assert isinstance(reducer, JsonTreeReducer)

    def test_returns_json_for_unknown(self) -> None:
        """Should return JsonTreeReducer for unknown type."""
        reducer = get_default_reducer("unknown_type")
        assert isinstance(reducer, JsonTreeReducer)


# =============================================================================
# Integration Tests
# =============================================================================


class TestReducerIntegration:
    def test_kubectl_get_workflow(self) -> None:
        """Simulate kubectl get workflow: large list reduced."""
        # Simulate kubectl get pods output
        pods = [{"name": f"pod-{i}", "status": "Running"} for i in range(100)]
        data = {"apiVersion": "v1", "kind": "PodList", "items": pods}

        reducer = JsonTreeReducer(max_items_per_array=10)
        result = reducer.reduce(data, max_bytes=5000, source_tool="kubectl_get")

        assert result.source_tool == "kubectl_get"
        assert result.counts["raw_items"] > result.counts["visible_items"]
        assert result.counts["omitted_items"] > 0
        assert result.truncated is True
        # LLM visible should have structure
        assert "data" in result.llm_visible

    def test_error_result(self) -> None:
        """Reducer should handle errors gracefully."""
        reducer = JsonTreeReducer()

        # Pass invalid data that causes processing error
        result = reducer.reduce("invalid json {", max_bytes=1000, source_tool="test")

        # Should return a valid result, not raise
        assert result.source_tool == "test"
        assert result.reduction_policy in ("string_fallback", "json_tree")
