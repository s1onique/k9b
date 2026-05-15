"""Tests for ui/api_debug.py execution summary diagnostics."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


class TestDebugEnvironmentGuard:
    """Tests for K9B_ENABLE_DEBUG_ENDPOINTS environment guard."""

    def test_debug_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Debug should be disabled when env var is not set."""
        # Ensure env var is not set
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        # Re-import to pick up fresh env state
        import sys

        # Clear any cached imports
        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import _is_debug_enabled

        assert not _is_debug_enabled(), "Debug should be disabled by default"

    def test_debug_enabled_when_env_var_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Debug should be enabled when env var is 'true'."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import _is_debug_enabled

        assert _is_debug_enabled(), "Debug should be enabled when env var is 'true'"

    def test_debug_disabled_when_env_var_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Debug should be disabled when env var is 'false'."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "false")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import _is_debug_enabled

        assert not _is_debug_enabled(), "Debug should be disabled when env var is 'false'"

    def test_debug_disabled_when_env_var_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Debug should be disabled when env var is empty string."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import _is_debug_enabled

        assert not _is_debug_enabled(), "Debug should be disabled when env var is empty"


class TestBuildExecutionSummaryDiagnostics:
    """Tests for build_execution_summary_diagnostics function."""

    def test_returns_none_when_debug_flag_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return None when debug_flag is False."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import build_execution_summary_diagnostics

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            result = build_execution_summary_diagnostics("test-run", health_root, debug_flag=False)
            assert result is None, "Should return None when debug_flag is False"

    def test_returns_none_when_env_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return None when env var is not set."""
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import build_execution_summary_diagnostics

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            result = build_execution_summary_diagnostics("test-run", health_root, debug_flag=True)
            assert result is None, "Should return None when env var is not set"

    def test_returns_diagnostic_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return diagnostic dict when both debug_flag and env are set."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import build_execution_summary_diagnostics

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            # Create a mock ui-index.json
            index_path = health_root / "ui-index.json"
            index_data = {
                "recent_runs_summary": {
                    "runs": [
                        {
                            "run_id": "test-run",
                            "timestamp": "2024-01-01T00:00:00Z",
                            "batchEligibility": "computed",
                            "batchExecutable": False,
                            "batchEligibleCount": 0,
                        }
                    ],
                    "total_count": 1,
                    "generated_at": "2024-01-01T00:00:00Z",
                    "version": 2,
                    "_plan_data": {},
                    "_execution_indices": {},
                }
            }
            index_path.write_text(json.dumps(index_data))

            result = build_execution_summary_diagnostics("test-run", health_root, debug_flag=True)

            assert result is not None, "Should return diagnostic when enabled"
            assert isinstance(result, dict), "Should return dict"
            assert result.get("run_id") == "test-run", "Should include run_id"
            assert "reason_execution_summary_missing" in result, "Should include reason field"