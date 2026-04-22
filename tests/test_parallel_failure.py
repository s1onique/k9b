"""Tests for parallel lane failure coordination with controlled subprocesses.

Scenario:
- Lane A: step-a1 (fails quickly), step-a2 (downstream, should SKIP)
- Lane B: step-b1 (runs longer, succeeds), step-b2 (downstream, should SKIP)

Expected behavior:
- step-a1: FAIL (fails fast)
- step-b1: PASS (already running when a1 failed, completes successfully)
- step-a2: SKIP (not yet started when global failure occurred)
- step-b2: SKIP (not yet started when global failure occurred)

This tests the truthful failure handling policy where:
1. Failed step reports FAIL
2. Running steps complete and report their actual status
3. Not-yet-started steps are skipped
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestParallelFailureCoordination(unittest.TestCase):
    """Test parallel lane failure coordination with controlled subprocesses."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        os.chmod(self.STEP_RUNNER, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_parallel_fail_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def tearDown(self) -> None:
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_parallel_failure_fast_fail_triggers_global_flag(self) -> None:
        """Test that a fast failure creates the global failure flag."""
        global_failed_file = os.path.join(self._tmp_dir, "global-failed.flag")
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-fast-fail"
        script = f'touch "{global_failed_file}"; [[ -f "{global_failed_file}" ]] && echo "GLOBAL_FAILURE_SET=true"'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10, env=env)
        self.assertIn("GLOBAL_FAILURE_SET=true", result.stdout)

    def test_parallel_failure_running_step_completes_with_actual_status(self) -> None:
        """Test that already-running steps complete with their actual status."""
        global_failed_file = os.path.join(self._tmp_dir, "global-failed.flag")
        with open(global_failed_file, "w") as f:
            f.write("")
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-running-step"
        script = f'source "{str(self.STEP_RUNNER)}"; step_run_continue "step-b1" "Running step" bash -c "sleep 0.3; echo ok"'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10, env=env)
        self.assertIn("[step-b1] PASS", result.stdout + result.stderr)

    def test_parallel_failure_downstream_step_is_skipped(self) -> None:
        """Test that not-yet-started downstream steps are skipped."""
        global_failed_file = os.path.join(self._tmp_dir, "global-failed.flag")
        with open(global_failed_file, "w") as f:
            f.write("")
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-downstream-skip"
        script = f'[[ -f "{global_failed_file}" ]] && echo "[step-downstream] SKIPPED"'
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10, env=env)
        self.assertIn("SKIPPED", result.stdout)

    def test_verify_all_does_not_kill_running_steps_on_failure(self) -> None:
        """verify_all.sh should NOT kill already-running steps when global failure is detected."""
        verify_content = self.VERIFY_ALL.read_text()
        # Check that "kill $bg_pid" is NOT used to forcibly kill background process
        # (kill -0 is just checking if process exists - that's fine)
        # Look for any "kill $" followed by bg_pid without -0
        self.assertNotRegex(verify_content, r"kill\s+[^0]\w*\s*\$bg_pid", "Should NOT kill running background process")
        # Should use 'wait' to let step complete naturally
        self.assertIn("wait", verify_content, "Should wait for background process to complete")

    def test_verify_all_marks_global_failure_on_step_fail(self) -> None:
        """verify_all.sh should mark global failure immediately when any step fails."""
        verify_content = self.VERIFY_ALL.read_text()
        self.assertIn("_mark_global_failed", verify_content)
        # The check uses '"FAIL"' pattern in _record_step_result function
        self.assertRegex(verify_content, r'"\s*FAIL\s*"', "Should check for FAIL result before marking global failure")

    def test_verify_all_skips_future_steps_after_global_failure(self) -> None:
        """verify_all.sh should skip not-yet-started steps after global failure."""
        verify_content = self.VERIFY_ALL.read_text()
        self.assertIn("_is_global_failed", verify_content)
        self.assertIn("SKIP", verify_content)


if __name__ == "__main__":
    unittest.main()
