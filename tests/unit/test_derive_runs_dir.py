"""Tests for _derive_content_index_runs_dir function in loop_scheduler_run.py.

This function is critical for correctly deriving the content index runs directory
from HEALTH_RUNS_DIR, handling the common case where HEALTH_RUNS_DIR=/app/runs/health.
"""

from __future__ import annotations

from pathlib import Path

# Import the function from the module
from k8s_diag_agent.health.loop_scheduler_run import _derive_content_index_runs_dir


class TestDeriveContentIndexRunsDir:
    """Test suite for _derive_content_index_runs_dir function."""

    def test_unset_returns_default(self) -> None:
        """When HEALTH_RUNS_DIR is unset, should return /app/runs."""
        result = _derive_content_index_runs_dir(None)
        assert result == Path("/app/runs")

    def test_empty_string_returns_default(self) -> None:
        """When HEALTH_RUNS_DIR is empty string, should return /app/runs."""
        result = _derive_content_index_runs_dir("")
        assert result == Path("/app/runs")

    def test_health_suffix_derives_parent(self) -> None:
        """When HEALTH_RUNS_DIR ends with /health, should return parent directory."""
        result = _derive_content_index_runs_dir("/app/runs/health")
        assert result == Path("/app/runs")

    def test_health_suffix_with_trailing_slash(self) -> None:
        """When HEALTH_RUNS_DIR ends with /health/, should return parent directory."""
        result = _derive_content_index_runs_dir("/app/runs/health/")
        assert result == Path("/app/runs")

    def test_custom_health_suffix_derives_parent(self) -> None:
        """When custom path ends with /health, should return parent directory."""
        result = _derive_content_index_runs_dir("/data/runs/health")
        assert result == Path("/data/runs")

    def test_runs_without_health_suffix_unchanged(self) -> None:
        """When HEALTH_RUNS_DIR is /app/runs (no /health suffix), should return as-is."""
        result = _derive_content_index_runs_dir("/app/runs")
        assert result == Path("/app/runs")

    def test_custom_runs_without_health_suffix_unchanged(self) -> None:
        """When custom path doesn't end with /health, should return as-is."""
        result = _derive_content_index_runs_dir("/data/runs")
        assert result == Path("/data/runs")

    def test_deep_nested_health_path(self) -> None:
        """When HEALTH_RUNS_DIR has deep nested /health, should return parent."""
        result = _derive_content_index_runs_dir("/var/lib/k9b/runs/health")
        assert result == Path("/var/lib/k9b/runs")

    def test_single_segment_health_path(self) -> None:
        """When HEALTH_RUNS_DIR is just /health, should return / (root)."""
        result = _derive_content_index_runs_dir("/health")
        assert result == Path("/")

    def test_strips_trailing_slash(self) -> None:
        """When HEALTH_RUNS_DIR has trailing slash, should be stripped."""
        result = _derive_content_index_runs_dir("/app/runs/")
        assert result == Path("/app/runs")

    def test_preserves_path_object_input(self) -> None:
        """When input is a string, should return Path object."""
        result = _derive_content_index_runs_dir("/app/runs/health")
        assert isinstance(result, Path)
