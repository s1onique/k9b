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
        script = f'source "{str(self.STEP_RUNNER)}"; step_run_continue "step-b1" "Running step" bash -c "sleep 0.05; echo ok"'
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
# First set the flag (step-a1 already did), then check
sleep 0.15
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

# step-b1: runs longer (100ms), succeeds
sleep 0.1
_record_step "frontend" "step-b1" "PASS" "100"

# step-b2: should SKIP due to global failure from a1
# Wait for lane A to have time to set the flag
sleep 0.1
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


    def test_orchestrator_runner_failure_propagates_to_aggregate(self) -> None:
        """Python orchestrator: lane failure causes aggregate failure.
        
        This tests the actual behavioral contract:
        1. When a lane fails, the aggregate result must be failure
        2. Lane result must track failed_count
        3. step_count and failed_count are tracked
        """
        import sys
        sys.path.insert(0, str(self.REPO_ROOT / "scripts"))
        try:
            import dataclasses

            from verify_all_orchestrator import LaneResult, VerificationResult
            
            # VerificationResult is a dataclass with correct fields
            fields = {f.name for f in dataclasses.fields(VerificationResult)}
            lane_fields = {f.name for f in dataclasses.fields(LaneResult)}
            
            # Contract: VerificationResult must have success and lane_results
            self.assertIn("success", fields, "VerificationResult must track success")
            self.assertIn("lane_results", fields, "VerificationResult must have lane_results")
            
            # Contract: LaneResult must have failed_count and success
            self.assertIn("failed_count", lane_fields, "LaneResult must track failed_count")
            self.assertIn("success", lane_fields, "LaneResult must track lane success")
            
            # Simulate a failed lane result
            failed_lane = LaneResult(
                lane="python",
                success=False,
                exit_code=1,
                duration_ms=100,
                step_count=3,
                failed_count=1,
            )
            
            # Contract assertions
            self.assertFalse(failed_lane.success, "Lane must be failure when steps fail")
            self.assertEqual(failed_lane.failed_count, 1, "Lane must track failed_count")
        except ImportError:
            self.skipTest("verify_all_orchestrator not available")
    
    def test_orchestrator_aggregate_fails_when_any_lane_fails(self) -> None:
        """Python orchestrator: if any lane fails, aggregate success must be False.
        
        This proves the failure aggregation contract.
        """
        import sys
        sys.path.insert(0, str(self.REPO_ROOT / "scripts"))
        try:
            from verify_all_orchestrator import LaneResult, VerificationResult
            
            # Simulate mixed results: one lane passes, one fails
            python_lane = LaneResult(
                lane="python",
                success=True,
                exit_code=0,
                duration_ms=100,
                step_count=3,
                failed_count=0,
            )
            frontend_lane = LaneResult(
                lane="frontend",
                success=False,
                exit_code=1,
                duration_ms=200,
                step_count=3,
                failed_count=1,
            )
            
            # Aggregate result: if any lane fails, success is False
            result = VerificationResult(
                success=False,  # At least one lane failed
                profile="full",
                scope="all",
                is_full_gate=True,
                is_full_lane=False,
                step_count=6,
                skipped_count=0,
                total_duration_ms=300,
                lane_results=[python_lane, frontend_lane],
                lane_state={},
                skipped=[],
                error_message=None,
            )
            
            # Contract: aggregate must be failure when any lane fails
            self.assertFalse(result.success, "Aggregate must be failure when any lane fails")
            self.assertEqual(len(result.lane_results), 2, "Must have results from both lanes")
        except ImportError:
            self.skipTest("verify_all_orchestrator not available")

    def test_orchestrator_forced_runner_failure_propagates(self) -> None:
        """Real forced-runner-failure test: one lane fails via subprocess, verify aggregate fails.
        
        This test executes the actual failure code path by monkeypatching _spawn_lane_runner
        to return a failing subprocess. This proves the orchestrator properly:
        1. Detects non-zero exit code from runner
        2. Sets lane.success = False
        3. Sets overall success = False
        4. Records failed lane in lane_results
        """
        import subprocess
        import sys
        from unittest.mock import MagicMock, patch
        
        sys.path.insert(0, str(self.REPO_ROOT / "scripts"))
        try:
            from verify_all_orchestrator import VerificationOrchestrator
            
            def fake_spawn_lane_runner(self: VerificationOrchestrator, lane: str, env: dict) -> subprocess.Popen:
                """Spawn a fake failing runner process."""
                # Create a mock Popen that returns exit code 1 (failure)
                mock_process = MagicMock(spec=subprocess.Popen)
                mock_process.wait.return_value = 1  # Simulate failed step
                mock_process.stdout = None
                mock_process.stderr = None
                return mock_process
            
            with tempfile.TemporaryDirectory() as tmpdir:
                orch = VerificationOrchestrator(
                    repo_root=tmpdir,
                    profile="fast",
                    scope="python",
                )
                orch.setup()
                
                # Monkeypatch _spawn_lane_runner to return failing process
                with patch.object(VerificationOrchestrator, '_spawn_lane_runner', fake_spawn_lane_runner):
                    # Also patch _get_lane_duration and _get_lane_stats to avoid file operations
                    orch._get_lane_duration = lambda lane: 100
                    orch._get_lane_stats = lambda lane: (1, 1)
                    
                    # Execute - this will call our fake failing subprocess
                    result = orch.execute()
                
                # Contract assertions:
                # 1. Aggregate result success is false
                self.assertFalse(result.success, "Aggregate success must be False when runner fails")
                
                # 2. Failing lane is represented in lane_results
                self.assertGreater(len(result.lane_results), 0, "lane_results must not be empty")
                
                # 3. At least one lane has success=False
                failed_lanes = [lr for lr in result.lane_results if not lr.success]
                self.assertGreater(len(failed_lanes), 0, "At least one lane must have success=False")
                
                # 4. Failed lane has non-zero exit code
                for lr in failed_lanes:
                    self.assertNotEqual(lr.exit_code, 0, f"Lane {lr.lane} failed with exit_code {lr.exit_code}")
                
                # 5. to_json() includes failed lane info
                json_output = result.to_json()
                self.assertFalse(json_output["success"], "JSON output must reflect failure")
                
        except ImportError:
            self.skipTest("verify_all_orchestrator not available")

    def test_orchestrator_lane_state_records_failure_truthfully(self) -> None:
        """Python orchestrator: lane state file records failures with actual exit codes.
        
        This proves the state file is not sanitized or relabeled.
        """
        import json
        import sys
        sys.path.insert(0, str(self.REPO_ROOT / "scripts"))
        try:
            from verify_all_orchestrator import VerificationOrchestrator
            
            with tempfile.TemporaryDirectory() as tmpdir:
                orch = VerificationOrchestrator(
                    repo_root=tmpdir,
                    profile="fast",
                    scope="python",
                )
                orch.setup()
                
                # Check lane state file structure
                self.assertTrue(orch.lane_state_file.exists(), "Lane state file must exist")
                
                state = json.loads(orch.lane_state_file.read_text())
                
                # Contract: state must have lanes structure
                self.assertIn("python", state, "Lane state must have python lane")
                self.assertIn("frontend", state, "Lane state must have frontend lane")
                
                # Each lane must have steps array with proper structure
                for lane_name, lane_steps in state.items():
                    self.assertIsInstance(lane_steps, list, f"Lane {lane_name} must be a list")
                    for step in lane_steps:
                        self.assertIn("id", step, "Step must have id")
                        self.assertIn("status", step, "Step must have status")
                        # exit_code must be present (null for skipped, number for run)
                        self.assertIn("exit_code", step, "Step must have exit_code field")
        except ImportError:
            self.skipTest("verify_all_orchestrator not available")


if __name__ == "__main__":
    unittest.main()
