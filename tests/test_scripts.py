"""Tests for shell scripts and step runner integration.

These tests are designed to:
- Minimize repo dirt by using isolated temp directories
- Reduce test cost by using step_runner directly for most tests
- Keep one end-to-end smoke test for verify_all.sh
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestStepRunner(unittest.TestCase):
    """Test the step_runner.sh shared library behavior."""

    REPO_ROOT = Path(__file__).parent.parent
    SCRIPT_DIR = REPO_ROOT / "scripts"
    STEP_RUNNER = SCRIPT_DIR / "step_runner.sh"
    VERIFY_ALL = SCRIPT_DIR / "verify_all.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory for each test."""
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        os.chmod(self.STEP_RUNNER, 0o755)
        # Create isolated temp directory for this test
        self._tmp_dir = tempfile.mkdtemp(prefix="test_step_runner_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_step_runner_is_executable(self) -> None:
        """Step runner should be executable."""
        self.assertTrue(self.STEP_RUNNER.is_file())
        mode = os.stat(self.STEP_RUNNER).st_mode
        self.assertTrue(mode & 0o111, "step_runner.sh should be executable")

    def test_step_runner_defines_required_functions(self) -> None:
        """Step runner should define all required functions."""
        source_content = self.STEP_RUNNER.read_text()
        required_functions = [
            "step_run",
            "step_run_continue",
            "step_finalize",
            "step_emit_summary",
            "step_enable_verbose",
            "step_get_results",
            "step_check_failed",
        ]
        for func in required_functions:
            self.assertIn(f"{func}()", source_content)

    def test_step_runner_compact_output_format(self) -> None:
        """Step runner should output single PASS line per step in compact mode."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-minimal"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "test-pass" "Test pass step" echo "ok"',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        # Single line with id, status, duration, and message
        self.assertIn("[test-pass] PASS", output)
        self.assertIn("Test pass step", output)
        # Should be exactly one result line (not two - no separate header)
        lines = [ln for ln in output.strip().split('\n') if 'test-pass' in ln]
        self.assertEqual(len(lines), 1, "Compact mode should emit exactly one result line per step")

    def test_step_runner_failure_includes_log_excerpt(self) -> None:
        """Step runner failure should include log excerpt."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-fail-excerpt"
        # Use step_run_continue to capture failure info without exiting
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run_continue "test-fail-excerpt" "Test fail" bash -c \'echo "error line 1"; echo "error line 2"; false\'',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("FAILED STEP: test-fail-excerpt", output)
        self.assertIn("EXIT CODE:", output)
        self.assertIn("LOG FILE:", output)
        self.assertIn("Failure excerpt", output)

    def test_step_runner_verbose_mode(self) -> None:
        """Step runner should support verbose mode."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-verbose"
        env["STEP_VERBOSE"] = "1"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "test-verbose" "Verbose test" bash -c \'echo "verbose output"; echo "line 2"\'',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("verbose output", output)
        self.assertIn("line 2", output)

    def test_step_runner_summary_file_format(self) -> None:
        """Step runner should emit summary file with correct format."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-summary"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "test-summary-step" "Summary test" echo "ok"; step_finalize 0',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        self.assertIn("Summary:", output)
        self.assertIn("VERIFICATION GATE: PASSED", output)

        # Check summary file exists in isolated directory
        summary_path = Path(self._data_dir) / "test-summary-summary.txt"
        self.assertTrue(summary_path.exists(), "Summary file should be in isolated temp dir")
        content = summary_path.read_text()
        self.assertIn("Run: test-summary", content)
        self.assertIn("Steps:", content)
        self.assertIn("test-summary-step|PASS", content)

    def test_step_runner_json_summary_valid(self) -> None:
        """Step runner should emit valid JSON summary with expected structure."""
        import json
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-json"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "step-a" "Step A" echo "ok"; step_run "step-b" "Step B" echo "ok"; step_finalize 0',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        self.assertIn("VERIFICATION GATE: PASSED", output)

        # Check JSON summary file exists
        json_path = Path(self._data_dir) / "test-json-summary.json"
        self.assertTrue(json_path.exists(), "JSON summary file should exist")
        
        # Verify JSON is valid
        json_content = json_path.read_text()
        data = json.loads(json_content)
        
        # Check required fields
        self.assertIn("run_id", data)
        self.assertEqual(data["run_id"], "test-json")
        self.assertIn("started", data)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "passed")
        self.assertIn("failed_count", data)
        self.assertEqual(data["failed_count"], 0)
        self.assertIn("failed_steps", data)
        self.assertEqual(data["failed_steps"], [])
        self.assertIn("steps", data)
        
        # Check step ordering is preserved
        self.assertEqual(len(data["steps"]), 2)
        self.assertEqual(data["steps"][0]["id"], "step-a")
        self.assertEqual(data["steps"][0]["status"], "PASS")
        self.assertIn("duration_ms", data["steps"][0])
        self.assertEqual(data["steps"][0]["exit_code"], 0)
        self.assertEqual(data["steps"][1]["id"], "step-b")

    def test_step_runner_json_summary_failure_case(self) -> None:
        """Step runner should record failed status in JSON summary."""
        import json
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-json-fail"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run_continue "pass-step" "Pass step" echo "ok"; step_run_continue "fail-step" "Fail step" bash -c "echo error; false"; step_finalize 1',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("VERIFICATION GATE: FAILED", output)

        # Check JSON summary file
        json_path = Path(self._data_dir) / "test-json-fail-summary.json"
        self.assertTrue(json_path.exists(), "JSON summary file should exist")
        
        data = json.loads(json_path.read_text())
        
        # Check failure state
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["failed_steps"], ["fail-step"])
        
        # Check failed step has correct exit code
        fail_step = next(s for s in data["steps"] if s["id"] == "fail-step")
        self.assertEqual(fail_step["status"], "FAIL")
        self.assertNotEqual(fail_step["exit_code"], 0)

    def test_step_runner_creates_logs_in_isolated_dir(self) -> None:
        """Step runner should create logs in the specified directory."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-logs"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "test-logs-step" "Test logs" echo "ok"',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        self.assertEqual(result.returncode, 0)
        log_path = Path(self._log_dir) / "test-logs-test-logs-step.log"
        self.assertTrue(log_path.exists(), "Log file should be in isolated temp dir")
        self.assertIn("ok", log_path.read_text())

    def test_step_runner_step_run_continues_on_failure(self) -> None:
        """step_run_continue should continue after failure - helper test only.
        
        This tests the step_run_continue helper behavior.
        Real verify_all.sh behavior: failure steps are tracked, finalization uses tracked state.
        """
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-continue"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run_continue "step-1" "Step 1" bash -c \'echo "step 1"; false\'; step_run_continue "step-2" "Step 2" echo "step 2"; step_finalize 0',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        # step_run_continue continues execution even on failure
        self.assertIn("[step-1] FAIL", output)
        self.assertIn("[step-2] PASS", output)
        # Note: Finalize with 0 despite tracked failure - this is helper behavior
        # Real verify_all.sh uses step_check_failed to determine exit code

    def test_step_runner_step_run_exits_on_failure(self) -> None:
        """step_run should exit on failure."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-exit"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "step-1" "Step 1" bash -c \'echo "step 1"; false\'; step_run "step-2" "Step 2" echo "step 2 should not run"',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[step-1] FAIL", output)
        # step-2 should not have run because step_run exits on failure
        self.assertNotIn("step 2 should not run", output)

    def test_step_runner_finalize_fails_on_tracked_failure(self) -> None:
        """step_finalize should report FAILED when steps failed."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-finalize-fail"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run_continue "fail-step" "Fail step" bash -c \'echo "failing"; false\'; step_finalize 1',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("VERIFICATION GATE: FAILED", output)
        self.assertIn("FAILED STEP: fail-step", output)

    def test_step_runner_timestamped_log_naming(self) -> None:
        """Step runner should create timestamped log files."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-timestamp"
        subprocess.run(
            [
                "bash",
                "-c",
                f'source "{self.STEP_RUNNER}"; step_run "timestamp-test" "Timestamp test" echo "ok"',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        log_path = Path(self._log_dir)
        logs = list(log_path.glob("test-timestamp-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertRegex(logs[0].name, r"test-timestamp-[a-z-]+\.log")


class TestVerifyAllIntegration(unittest.TestCase):
    """End-to-end smoke tests for verify_all.sh.

    Only one test runs the full verify_all.sh to minimize test cost.
    Other tests use isolated step_runner behavior.
    """

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def test_verify_all_sources_step_runner(self) -> None:
        """verify_all.sh should source step_runner.sh."""
        verify_content = self.VERIFY_ALL.read_text()
        self.assertIn('source "$SCRIPT_DIR/step_runner.sh"', verify_content)

    def test_verify_all_emits_pass_marker(self) -> None:
        """verify_all.sh should emit VERIFICATION GATE: PASSED on success.
        
        This test runs the full verify_all.sh. It is gated behind 
        RUN_FULL_VERIFY_TEST=1 to keep normal test runs fast.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        result = subprocess.run(
            [str(self.VERIFY_ALL)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        self.assertIn("VERIFICATION GATE: PASSED", output)
        self.assertEqual(result.returncode, 0)

    def test_verify_all_creates_logs_in_repo(self) -> None:
        """verify_all.sh should create logs in runs/verification.
        
        This test runs the full verify_all.sh. It is gated behind 
        RUN_FULL_VERIFY_TEST=1 to keep normal test runs fast.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        # Clean up any existing logs first
        verification_dir = self.REPO_ROOT / "runs" / "verification"
        initial_logs = set(verification_dir.glob("*.log")) if verification_dir.exists() else set()

        subprocess.run(
            [str(self.VERIFY_ALL)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        # Check new logs were created
        all_logs = set(verification_dir.glob("*.log"))
        new_logs = all_logs - initial_logs
        self.assertGreater(len(new_logs), 0, "verify_all.sh should create log files")

        # Verify log naming pattern
        for log in new_logs:
            self.assertRegex(
                log.name,
                r"^\d{8}-\d{6}-[a-z-]+\.log$",
                f"Log file {log.name} should match timestamp pattern",
            )


class TestStepRunnerJsonMode(unittest.TestCase):
    """Test JSON output mode via STEP_JSON_MODE environment variable."""

    REPO_ROOT = Path(__file__).parent.parent
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        self._tmp_dir = tempfile.mkdtemp(prefix="test_json_mode_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_json_mode_emits_valid_json_on_stdout(self) -> None:
        """JSON mode should emit valid JSON only on stdout."""
        import json
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-json-stdout"
        env["STEP_JSON_MODE"] = "1"
        result = subprocess.run(
            ["bash", "-c", f'source "{self.STEP_RUNNER}"; step_run "pass-step" "Pass step" echo "ok"; step_finalize 0'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        # stdout should be pure JSON
        stdout = result.stdout.strip()
        # Should not contain progress messages
        self.assertNotIn("[pass-step]", stdout)
        self.assertNotIn("VERIFICATION GATE", stdout)
        # Should be valid JSON
        data = json.loads(stdout)
        self.assertIn("run_id", data)
        self.assertEqual(data["status"], "passed")

    def test_json_mode_success_includes_expected_keys(self) -> None:
        """JSON mode success should include all required top-level keys."""
        import json
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-json-keys"
        env["STEP_JSON_MODE"] = "1"
        result = subprocess.run(
            ["bash", "-c", f'source "{self.STEP_RUNNER}"; step_run "step-a" "Step A" echo "ok"; step_run "step-b" "Step B" echo "ok"; step_finalize 0'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        data = json.loads(result.stdout.strip())
        # Check all required top-level keys
        self.assertIn("run_id", data)
        self.assertIn("started", data)
        self.assertIn("status", data)
        self.assertIn("failed_count", data)
        self.assertIn("failed_steps", data)
        self.assertIn("steps", data)
        # Check values
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["failed_count"], 0)
        self.assertEqual(data["failed_steps"], [])
        self.assertEqual(len(data["steps"]), 2)
        # Check step structure
        for step in data["steps"]:
            self.assertIn("id", step)
            self.assertIn("status", step)
            self.assertIn("duration_ms", step)
            self.assertIn("exit_code", step)
            self.assertIn("log_file", step)

    def test_json_mode_failure_keeps_nonzero_exit_code(self) -> None:
        """JSON mode failure should return non-zero exit code."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-json-fail-exit"
        env["STEP_JSON_MODE"] = "1"
        result = subprocess.run(
            ["bash", "-c", f'source "{self.STEP_RUNNER}"; step_run_continue "fail-step" "Fail step" bash -c "echo error; false"; step_finalize 1'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        self.assertNotEqual(result.returncode, 0)
        import json
        data = json.loads(result.stdout.strip())
        self.assertEqual(data["status"], "failed")
        self.assertGreater(data["failed_count"], 0)


class TestStepRunnerOutputContracts(unittest.TestCase):
    """Test output format contracts for LLM usability."""

    REPO_ROOT = Path(__file__).parent.parent
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        self._tmp_dir = tempfile.mkdtemp(prefix="test_contracts_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_success_output_format(self) -> None:
        """Success output should be compact and LLM-parseable - single line per step."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-llm-format"
        result = subprocess.run(
            ["bash", "-c", f'source "{self.STEP_RUNNER}"; step_run "llm-test" "LLM test" echo "ok"; step_finalize 0'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Single result line with id, status, duration, and message
        self.assertIn("[llm-test] PASS", output)
        self.assertRegex(output, r"\[llm-test\] PASS \(\d+(?:\.\d+)?(?:ms|s)\) - LLM test")
        self.assertIn("VERIFICATION GATE: PASSED", output)

    def test_failure_output_includes_bounded_excerpt(self) -> None:
        """Failure output should include bounded excerpt (last 30 lines)."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-bounded"
        result = subprocess.run(
            ["bash", "-c", f'source "{self.STEP_RUNNER}"; step_run "bounded-test" "Bounded test" bash -c \'for i in $(seq 1 50); do echo "line $i"; done; false\' || true'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        stderr = result.stderr
        self.assertIn("[bounded-test] FAIL", stderr)
        self.assertIn("Failure excerpt", stderr)
        self.assertIn("LOG FILE:", stderr)
        self.assertIn("EXIT CODE:", stderr)


class TestVerifyAllJsonMode(unittest.TestCase):
    """Test verify_all.sh --json flag behavior."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_verify_json_")
        os.makedirs(self._tmp_dir, exist_ok=True)
        # Clean up any existing lock
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            import shutil
            shutil.rmtree(lock_dir, ignore_errors=True)

    def tearDown(self) -> None:
        """Clean up temp directory and lock."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_verify_all_json_flag_accepted(self) -> None:
        """verify_all.sh --json should be accepted without error."""
        # Test with help flag first to verify argument parsing works
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)

    def test_verify_all_default_mode_unchanged(self) -> None:
        """Default mode (no --json) should still show human-readable output.
        
        This test runs the full verify_all.sh gated behind RUN_FULL_VERIFY_TEST.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        result = subprocess.run(
            [str(self.VERIFY_ALL)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # Should contain VERIFICATION GATE marker
        self.assertIn("VERIFICATION GATE: PASSED", output)
        # Should NOT be valid JSON
        import json
        with self.assertRaises(json.JSONDecodeError):
            json.loads(output.strip())


class TestVerifyAllRecursionAndLock(unittest.TestCase):
    """Test recursion protection, lock mechanism, and integration test blocking."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_verify_all_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        # Clean up lock directory if it was created
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_verify_all_rejects_recursive_invocation(self) -> None:
        """verify_all.sh should reject recursive invocation with VERIFY_ALL_ACTIVE set."""
        env = os.environ.copy()
        env["VERIFY_ALL_ACTIVE"] = "1"
        result = subprocess.run(
            [str(self.VERIFY_ALL)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "Recursive invocation should fail")
        self.assertIn("recursion detected", output.lower())

    def test_verify_all_unit_tests_blocked_under_verify_context(self) -> None:
        """Unittest step should block RUN_FULL_VERIFY_TEST when VERIFY_ALL_ACTIVE is set."""
        # Verify that unittest step sets VERIFY_ALL_ACTIVE and clears RUN_FULL_VERIFY_TEST
        verify_content = self.VERIFY_ALL.read_text()
        
        # Find the unit-tests step_run_continue line
        import re
        unit_tests_pattern = r'step_run_continue\s+"unit-tests".*?env\s+.*?VERIFY_ALL_ACTIVE=1'
        self.assertRegex(verify_content, unit_tests_pattern,
            "unit-tests step should pass VERIFY_ALL_ACTIVE=1 to env")
        
        # Verify RUN_FULL_VERIFY_TEST is cleared (set to empty or not passed)
        unit_tests_line_pattern = r'step_run_continue\s+"unit-tests"[^;]+'
        match = re.search(unit_tests_line_pattern, verify_content)
        self.assertIsNotNone(match, "Should find unit-tests step line")
        # mypy needs us to assert again for type narrowing
        assert match is not None
        line = match.group(0)
        # Should have RUN_FULL_VERIFY_TEST= with nothing after it (clearing it)
        self.assertIn("RUN_FULL_VERIFY_TEST=", line,
            "unit-tests step should clear RUN_FULL_VERIFY_TEST")

    def test_verify_all_concurrent_launch_rejected(self) -> None:
        """Second concurrent verify_all.sh run should be rejected by lock."""
        # Create a fake lock with an active-looking PID to simulate concurrent run
        lock_dir = self.REPO_ROOT / ".verify_lock"
        lock_dir.mkdir(exist_ok=True)
        lock_file = lock_dir / "pid"
        # Write the current shell's PID - it's definitely running
        fake_pid = str(os.getpid())
        lock_file.write_text(fake_pid + "\n")
        
        try:
            # Clear VERIFY_ALL_ACTIVE from env to avoid triggering recursion check first
            env = os.environ.copy()
            env.pop("VERIFY_ALL_ACTIVE", None)
            
            result = subprocess.run(
                [str(self.VERIFY_ALL)],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, "Concurrent run should be rejected")
            self.assertIn("Another verification run is active", output)
        finally:
            # Clean up our fake lock
            if lock_file.exists():
                lock_file.unlink()

    def test_verify_all_stale_lock_cleared(self) -> None:
        """verify_all.sh should clear stale locks and proceed."""
        # Create a stale lock (PID that doesn't exist)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        lock_dir.mkdir(exist_ok=True)
        lock_file = lock_dir / "pid"
        stale_pid = "999998"
        lock_file.write_text(stale_pid + "\n")
        
        try:
            # Run with isolated env to avoid other checks failing
            env = os.environ.copy()
            # Don't run full steps, just test that we get past the lock check
            # We can't easily skip pre-flight, but we can verify lock behavior
            # by checking if the error message is NOT about lock
            result = subprocess.run(
                [str(self.VERIFY_ALL)],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr
            # If there's a lock error, it should NOT be about "Another verification run"
            if result.returncode != 0:
                self.assertNotIn("Another verification run is active", output,
                    "Stale lock should be cleared, not cause rejection")
        finally:
            # Clean up stale lock
            if lock_file.exists():
                lock_file.unlink()


if __name__ == "__main__":
    unittest.main()
