"""Unit tests for tool_spill_content module.

Tests content type detection and spill decision logic.
Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-SPLIT01
"""
from __future__ import annotations

import json

from k8s_diag_agent.collect.tool_budget_types import ToolBudget
from k8s_diag_agent.collect.tool_spill_content import (
    compute_size_bytes,
    detect_content_type,
    should_spill,
)
from k8s_diag_agent.collect.tool_spill_types import SpillReason, ToolOutputContentType


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
