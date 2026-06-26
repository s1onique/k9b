"""Tests for atomic lock concurrency under race conditions.

Tests atomic lock behavior under actual concurrent race conditions:
- mkdir-based atomic lock under real startup race
- Exactly one process wins and others fail with active-lock error
- Lock cleanup by winner on exit
"""

import os
import subprocess
import unittest
from pathlib import Path


class TestAtomicLockRaces(unittest.TestCase):
    """Test atomic lock behavior under actual concurrent race conditions.

    This tests the mkdir-based atomic lock under real startup race conditions,
    proving that exactly one process wins and others fail with active-lock error.

    The test spawns multiple processes nearly simultaneously and verifies:
    - Exactly one process succeeds (wins the lock)
    - All other processes fail with the "Another verification run is active" error
    - The lock is properly cleaned up by the winner on exit

    Note: These tests are gated behind CONCURRENCY_TEST=1 because they spawn
    multiple processes and may take ~30-60 seconds to run.
    """

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

    def setUp(self) -> None:
        """Set up test environment."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        # Clean up any existing lock before test
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            import shutil
            shutil.rmtree(lock_dir, ignore_errors=True)

    def tearDown(self) -> None:
        """Clean up lock directory after test."""
        import shutil
        lock_dir = self.REPO_ROOT / ".verify_lock"
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_atomic_lock_race_exactly_one_wins(self) -> None:
        """Atomic lock should ensure exactly one process wins under concurrent startup race.

        This test proves the mkdir-based atomic lock works correctly by:
        1. Spawning N processes nearly simultaneously (with ThreadPoolExecutor)
        2. Waiting for all to complete
        3. Verifying exactly one succeeded (exit code 0)
        4. Verifying all others failed with active-lock error

        Uses --python-only to minimize runtime while still exercising full lock path.
        """
        if os.environ.get("CONCURRENCY_TEST") != "1":
            self.skipTest("Set CONCURRENCY_TEST=1 to run atomic lock race test")

        import concurrent.futures
        import shutil

        lock_dir = self.REPO_ROOT / ".verify_lock"

        # Clean lock directory before test
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

        # Number of concurrent processes to spawn
        num_concurrent = 5

        # Track results from each process
        results: list[tuple[int, str, str]] = []  # (exit_code, stdout, stderr)

        def run_verify() -> tuple[int, str, str]:
            """Run verify_all.sh in a subprocess and return results."""
            env = os.environ.copy()
            env.pop("VERIFY_ALL_ACTIVE", None)
            # Use --python-only to minimize runtime
            result = subprocess.run(
                [str(self.VERIFY_ALL), "--python-only"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                cwd=self.REPO_ROOT,
            )
            return (result.returncode, result.stdout, result.stderr)

        # Launch all processes nearly simultaneously using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(run_verify) for _ in range(num_concurrent)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append((-1, "", str(e)))

        successes = [r for r in results if r[0] == 0]
        failures = [r for r in results if r[0] != 0]

        self.assertEqual(
            len(successes), 1,
            f"Expected exactly 1 process to win the lock, got {len(successes)}. "
            f"Exit codes: {[r[0] for r in results]}"
        )

        for i, (exit_code, stdout, stderr) in enumerate(failures):
            combined = stdout + stderr
            self.assertIn(
                "Another verification run is active", combined,
                f"Process {i} (exit={exit_code}) should fail with active-lock error. "
                f"Output: {combined[:200]}"
            )

        lock_marker = lock_dir / ".lock"
        self.assertFalse(
            lock_marker.exists(),
            "Lock should be cleaned up after winner exits"
        )

    def test_atomic_lock_race_with_process_pool(self) -> None:
        """Stress test: Multiple rapid fork attempts with ProcessPoolExecutor.

        Uses true separate processes for maximum race condition probability.
        Gated behind CONCURRENCY_TEST=1.
        """
        if os.environ.get("CONCURRENCY_TEST") != "1":
            self.skipTest("Set CONCURRENCY_TEST=1 to run atomic lock race test")

        import concurrent.futures
        import shutil

        lock_dir = self.REPO_ROOT / ".verify_lock"

        # Clean lock directory before test
        if lock_dir.exists():
            shutil.rmtree(lock_dir, ignore_errors=True)

        num_concurrent = 8

        def spawn_verify() -> tuple[int, str]:
            env = os.environ.copy()
            env.pop("VERIFY_ALL_ACTIVE", None)
            result = subprocess.run(
                [str(self.VERIFY_ALL), "--python-only"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                cwd=self.REPO_ROOT,
            )
            return (result.returncode, result.stdout + result.stderr)

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(spawn_verify) for _ in range(num_concurrent)]
            results = []
            for future in concurrent.futures.as_completed(futures, timeout=120):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append((-1, str(e)))

        successes = [r for r in results if r[0] == 0]
        failures = [r for r in results if r[0] != 0]

        self.assertEqual(
            len(successes), 1,
            f"Expected exactly 1 winner, got {len(successes)}. "
            f"Exit codes: {[r[0] for r in results]}"
        )

        for i, (exit_code, output) in enumerate(failures):
            self.assertIn(
                "Another verification run is active", output,
                f"Failure {i} should be due to active lock. Exit: {exit_code}"
            )

        lock_marker = lock_dir / ".lock"
        self.assertFalse(
            lock_marker.exists(),
            "Lock should not be left behind after race test"
        )


if __name__ == "__main__":
    unittest.main()
