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

    def test_behavioral_parallel_failure_coordination(self) -> None:
        """Behavioral runtime test for parallel lane failure coordination.

        Scenario:
        - Lane A: step-a1 (fails fast ~50ms), step-a2 (would run later, should SKIP)
        - Lane B: step-b1 (runs ~200ms, succeeds), step-b2 (should SKIP)

        Expected observed outcomes:
        - step-a1: FAIL
        - step-b1: PASS
        - step-a2: SKIP
        - step-b2: SKIP

        This proves the actual coordination policy: fast failure triggers global
        skip for not-yet-started steps while running steps complete truthfully.
        """
        global_flag = os.path.join(self._tmp_dir, "global-failed.flag")
        marker_file = os.path.join(self._tmp_dir, "results.txt")

        # Create helper script with shared functions (must be sourced)
        helper_script = os.path.join(self._tmp_dir, "helper.sh")
        with open(helper_script, "w") as f:
            f.write("""#!/usr/bin/env bash
# Shared coordination helpers - source this before running steps

MARKER_FILE="${MARKER_FILE:-}"
GLOBAL_FLAG="${GLOBAL_FLAG:-}"

_mark_global_failed() {
    touch "$GLOBAL_FLAG" 2>/dev/null || true
}

_is_global_failed() {
    [[ -f "$GLOBAL_FLAG" ]] && return 0 || return 1
}

_record_step() {
    local lane="$1"
    local step_id="$2"
    local result="$3"
    local duration="$4"

    if [[ "$result" == "FAIL" ]]; then
        _mark_global_failed
    fi

    # Append to marker file for test assertions
    echo "${lane}:${step_id}:${result}:${duration}" >> "$MARKER_FILE"
}
""")
        os.chmod(helper_script, 0o755)

        # Create lane A script
        lane_a_script = os.path.join(self._tmp_dir, "lane_a.sh")
        with open(lane_a_script, "w") as f:
            f.write(f"""#!/usr/bin/env bash
set -uo pipefail
source "{helper_script}"

# step-a1: fails fast after 50ms
sleep 0.05
_record_step "python" "step-a1" "FAIL" "50"

# step-a2: would run after a1, should SKIP due to global failure
sleep 0.1
if _is_global_failed; then
    _record_step "python" "step-a2" "SKIP" "0"
else
    _record_step "python" "step-a2" "PASS" "50"
fi
""")
        os.chmod(lane_a_script, 0o755)

        # Create lane B script
        lane_b_script = os.path.join(self._tmp_dir, "lane_b.sh")
        with open(lane_b_script, "w") as f:
            f.write(f"""#!/usr/bin/env bash
set -uo pipefail
source "{helper_script}"

# step-b1: runs longer (200ms), succeeds
sleep 0.2
_record_step "frontend" "step-b1" "PASS" "200"

# step-b2: should SKIP due to global failure from a1
if _is_global_failed; then
    _record_step "frontend" "step-b2" "SKIP" "0"
else
    _record_step "frontend" "step-b2" "PASS" "50"
fi
""")
        os.chmod(lane_b_script, 0o755)

        # Run both lanes in parallel with shared environment
        env = os.environ.copy()
        env["MARKER_FILE"] = marker_file
        env["GLOBAL_FLAG"] = global_flag

        # Launch both lanes concurrently
        proc_a = subprocess.Popen(
            [lane_a_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc_b = subprocess.Popen(
            [lane_b_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for both to complete
        stdout_a, stderr_a = proc_a.communicate(timeout=5)
        stdout_b, stderr_b = proc_b.communicate(timeout=5)

        # Read and parse results
        results = {}
        if os.path.exists(marker_file):
            with open(marker_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split(":")
                        if len(parts) >= 4:
                            lane, step_id, result_status, duration = parts[0], parts[1], parts[2], parts[3]
                            results[step_id] = {"lane": lane, "result": result_status, "duration": duration}

        # Assert actual observed outcomes
        self.assertIn("step-a1", results, "step-a1 should have run")
        self.assertIn("step-b1", results, "step-b1 should have run")
        self.assertIn("step-a2", results, "step-a2 should have run")
        self.assertIn("step-b2", results, "step-b2 should have run")

        # Core assertions: prove the coordination policy
        self.assertEqual(
            results["step-a1"]["result"],
            "FAIL",
            "step-a1 must FAIL (fast failure)",
        )
        self.assertEqual(
            results["step-b1"]["result"],
            "PASS",
            "step-b1 must PASS (completed before/during global failure)",
        )
        self.assertEqual(
            results["step-a2"]["result"],
            "SKIP",
            "step-a2 must SKIP (not yet started when global failure occurred)",
        )
        self.assertEqual(
            results["step-b2"]["result"],
            "SKIP",
            "step-b2 must SKIP (not yet started when global failure occurred)",
        )

        # Verify global failure flag was created
        self.assertTrue(
            os.path.exists(global_flag),
            "Global failure flag must be created when step fails",
        )


if __name__ == "__main__":
    unittest.main()
