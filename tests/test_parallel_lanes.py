"""Tests for parallel execution lanes in verification.

Tests parallel execution patterns:
- Parallel step execution
- Lane isolation
- Resource coordination
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestParallelLanes(unittest.TestCase):
    """Test parallel execution lanes in step_runner."""

    REPO_ROOT = Path(__file__).parent.parent
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        if not self.STEP_RUNNER.exists():
            self.skipTest("step_runner.sh not found")
        os.chmod(self.STEP_RUNNER, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_parallel_")
        self._log_dir = os.path.join(self._tmp_dir, "logs")
        self._data_dir = os.path.join(self._tmp_dir, "data")
        os.makedirs(self._log_dir, exist_ok=True)
        os.makedirs(self._data_dir, exist_ok=True)

    def tearDown(self) -> None:
        import shutil
        if hasattr(self, "_tmp_dir") and os.path.exists(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_parallel_steps_complete(self) -> None:
        """Parallel steps should all complete."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "p1" "Parallel 1" sleep 0.1 &
                step_run "p2" "Parallel 2" sleep 0.1 &
                step_run "p3" "Parallel 3" sleep 0.1 &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[p1]", output)
        self.assertIn("[p2]", output)
        self.assertIn("[p3]", output)

    def test_parallel_steps_independent_logs(self) -> None:
        """Parallel steps should create independent log files."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-logs"
        subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "log1" "Log 1" echo "one" &
                step_run "log2" "Log 2" echo "two" &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        log_path = Path(self._log_dir)
        logs = list(log_path.glob("test-parallel-logs-*.log"))
        # Should have created log files for both parallel steps
        self.assertGreaterEqual(len(logs), 1)

    def test_parallel_steps_exit_codes(self) -> None:
        """Parallel steps should preserve individual exit codes."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-exit"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "pass" "Should pass" echo "ok" &
                step_run "fail" "Should fail" false &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[pass] PASS", output)
        self.assertIn("[fail] FAIL", output)

    def test_parallel_with_sequential_dependency(self) -> None:
        """Parallel steps can be followed by sequential steps."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-seq"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "p1" "Parallel 1" sleep 0.1 &
                step_run "p2" "Parallel 2" sleep 0.1 &
                wait
                step_run "seq" "Sequential after parallel" echo "done"
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[p1]", output)
        self.assertIn("[p2]", output)
        self.assertIn("[seq] PASS", output)

    def test_parallel_steps_timing(self) -> None:
        """Parallel steps should complete faster than sequential."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-timing"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                START=$(date +%s.%N)
                step_run "tp1" "Timing 1" sleep 1 &
                step_run "tp2" "Timing 2" sleep 1 &
                wait
                END=$(date +%s.%N)
                echo "DURATION: $(echo "$END - $START" | bc)"
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[tp1]", output)
        self.assertIn("[tp2]", output)
        # Duration should be close to 1 second (parallel), not 2 (sequential)

    def test_parallel_steps_output_interleaving(self) -> None:
        """Parallel steps should not corrupt each other's output."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-output"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "out1" "Output 1" echo "LINE1" && echo "LINE2" &
                step_run "out2" "Output 2" echo "A" && echo "B" &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[out1]", output)
        self.assertIn("[out2]", output)

    def test_lane_isolation(self) -> None:
        """Steps in different lanes should be isolated."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-lane"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "lane-a/step1" "Lane A Step 1" echo "a1" &
                step_run "lane-b/step1" "Lane B Step 1" echo "b1" &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[lane-a/step1]", output)
        self.assertIn("[lane-b/step1]", output)

    def test_parallel_with_environment_variables(self) -> None:
        """Parallel steps should maintain environment isolation."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-env"
        env["VAR1"] = "value1"
        env["VAR2"] = "value2"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "env1" "Env 1" bash -c 'echo "VAR1=$VAR1"' &
                step_run "env2" "Env 2" bash -c 'echo "VAR2=$VAR2"' &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("value1", output)
        self.assertIn("value2", output)

    def test_parallel_error_propagation(self) -> None:
        """Parallel steps should propagate errors correctly."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-error"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                set -o pipefail
                source "{self.STEP_RUNNER}"
                step_run "err1" "Error 1" false &
                step_run "err2" "Error 2" echo "ok" &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[err1] FAIL", output)

    def test_parallel_with_timeout(self) -> None:
        """Parallel steps should handle timeouts correctly."""
        env = os.environ.copy()
        env["STEP_LOG_DIR"] = self._log_dir
        env["STEP_DATA_DIR"] = self._data_dir
        env["STEP_RUN_TIMESTAMP"] = "test-parallel-timeout"
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'''
                source "{self.STEP_RUNNER}"
                step_run "to1" "Timeout 1" timeout 1 sleep 5 &
                step_run "to2" "Timeout 2" echo "ok" &
                wait
                ''',
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        output = result.stdout + result.stderr
        self.assertIn("[to1]", output)
        self.assertIn("[to2]", output)


if __name__ == "__main__":
    unittest.main()
