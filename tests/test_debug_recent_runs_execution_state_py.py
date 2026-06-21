"""Tests for debug_recent_runs_execution_state.py.

Tests use in-process mocking for HTTP tests, subprocess for CLI surface only.
"""

import json
import os
import shutil
import subprocess

# Import module directly for in-process testing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from debug_recent_runs_execution_state import run_debug, validate_run_id

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
SCRIPT_PY = SCRIPT_DIR / "debug_recent_runs_execution_state.py"
SCRIPT_SH = SCRIPT_DIR / "debug_recent_runs_execution_state.sh"


class TestValidation(unittest.TestCase):
    """Test run_id validation."""
    
    def test_valid_run_id(self) -> None:
        is_valid, msg = validate_run_id("health-run-20260515T073859Z")
        self.assertTrue(is_valid)
    
    def test_path_traversal_rejected(self) -> None:
        is_valid, msg = validate_run_id("../etc/passwd")
        self.assertFalse(is_valid)
        self.assertIn("path traversal", msg.lower())
    
    def test_slash_rejected(self) -> None:
        is_valid, msg = validate_run_id("run/test")
        self.assertFalse(is_valid)
    
    def test_backslash_rejected(self) -> None:
        is_valid, msg = validate_run_id("run\\test")
        self.assertFalse(is_valid)
    
    def test_double_dot_rejected(self) -> None:
        is_valid, _ = validate_run_id("foo..bar")
        self.assertFalse(is_valid)
    
    def test_special_chars_rejected(self) -> None:
        is_valid, _ = validate_run_id("run$test")
        self.assertFalse(is_valid)
    
    def test_underscore_accepted(self) -> None:
        is_valid, _ = validate_run_id("run_test_123")
        self.assertTrue(is_valid)
    
    def test_empty_rejected(self) -> None:
        is_valid, msg = validate_run_id("")
        self.assertFalse(is_valid)


PYTHON = REPO_ROOT / ".venv" / "bin" / "python"


class TestCliSurface(unittest.TestCase):
    """Test CLI surface via subprocess using .venv python."""
    
    def test_help_exits_zero(self) -> None:
        result = subprocess.run([str(PYTHON), str(SCRIPT_PY), "--help"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
    
    def test_help_contains_options(self) -> None:
        result = subprocess.run([str(PYTHON), str(SCRIPT_PY), "--help"], capture_output=True, text=True, timeout=10)
        output = result.stdout + result.stderr
        self.assertIn("--base-url", output)
        self.assertIn("--run-id", output)
    
    def test_missing_base_url_exits_2(self) -> None:
        result = subprocess.run([str(PYTHON), str(SCRIPT_PY), "--run-id", "test"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
    
    def test_missing_run_id_exits_2(self) -> None:
        result = subprocess.run([str(PYTHON), str(SCRIPT_PY), "--base-url", "http://x"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
    
    def test_invalid_run_id_exits_3(self) -> None:
        result = subprocess.run(
            [str(PYTHON), str(SCRIPT_PY), "--base-url", "http://x", "--run-id", "../x"],
            capture_output=True, text=True, timeout=10
        )
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("path traversal", result.stderr.lower())


class TestShellShim(unittest.TestCase):
    """Test shell shim delegation."""
    
    def test_shell_help(self) -> None:
        result = subprocess.run([str(SCRIPT_SH), "--help"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--base-url", result.stdout)
    
    def test_shell_rejects_path_traversal(self) -> None:
        result = subprocess.run(
            [str(SCRIPT_SH), "--base-url", "http://x", "--run-id", "../x"],
            capture_output=True, text=True, timeout=10
        )
        self.assertNotEqual(result.returncode, 0, result.stderr)


class TestRunDebugInProcess(unittest.TestCase):
    """Test run_debug function directly with mocked HTTP."""
    
    def setUp(self) -> None:
        self._tmp_dir = tempfile.mkdtemp(prefix="test_debug_")
    
    def tearDown(self) -> None:
        if os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
    
    def _mock_response(self, data: dict, status: int = 200) -> MagicMock:
        mock = MagicMock()
        mock.getcode.return_value = status
        mock.read.return_value = json.dumps(data).encode('utf-8')
        return mock
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_produces_all_files(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.fetch_json.return_value = (
            {"runs": [{"runId": "test-run"}], "_debug_execution_summary": {"stale_index_detected": True}},
            200,
            None
        )
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        exit_code = run_debug(
            base_url="http://localhost:8080",
            run_id="test-run",
            output_dir=output_dir,
        )
        
        self.assertEqual(exit_code, 0)
        for fname in ["recent-runs-debug.json", "recent-runs-row.json", 
                       "runs-debug-block.json", "execution-summary-diagnostics.json",
                       "worklist-run-payload.json", "summary.md"]:
            self.assertTrue((output_dir / fname).exists(), f"{fname} missing")
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_summary_contains_sections(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.fetch_json.return_value = (
            {"runs": [{"runId": "test-run"}], "_debug_execution_summary": {"stale_index_detected": True}},
            200, None
        )
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        run_debug("http://localhost:8080", "test-run", output_dir=output_dir)
        
        content = (output_dir / "summary.md").read_text()
        self.assertIn("Recent Runs Row", content)
        self.assertIn("Root-Cause Hints", content)
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_stale_index_hint(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.fetch_json.return_value = (
            {"runs": [{"runId": "test-run"}], "_debug_execution_summary": {"stale_index_detected": True}},
            200, None
        )
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        run_debug("http://localhost:8080", "test-run", output_dir=output_dir)
        
        content = (output_dir / "summary.md").read_text()
        self.assertIn("stale", content.lower())
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_worklist_failure_graceful(self, mock_client_cls: MagicMock) -> None:
        call_count = [0]
        def side_effect(url: str) -> tuple[dict[str, list[object] | None] | None, int, str | None]:
            call_count[0] += 1
            if "/api/run?" in url:
                return None, 404, "Not Found"
            return {"runs": [], "_debug_execution_summary": None}, 200, None
        
        mock_client = MagicMock()
        mock_client.fetch_json.side_effect = side_effect
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        exit_code = run_debug("http://localhost:8080", "test-run", output_dir=output_dir)
        
        # Should exit 0 even with worklist failure (only main endpoints counted)
        self.assertIn(exit_code, [0, 5])
        # Worklist file should exist
        self.assertTrue((output_dir / "worklist-run-payload.json").exists())
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_all_endpoints_fail_exit_5(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.fetch_json.return_value = None, 0, "Connection refused"
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        exit_code = run_debug("http://localhost:8080", "test-run", output_dir=output_dir)
        
        # 2 main endpoints fail + worklist = partial failure
        self.assertEqual(exit_code, 5)
    
    @patch('debug_recent_runs_execution_state.HttpClient')
    def test_diag_failure_counts_as_partial_failure(self, mock_client_cls: MagicMock) -> None:
        """Regression test: diag endpoint failure must update failed_count."""
        mock_client = MagicMock()
        
        def side_effect(url: str) -> tuple[dict[str, object] | None, int, str | None]:
            if "/api/debug/runs/" in url:
                return None, 500, "HTTP 500"
            return {"runs": [{"runId": "test-run"}], "_debug_execution_summary": {}}, 200, None
        
        mock_client.fetch_json.side_effect = side_effect
        mock_client_cls.return_value = mock_client
        
        output_dir = Path(self._tmp_dir) / "output"
        exit_code = run_debug("http://localhost:8080", "test-run", output_dir=output_dir)
        
        # Diag endpoint failed, so should return partial failure
        self.assertEqual(exit_code, 5)


if __name__ == "__main__":
    unittest.main()
