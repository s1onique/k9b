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

    def test_verify_all_json_mode_success(self) -> None:
        """verify_all.sh --json should emit valid JSON on stdout on success.
        
        This test runs the full verify_all.sh --json gated behind RUN_FULL_VERIFY_TEST.
        
        Contract:
        - stdout is valid JSON (parseable by json.loads)
        - stdout does not contain compact progress lines (no [step-id] markers)
        - stdout does not contain VERIFICATION GATE text
        - exit code is 0
        - stderr is quiet except for truly fatal wrapper errors
        """
        import json
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh --json test")
        
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        # Exit code should be 0
        self.assertEqual(result.returncode, 0, 
            f"verify_all.sh --json should exit with 0 on success. stderr: {stderr}")
        
        # stdout should be valid JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            self.fail(f"stdout is not valid JSON: {e}\nstdout: {stdout}")
        
        # stdout should not contain compact progress lines (e.g., "[ruff-lint] PASS (0ms)")
        # Check for the full compact progress pattern: [step-id] <status> (
        # Note: JSON documents legitimately contain PASS/FAIL in status fields,
        # but never in the compact progress line format "[step-id] STATUS ("
        self.assertNotIn("[ruff-lint]", stdout, "stdout should not contain step progress in compact format")
        self.assertNotIn("VERIFICATION GATE", stdout, "stdout should not contain gate marker")
        # Check for compact progress line pattern (step-id in brackets followed by status with duration)
        # This pattern will NOT match JSON like {"status": "PASS"} - it's intentionally specific
        self.assertNotRegex(stdout, r"\[\w+-\w+\]\s+(?:PASS|FAIL)\s*\(", 
            "stdout should not contain compact progress lines")
        
        # JSON should have expected structure
        self.assertIn("run_id", data)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "passed")
        self.assertIn("steps", data)
        self.assertGreater(len(data["steps"]), 0, "Should have at least one step")

    def test_verify_all_json_mode_failure_path(self) -> None:
        """verify_all.sh --json failure path: non-zero exit + valid JSON failure summary.
        
        This test is intentionally constrained because:
        1. It requires making a step fail, which is awkward in a gated test
        2. The full verify_all.sh steps (ruff, mypy, npm) are expensive
        
        Approach: This test runs the script normally and accepts that it may pass.
        If it ever fails due to actual code issues, the JSON contract should hold.
        
        The test proves the failure-path contract by testing step_runner JSON mode
        directly (which is already covered by test_json_mode_failure_keeps_nonzero_exit_code).
        
        Additionally, we verify that stderr behavior is correct in JSON mode:
        - stderr should be quiet during normal operation
        - stderr should only contain truly fatal wrapper/preflight errors
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh --json test")
        
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        # Regardless of pass or fail, verify JSON contract holds
        import json
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            self.fail(f"Even on failure, stdout should be valid JSON: {e}")
        
        # If the run succeeded, status should be passed
        # If the run failed, status should be failed (this is the failure path contract)
        if result.returncode == 0:
            self.assertEqual(data["status"], "passed")
        else:
            self.assertEqual(data["status"], "failed")
            self.assertGreater(data["failed_count"], 0)
            self.assertIn("failed_steps", data)
        
        # stderr should be quiet - no step progress lines
        stderr = result.stderr
        # Progress markers should not appear in stderr during JSON mode
        self.assertNotIn("[ruff-lint]", stderr, 
            "stderr should not contain step progress in JSON mode")
        self.assertNotIn("[unit-tests]", stderr,
            "stderr should not contain step progress in JSON mode")
        self.assertNotIn("FAIL (", stderr,
            "stderr should not contain FAIL markers in JSON mode")
        self.assertNotIn("PASS (", stderr,
            "stderr should not contain PASS markers in JSON mode")

    def test_verify_all_json_mode_stderr_contract(self) -> None:
        """verify_all.sh --json stderr should be quiet except for fatal wrapper errors.
        
        Contract:
        - stderr should be empty during normal operation
        - stderr should only contain truly fatal wrapper/preflight errors like:
          - recursion detection
          - lock conflicts
          - missing interpreter
          - argument parsing errors
        
        Progress output and step failures should NOT appear on stderr.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh --json test")
        
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )

        stderr = result.stderr
        
        # stderr should NOT contain step progress markers
        step_patterns = ["[ruff-lint]", "[unit-tests]", "[mypy]", "[npm-", "FAIL (", "PASS ("]
        for pattern in step_patterns:
            self.assertNotIn(pattern, stderr,
                f"stderr should not contain '{pattern}' in JSON mode")
        
        # stderr should NOT contain VERIFICATION GATE
        self.assertNotIn("VERIFICATION GATE", stderr,
            "stderr should not contain VERIFICATION GATE in JSON mode")
        
        # If there is stderr output, it should be a fatal error (non-zero exit code)
        if stderr.strip() and result.returncode == 0:
            self.fail(f"Expected empty stderr on success, got: {stderr}")

    def test_verify_all_json_mode_fatal_error_goes_to_stderr(self) -> None:
        """verify_all.sh --json fatal wrapper errors should still go to stderr.
        
        This tests the contract that truly fatal errors (not step failures)
        are still reported on stderr even in JSON mode.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh --json test")
        
        # Test with unknown argument - should fail with error on stderr
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json", "--unknown-option"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        # Should fail
        self.assertNotEqual(result.returncode, 0)
        
        # Error message should be on stderr
        self.assertIn("Unknown option", result.stderr)
        
        # stdout should be empty (no JSON output on argument error)
        self.assertEqual(result.stdout.strip(), "")


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
        # Verify that unit-tests step sets VERIFY_ALL_ACTIVE and clears RUN_FULL_VERIFY_TEST
        verify_content = self.VERIFY_ALL.read_text()
        
        # Find the unit-tests step call in the Python lane
        # With parallel lanes, it's now called via _run_and_record
        import re
        unit_tests_pattern = r'_run_and_record\s+"python"\s+"unit-tests".*?env\s+.*?VERIFY_ALL_ACTIVE=1'
        self.assertRegex(verify_content, unit_tests_pattern,
            "unit-tests step should pass VERIFY_ALL_ACTIVE=1 to env")
        
        # Verify RUN_FULL_VERIFY_TEST is cleared (set to empty or not passed)
        unit_tests_line_pattern = r'_run_and_record\s+"python"\s+"unit-tests"[^;]+'
        match = re.search(unit_tests_line_pattern, verify_content)
        self.assertIsNotNone(match, "Should find unit-tests step line in Python lane")
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
        # This test runs the full verify_all.sh and is gated behind RUN_FULL_VERIFY_TEST
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        
        # Create a stale lock (PID that doesn't exist)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        lock_dir.mkdir(exist_ok=True)
        lock_file = lock_dir / "pid"
        stale_pid = "999998"
        lock_file.write_text(stale_pid + "\n")
        
        try:
            # Run with isolated env to avoid other checks failing
            env = os.environ.copy()
            result = subprocess.run(
                [str(self.VERIFY_ALL)],
                capture_output=True,
                text=True,
                timeout=300,
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


class TestStepRunnerLongRunningHints(unittest.TestCase):
    """Test runtime hints for long-running steps."""

    REPO_ROOT = Path(__file__).parent.parent
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        self._tmp_dir = tempfile.mkdtemp(prefix="test_hints_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_long_running_step_emits_hint(self) -> None:
        """Long-running step should emit START hint before execution."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-long"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Should emit hint for unit-tests (default long-running step)
        self.assertIn("[HINT:START]", output, "Long-running step should emit START hint")
        self.assertIn("step=unit-tests", output, "Hint should include step id")
        # Should include log path
        self.assertIn("log=", output, "Hint should include log path")
        # Final result should still be present
        self.assertIn("[unit-tests] PASS", output)

    def test_short_step_does_not_emit_hint(self) -> None:
        """Short-running step should NOT emit START hint."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-short"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "ruff-lint" "Ruff lint" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Should NOT emit hint for short-running steps
        self.assertNotIn("[HINT:START]", output, 
            "Short-running step should not emit START hint")

    def test_json_mode_suppresses_hints(self) -> None:
        """JSON mode should suppress hint output."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-json"
        env["STEP_JSON_MODE"] = "1"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "echo ok"; step_finalize 0'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        stdout = result.stdout
        # JSON mode should suppress all hints
        self.assertNotIn("[HINT:START]", stdout, "JSON mode should suppress hints")
        # stdout should be valid JSON
        import json
        data = json.loads(stdout)
        self.assertIn("run_id", data)

    def test_verbose_mode_suppresses_hints(self) -> None:
        """Verbose mode should suppress hint output."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-verbose"
        env["STEP_VERBOSE"] = "1"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Verbose mode streams full output, so hints are not needed
        # The step header is printed instead
        self.assertNotIn("[HINT:START]", output,
            "Verbose mode should suppress hints (uses header instead)")

    def test_custom_long_running_list(self) -> None:
        """Custom STEP_LONG_RUNNING_HINTS should override defaults."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-custom"
        env["STEP_LONG_RUNNING_HINTS"] = "custom-long-step"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "custom-long-step" "Custom test" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        self.assertIn("[HINT:START]", output, 
            "Custom long-running step should emit hint")
        self.assertIn("step=custom-long-step", output)

    def test_hint_includes_log_path(self) -> None:
        """Hint should include the actual log file path for machine parsing."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hint-logpath"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "npm-test-ui" "UI tests" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Hint should include log path
        self.assertIn("log=", output, "Hint should include log path")
        # The log path should point to the expected log file
        self.assertIn("npm-test-ui.log", output, "Log path should reference the step's log file")


class TestStepRunnerHeartbeat(unittest.TestCase):
    """Test heartbeat mechanism for long-running steps."""

    REPO_ROOT = Path(__file__).parent.parent
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        self._tmp_dir = tempfile.mkdtemp(prefix="test_heartbeat_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_short_step_does_not_emit_heartbeat(self) -> None:
        """Short-running step should not emit heartbeat."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-short"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "test-step" "Test step" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        self.assertNotIn("[HINT:HEARTBEAT]", output,
            "Short step should not emit heartbeat")

    def test_json_mode_suppresses_heartbeat(self) -> None:
        """JSON mode should suppress heartbeat output."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-json"
        env["STEP_JSON_MODE"] = "1"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "echo ok"; step_finalize 0'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        stdout = result.stdout
        # JSON mode should suppress heartbeat
        self.assertNotIn("[HINT:HEARTBEAT]", stdout, "JSON mode should suppress heartbeat")

    def test_verbose_mode_suppresses_heartbeat(self) -> None:
        """Verbose mode should suppress heartbeat output."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-verbose"
        env["STEP_VERBOSE"] = "1"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "echo ok"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Verbose mode streams full output, heartbeats not needed
        self.assertNotIn("[HINT:HEARTBEAT]", output,
            "Verbose mode should suppress heartbeat")

    def test_long_step_emits_live_heartbeat_before_result(self) -> None:
        """Long-running step should emit heartbeat BEFORE the PASS/FAIL result line."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-long"
        env["STEP_HEARTBEAT_INTERVAL"] = "1"  # 1 second interval for test
        result = subprocess.run(
            ["bash", "-c", 
             # Sleep for 2 seconds to ensure at least one heartbeat fires during execution
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "sleep 2"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        lines = output.strip().split('\n')
        
        # Should have heartbeat BEFORE final PASS line
        hb_idx = None
        pass_idx = None
        for i, line in enumerate(lines):
            if "[HINT:HEARTBEAT]" in line:
                hb_idx = i
            if "[unit-tests] PASS" in line:
                pass_idx = i
        
        self.assertIsNotNone(hb_idx, "Should emit at least one heartbeat")
        self.assertIsNotNone(pass_idx, "Should emit PASS result")
        # mypy needs explicit assertions for type narrowing
        assert hb_idx is not None
        assert pass_idx is not None
        self.assertLess(hb_idx, pass_idx,
            "Heartbeat should come BEFORE PASS line (live during execution)")

    def test_heartbeat_format_includes_step_elapsed_log(self) -> None:
        """Heartbeat format should include step id, elapsed time, and log path."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-format"
        env["STEP_HEARTBEAT_INTERVAL"] = "1"  # 1 second interval
        result = subprocess.run(
            ["bash", "-c", 
             # Sleep for 2 seconds to ensure heartbeat fires
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "sleep 2"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Should contain the new heartbeat format
        self.assertIn("[HINT:HEARTBEAT]", output, "Should have HINT:HEARTBEAT marker")
        self.assertIn("step=unit-tests", output, "Heartbeat should include step id")
        self.assertIn("elapsed=", output, "Heartbeat should include elapsed time")
        self.assertIn("log=", output, "Heartbeat should include log path")
        # Verify log path references the correct log file
        self.assertIn("unit-tests.log", output, "Log path should reference unit-tests.log")

    def test_heartbeat_only_emits_at_interval_boundaries(self) -> None:
        """Heartbeat should only emit at configured interval boundaries, not every poll."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-boundary"
        env["STEP_HEARTBEAT_INTERVAL"] = "3"  # 3 second interval
        result = subprocess.run(
            ["bash", "-c", 
             # Sleep for 5 seconds - should get exactly one heartbeat at ~3s
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "sleep 5"'],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )

        output = result.stdout
        heartbeat_lines = [ln for ln in output.split('\n') if "[HINT:HEARTBEAT]" in ln]
        # With 3s interval and 5s sleep, should get exactly 1 heartbeat (around 3s elapsed)
        self.assertEqual(len(heartbeat_lines), 1,
            f"Should emit exactly 1 heartbeat at 3s boundary, got {len(heartbeat_lines)}: {heartbeat_lines}")

    def test_heartbeat_distinct_from_hint(self) -> None:
        """Heartbeat should be distinct from START hint - different purpose and timing."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-distinct"
        env["STEP_HEARTBEAT_INTERVAL"] = "1"
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; step_run_continue "unit-tests" "Unit tests" bash -c "sleep 2"'],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout
        # Both START hint and HEARTBEAT should be present (distinct lines)
        self.assertIn("[HINT:START]", output, "Should have START hint")
        self.assertIn("[HINT:HEARTBEAT]", output, "Should have HEARTBEAT")
        # They should be on different lines
        lines = output.split('\n')
        start_lines = [ln for ln in lines if "[HINT:START]" in ln]
        hb_lines = [ln for ln in lines if "[HINT:HEARTBEAT]" in ln]
        self.assertEqual(len(start_lines), 1, "Should have exactly one START hint")
        self.assertGreaterEqual(len(hb_lines), 1, "Should have at least one heartbeat")

    def test_heartbeat_elapsed_is_per_step(self) -> None:
        """Heartbeat elapsed time should be per-step, not cumulative from run start.
        
        This tests that sequential long-running steps each start elapsed from 0.
        """
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-hb-per-step"
        env["STEP_HEARTBEAT_INTERVAL"] = "3"  # 3 second intervals
        # Run two sequential steps: step-1 (4s) then step-2 (4s)
        # step-1 should emit heartbeat at 3s (elapsed=3)
        # step-2 should ALSO emit heartbeat at 3s (elapsed=3, not elapsed=7)
        result = subprocess.run(
            ["bash", "-c", 
             f'source "{self.STEP_RUNNER}"; '
             f'step_run_continue "step-1" "Step 1" bash -c "sleep 4"; '
             f'step_run_continue "step-2" "Step 2" bash -c "sleep 4"'],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )

        output = result.stdout
        
        # Extract heartbeat lines for each step
        step1_hb = [ln for ln in output.split('\n') if "[HINT:HEARTBEAT]" in ln and "step=step-1" in ln]
        step2_hb = [ln for ln in output.split('\n') if "[HINT:HEARTBEAT]" in ln and "step=step-2" in ln]
        
        # Both steps should have emitted heartbeats
        self.assertEqual(len(step1_hb), 1, f"Step 1 should have 1 heartbeat, got: {step1_hb}")
        self.assertEqual(len(step2_hb), 1, f"Step 2 should have 1 heartbeat, got: {step2_hb}")
        
        # Both should have elapsed=3s (first heartbeat at 3s boundary)
        self.assertIn("elapsed=3s", step1_hb[0], "Step 1 heartbeat should have elapsed=3s")
        self.assertIn("elapsed=3s", step2_hb[0], "Step 2 heartbeat should have elapsed=3s, not cumulative")
        
        # Step 2 should NOT have elapsed=7s or higher (cumulative from step-1)
        for line in step2_hb:
            self.assertNotRegex(line, r"elapsed=[7-9]\d+s",
                "Step 2 should not have cumulative elapsed time from step 1")


class TestParallelLanes(unittest.TestCase):
    """Test lane-level parallelism behavior in verify_all.sh."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_parallel_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up temp directory and lock."""
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_verify_all_runs_two_concurrent_lanes(self) -> None:
        """verify_all.sh should run Python and Frontend lanes concurrently.
        
        This test verifies the parallel execution structure without running
        the full expensive suite. We check that the script structure supports
        concurrent lane execution.
        """
        verify_content = self.VERIFY_ALL.read_text()
        
        # Should have Python lane definition
        self.assertIn("_run_python_lane", verify_content,
            "verify_all.sh should define Python lane function")
        
        # Should have Frontend lane definition
        self.assertIn("_run_frontend_lane", verify_content,
            "verify_all.sh should define Frontend lane function")
        
        # Should launch both lanes in background (&)
        self.assertIn("_run_python_lane &", verify_content,
            "Python lane should be launched in background")
        self.assertIn("_run_frontend_lane &", verify_content,
            "Frontend lane should be launched in background")

    def test_verify_all_preserves_canonical_step_order(self) -> None:
        """verify_all.sh JSON summary should have deterministic canonical step order.
        
        Canonical order: ruff-lint, unit-tests, mypy, npm-ci, npm-test-ui, npm-build
        regardless of which lane completed first.
        """
        import json
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        
        # Find lane state file in runs/verification before the run
        verification_dir = self.REPO_ROOT / "runs" / "verification"
        initial_files = set(verification_dir.glob("*-lane-state.json"))
        
        subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )
        
        # Find the new lane state file
        new_files = set(verification_dir.glob("*-lane-state.json"))
        lane_files = sorted(new_files - initial_files)
        
        self.assertGreater(len(lane_files), 0, "Should have created a lane state file")
        
        # Read the lane state file
        latest_file = lane_files[-1]
        with open(latest_file) as f:
            state = json.load(f)
        
        # Extract step IDs in order (python lane first, then frontend)
        step_ids = [s["id"] for s in state["python"] + state["frontend"]]
        
        # Canonical order should be: ruff-lint, unit-tests, mypy (Python lane)
        # followed by npm-ci, npm-test-ui, npm-build (Frontend lane)
        expected_order = ["ruff-lint", "unit-tests", "mypy", "npm-ci", "npm-test-ui", "npm-build"]
        
        self.assertEqual(step_ids, expected_order,
            f"Steps should follow canonical order, got: {step_ids}")

    def test_verify_all_nonzero_exit_on_any_lane_failure(self) -> None:
        """verify_all.sh should return non-zero exit code if any lane step fails.
        
        This is verified by running the full suite - if all steps pass, exit is 0.
        If any step fails, exit should be non-zero.
        """
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )
        
        import json
        data = json.loads(result.stdout.strip())
        
        # Exit code should match status
        if data["status"] == "failed":
            self.assertNotEqual(result.returncode, 0,
                "Exit code should be non-zero when steps fail")
        else:
            self.assertEqual(result.returncode, 0,
                "Exit code should be 0 when all steps pass")

    def test_verify_all_json_mode_pure_json(self) -> None:
        """verify_all.sh --json should emit valid JSON only on stdout.
        
        Contract:
        - stdout is valid JSON (parseable by json.loads)
        - stdout does not contain compact progress lines
        - stderr is quiet during normal operation
        """
        import json
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh --json test")
        
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )
        
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        # stdout should be valid JSON
        try:
            json.loads(stdout)
        except json.JSONDecodeError as e:
            self.fail(f"stdout is not valid JSON: {e}\nstdout: {stdout}")
        
        # stdout should not contain compact progress pattern
        self.assertNotRegex(stdout, r"\[\w+-\w+\]\s+(?:PASS|FAIL)\s*\(",
            "stdout should not contain compact progress lines")
        
        # stderr should be quiet (no step markers)
        step_patterns = ["[ruff-lint]", "[unit-tests]", "[npm-", "FAIL (", "PASS ("]
        for pattern in step_patterns:
            self.assertNotIn(pattern, stderr,
                f"stderr should not contain '{pattern}' in JSON mode")

    def test_verify_all_recursion_protection_preserved(self) -> None:
        """verify_all.sh should still reject recursive invocation under parallel mode."""
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
        self.assertNotEqual(result.returncode, 0,
            "Recursive invocation should fail")
        self.assertIn("recursion detected", output.lower())

    def test_verify_all_lock_protection_preserved(self) -> None:
        """verify_all.sh should still reject concurrent runs under parallel mode."""
        # Create a fake lock with an active-looking PID
        lock_dir = self.REPO_ROOT / ".verify_lock"
        lock_dir.mkdir(exist_ok=True)
        lock_file = lock_dir / "pid"
        fake_pid = str(os.getpid())
        lock_file.write_text(fake_pid + "\n")
        
        try:
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
            self.assertNotEqual(result.returncode, 0,
                "Concurrent run should be rejected")
            self.assertIn("Another verification run is active", output)
        finally:
            if lock_file.exists():
                lock_file.unlink()

    def test_lane_state_file_contains_both_lanes(self) -> None:
        """verify_all.sh should create lane state file with both Python and Frontend results.
        
        This test verifies the parallel execution state tracking works correctly.
        """
        import json
        if os.environ.get("RUN_FULL_VERIFY_TEST") != "1":
            self.skipTest("Set RUN_FULL_VERIFY_TEST=1 to run full verify_all.sh test")
        
        subprocess.run(
            [str(self.VERIFY_ALL), "--json"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=self.REPO_ROOT,
        )
        
        # Find lane state file in runs/verification
        verification_dir = self.REPO_ROOT / "runs" / "verification"
        lane_files = sorted(verification_dir.glob("*-lane-state.json"))
        
        if lane_files:
            # Read the most recent lane state file
            latest_file = lane_files[-1]
            with open(latest_file) as f:
                state = json.load(f)
            
            # Should have both lanes
            self.assertIn("python", state, "Lane state should have python lane")
            self.assertIn("frontend", state, "Lane state should have frontend lane")
            
            # Each lane should have its steps
            python_steps = [s["id"] for s in state["python"]]
            frontend_steps = [s["id"] for s in state["frontend"]]
            
            # Python lane should have ruff-lint, unit-tests, mypy
            for expected in ["ruff-lint", "unit-tests", "mypy"]:
                self.assertIn(expected, python_steps,
                    f"Python lane should include {expected}")
            
            # Frontend lane should have npm-ci, npm-test-ui, npm-build
            for expected in ["npm-ci", "npm-test-ui", "npm-build"]:
                self.assertIn(expected, frontend_steps,
                    f"Frontend lane should include {expected}")


if __name__ == "__main__":
    unittest.main()
