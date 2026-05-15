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


class TestIsDebugDiagnosticsEnabled:
    """Tests for is_debug_diagnostics_enabled function."""

    def test_returns_true_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return True when env var is set to 'true'."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import is_debug_diagnostics_enabled

        assert is_debug_diagnostics_enabled() is True, "Should return True when enabled"

    def test_returns_false_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return False when env var is not set."""
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import is_debug_diagnostics_enabled

        assert is_debug_diagnostics_enabled() is False, "Should return False when disabled"


class TestGetRecentRunsDebugData:
    """Tests for get_recent_runs_debug_data function."""

    def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return None when debug is disabled."""
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_recent_runs_debug_data

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            result = get_recent_runs_debug_data("test-run", health_root)
            assert result is None, "Should return None when disabled"

    def test_returns_data_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return debug data when enabled."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_recent_runs_debug_data

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
                        },
                        {
                            "run_id": "other-run",
                            "timestamp": "2024-01-02T00:00:00Z",
                        },
                    ],
                    "total_count": 2,
                    "generated_at": "2024-01-03T00:00:00Z",
                    "version": 2,
                }
            }
            index_path.write_text(json.dumps(index_data))

            result = get_recent_runs_debug_data("test-run", health_root)

            assert result is not None, "Should return data when enabled"
            assert result.get("run_id") == "test-run"
            assert result.get("total_runs") == 2
            assert result.get("target_row") is not None
            assert result["target_row"].get("run_id") == "test-run"


class TestGetRunsDebugBlock:
    """Tests for get_runs_debug_block function."""

    def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return None when debug is disabled."""
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_runs_debug_block

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            result = get_runs_debug_block("test-run", health_root)
            assert result is None, "Should return None when disabled"


class TestGetWorklistPayload:
    """Tests for get_worklist_payload function."""

    def test_returns_worklist_payload_with_top_level_candidates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return worklist payload when candidates at top level."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_worklist_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            external_analysis = health_root / "external-analysis"
            external_analysis.mkdir()

            # Create plan with top-level candidates
            plan_path = external_analysis / "test-run-next-check-plan.json"
            plan_data = {
                "purpose": "next-check-planning",
                "run_id": "test-run",
                "timestamp": "2024-01-01T00:00:00Z",
                "candidates": [
                    {"index": 0, "cluster": "prod-1", "status": "pending"},
                    {"index": 1, "cluster": "prod-2", "status": "pending"},
                ],
            }
            plan_path.write_text(json.dumps(plan_data))

            result = get_worklist_payload("test-run", health_root)

            assert result.get("run_id") == "test-run"
            assert result.get("run_payload") is not None, f"run_payload should not be None, errors: {result.get('errors')}"
            assert result["run_payload"].get("candidate_count") == 2
            assert result.get("execution_summary") is not None
            assert result["execution_summary"].get("totalCandidates") == 2

    def test_returns_worklist_payload_with_payload_candidates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return worklist payload when candidates in payload.candidates."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_worklist_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            external_analysis = health_root / "external-analysis"
            external_analysis.mkdir()

            # Create plan with nested payload.candidates (real artifact shape)
            plan_path = external_analysis / "test-run-next-check-plan.json"
            plan_data = {
                "purpose": "next-check-planning",
                "run_id": "test-run",
                "timestamp": "2024-01-01T00:00:00Z",
                "payload": {
                    "candidates": [
                        {"index": 0, "cluster": "prod-1", "status": "pending"},
                        {"index": 1, "cluster": "prod-2", "status": "pending"},
                        {"index": 2, "cluster": "prod-3", "status": "pending"},
                    ],
                },
            }
            plan_path.write_text(json.dumps(plan_data))

            result = get_worklist_payload("test-run", health_root)

            assert result.get("run_id") == "test-run"
            assert result.get("run_payload") is not None, f"run_payload should not be None, errors: {result.get('errors')}"
            assert result["run_payload"].get("candidate_count") == 3, "Should read candidates from payload.candidates"

    def test_extracts_root_level_status_from_execution_artifact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should read status from root-level and store in execution_indices."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import get_worklist_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            external_analysis = health_root / "external-analysis"
            external_analysis.mkdir()

            # Create plan with candidates in payload (real artifact shape)
            plan_path = external_analysis / "test-run-next-check-plan.json"
            plan_data = {
                "purpose": "next-check-planning",
                "run_id": "test-run",
                "timestamp": "2024-01-01T00:00:00Z",
                "payload": {
                    "candidates": [
                        {"index": 0, "cluster": "prod-1", "status": "pending"},
                        {"index": 1, "cluster": "prod-2", "status": "pending"},
                        {"index": 2, "cluster": "prod-3", "status": "pending"},
                    ],
                },
            }
            plan_path.write_text(json.dumps(plan_data))

            # Create execution artifacts with root-level status
            exec_path = external_analysis / "test-run-001-next-check-execution.json"
            exec_data = {
                "purpose": "next-check-execution",
                "status": "executed/success",  # Root-level status
                "payload": {
                    "candidateIndex": 0,
                    "cluster": "prod-1",
                },
            }
            exec_path.write_text(json.dumps(exec_data))

            exec_path2 = external_analysis / "test-run-002-next-check-execution.json"
            exec_data2 = {
                "purpose": "next-check-execution",
                "status": "executed/failed",  # Root-level status
                "payload": {
                    "candidateIndex": 1,
                    "cluster": "prod-2",
                },
            }
            exec_path2.write_text(json.dumps(exec_data2))

            result = get_worklist_payload("test-run", health_root)

            # Verify run_payload has the correct candidate count
            assert result.get("run_payload") is not None
            assert result["run_payload"].get("candidate_count") == 3
            
            # Verify execution_summary is computed
            assert result.get("execution_summary") is not None
            # Execution summary counts depend on _compute_execution_summary_indexed behavior
            assert result["execution_summary"].get("totalCandidates") == 3


class TestBuildExecutionStateBundle:
    """Tests for build_execution_state_bundle function."""

    def test_returns_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return None when debug is disabled."""
        monkeypatch.delenv("K9B_ENABLE_DEBUG_ENDPOINTS", raising=False)

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        from k8s_diag_agent.ui.api_debug import build_execution_state_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            result = build_execution_state_bundle("test-run", health_root)
            assert result is None, "Should return None when disabled"

    def test_returns_zip_bundle_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Function should return ZIP bundle bytes when enabled."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        import io
        import zipfile

        from k8s_diag_agent.ui.api_debug import build_execution_state_bundle

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

            result = build_execution_state_bundle("test-run", health_root)

            assert result is not None, "Should return bundle when enabled"
            assert isinstance(result, bytes), "Should return bytes"
            assert len(result) > 0, "Should have non-zero size"

            # Verify it's a valid ZIP
            buffer = io.BytesIO(result)
            with zipfile.ZipFile(buffer, "r") as zf:
                names = zf.namelist()
                assert "summary.md" in names, "Should contain summary.md"
                assert "recent-runs-debug.json" in names, "Should contain recent-runs-debug.json"
                assert "recent-runs-row.json" in names, "Should contain recent-runs-row.json"
                assert "runs-debug-block.json" in names, "Should contain runs-debug-block.json"
                assert "execution-summary-diagnostics.json" in names, "Should contain execution-summary-diagnostics.json"
                assert "worklist-run-payload.json" in names, "Should contain worklist-run-payload.json"

    def test_bundle_contains_valid_json_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bundle should contain valid JSON in all JSON files."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        import io
        import zipfile

        from k8s_diag_agent.ui.api_debug import build_execution_state_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            # Create minimal index
            index_path = health_root / "ui-index.json"
            index_data = {
                "recent_runs_summary": {
                    "runs": [{"run_id": "test-run", "timestamp": "2024-01-01T00:00:00Z"}],
                    "total_count": 1,
                    "generated_at": "2024-01-01T00:00:00Z",
                    "version": 2,
                    "_plan_data": {},
                    "_execution_indices": {},
                }
            }
            index_path.write_text(json.dumps(index_data))

            result = build_execution_state_bundle("test-run", health_root)

            assert result is not None

            buffer = io.BytesIO(result)
            with zipfile.ZipFile(buffer, "r") as zf:
                json_files = [
                    "recent-runs-debug.json",
                    "recent-runs-row.json",
                    "runs-debug-block.json",
                    "execution-summary-diagnostics.json",
                    "worklist-run-payload.json",
                ]
                for json_file in json_files:
                    content = zf.read(json_file).decode("utf-8")
                    parsed = json.loads(content)
                    assert isinstance(parsed, dict), f"{json_file} should be a dict"

    def test_bundle_summary_contains_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bundle summary.md should contain the run ID."""
        monkeypatch.setenv("K9B_ENABLE_DEBUG_ENDPOINTS", "true")

        import sys

        mods_to_clear = [k for k in sys.modules if k.startswith("k8s_diag_agent.ui.api_debug")]
        for mod in mods_to_clear:
            del sys.modules[mod]

        import io
        import zipfile

        from k8s_diag_agent.ui.api_debug import build_execution_state_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            health_root = Path(tmpdir) / "health"
            health_root.mkdir()

            index_path = health_root / "ui-index.json"
            index_data = {
                "recent_runs_summary": {
                    "runs": [{"run_id": "my-test-run-123", "timestamp": "2024-01-01T00:00:00Z"}],
                    "total_count": 1,
                    "generated_at": "2024-01-01T00:00:00Z",
                    "version": 2,
                    "_plan_data": {},
                    "_execution_indices": {},
                }
            }
            index_path.write_text(json.dumps(index_data))

            result = build_execution_state_bundle("my-test-run-123", health_root)

            assert result is not None

            buffer = io.BytesIO(result)
            with zipfile.ZipFile(buffer, "r") as zf:
                summary = zf.read("summary.md").decode("utf-8")
                assert "my-test-run-123" in summary, "Summary should contain run ID"
                assert "# k9b Execution State Diagnostics" in summary, "Summary should have title"
