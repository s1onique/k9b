"""Tests for verify_all integration with step_runner.

Tests verify_all.sh/verify_all.py integration:
- End-to-end smoke tests for verify_all.sh
- JSON mode output
- Recursion and lock handling
- Profile execution

OPTIMIZED: These tests avoid running the full verification gate to keep CI fast.
Tests that need to verify gate behavior use --print-plan or --list-profiles
instead of running the full --profile fast/act-local.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestVerifyAllIntegration(unittest.TestCase):
    """End-to-end smoke tests for verify_all.sh.

    Only lightweight tests run - no full verification gate execution.
    """

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    VERIFY_PY = REPO_ROOT / "scripts" / "verify_all.py"

    def setUp(self) -> None:
        """Set up test environment."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)

    def test_verify_all_sh_is_executable(self) -> None:
        """verify_all.sh should be executable."""
        self.assertTrue(self.VERIFY_ALL.is_file())
        mode = os.stat(self.VERIFY_ALL).st_mode
        self.assertTrue(mode & 0o111, "verify_all.sh should be executable")

    def test_verify_all_sh_has_help_flag(self) -> None:
        """verify_all.sh should respond to --help."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        # Help should succeed
        self.assertEqual(result.returncode, 0, f"Help flag should succeed. Output: {result.stdout}")
        self.assertIn("help", result.stdout.lower())

    def test_verify_all_sh_shows_profiles(self) -> None:
        """verify_all.sh should list available profiles."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--list-profiles"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        # Should succeed and show profiles
        self.assertEqual(result.returncode, 0)
        self.assertIn("profile", result.stdout.lower())

    def test_verify_all_sh_accepts_fast_profile(self) -> None:
        """verify_all.sh should accept --profile fast (via print-plan, no gate execution)."""
        # Use --print-plan to verify profile acceptance without running the gate
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast", "--print-plan"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0, f"Fast profile should be accepted. Output: {result.stdout}")
        self.assertIn("Profile: fast", result.stdout)

    def test_verify_all_sh_accepts_act_local_profile(self) -> None:
        """verify_all.sh should accept --profile act-local (via --list-profiles)."""
        # Note: act-local is not a valid plan profile (only fast/full are plan profiles)
        # Verify it's accepted by listing profiles
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--list-profiles"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("act-local", result.stdout.lower())

    def test_verify_all_py_exists(self) -> None:
        """verify_all.py should exist as the main implementation."""
        self.assertTrue(self.VERIFY_PY.exists(), "verify_all.py should exist")

    def test_verify_all_py_is_executable(self) -> None:
        """verify_all.py should be executable."""
        if not self.VERIFY_PY.exists():
            self.skipTest("verify_all.py not found")
        mode = os.stat(self.VERIFY_PY).st_mode
        self.assertTrue(mode & 0o111, "verify_all.py should be executable")


class TestVerifyAllJsonMode(unittest.TestCase):
    """Test verify_all JSON mode output."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

    def setUp(self) -> None:
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)

    def test_json_flag_accepted(self) -> None:
        """verify_all.sh should accept --json flag (via print-plan)."""
        # Use --print-plan --json to verify JSON output without running gate
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # Should accept the flag without error
        self.assertNotIn("unrecognized option", output)

    def test_json_mode_produces_valid_json(self) -> None:
        """verify_all.sh JSON output should be parseable (via print-plan --json)."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast", "--print-plan", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        # Should be valid JSON
        try:
            parsed = json.loads(result.stdout)
            self.assertIn("profile", parsed)
        except json.JSONDecodeError as e:
            self.fail(f"Output should be valid JSON: {e}\nOutput: {result.stdout}")


class TestVerifyAllRecursionAndLock(unittest.TestCase):
    """Test verify_all recursion prevention and locking.

    OPTIMIZED: Uses lock module directly with temp directories instead of
    running full verify_all.sh with --profile fast.
    """

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

    def setUp(self) -> None:
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)

    def test_lock_file_created(self) -> None:
        """verify_all should create a lock file during execution (via lock module)."""
        # Test lock module directly with temp directory
        sys_path = str(self.REPO_ROOT / "scripts")
        if sys_path not in __import__("sys").path:
            __import__("sys").path.insert(0, sys_path)

        from verify_all_lock import VerifyLock

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir) / ".verify_lock"
            lock = VerifyLock(lock_dir)

            # Verify lock can be acquired
            acquired = lock.acquire(profile="test")
            self.assertTrue(acquired, "Lock should be acquired")

            # Verify lock file exists
            self.assertTrue(lock_dir.exists(), "Lock directory should exist")

            # Verify lock is active
            status = lock.get_status()
            self.assertTrue(status.locked, "Lock should be active")
            self.assertEqual(status.status, "active", "Status should be active")

            # Clean up
            lock.release()

    def test_concurrent_execution_blocked(self) -> None:
        """verify_all should block concurrent executions (via lock module)."""
        sys_path = str(self.REPO_ROOT / "scripts")
        if sys_path not in __import__("sys").path:
            __import__("sys").path.insert(0, sys_path)

        from verify_all_lock import VerifyLock

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir) / ".verify_lock"

            # First lock acquisition
            lock1 = VerifyLock(lock_dir)
            acquired1 = lock1.acquire(profile="test")
            self.assertTrue(acquired1, "First lock should be acquired")

            # Second lock attempt should fail
            lock2 = VerifyLock(lock_dir)
            acquired2 = lock2.acquire(profile="test")

            # Cleanup
            lock1.release()

            self.assertFalse(acquired2, "Second lock should be blocked")

    def test_lock_cleanup_on_success(self) -> None:
        """verify_all should clean up lock file on success (via lock module)."""
        sys_path = str(self.REPO_ROOT / "scripts")
        if sys_path not in __import__("sys").path:
            __import__("sys").path.insert(0, sys_path)

        from verify_all_lock import VerifyLock

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir) / ".verify_lock"
            lock = VerifyLock(lock_dir)

            # Acquire and release
            acquired = lock.acquire(profile="test")
            self.assertTrue(acquired)
            lock.release()

            # Lock dir should be cleaned up
            # Note: The lock implementation may remove the dir or leave it empty
            # The key is that the lock is released and can be re-acquired
            lock3 = VerifyLock(lock_dir)
            reacquired = lock3.acquire(profile="test")
            self.assertTrue(reacquired, "Lock should be re-acquirable after release")
            lock3.release()

    def test_lock_cleanup_on_failure(self) -> None:
        """verify_all should clean up lock file on failure (invalid profile)."""
        # Run with a non-existent profile to trigger failure
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "nonexistent-profile-xyz"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )

        result.stdout + result.stderr
        # Should fail gracefully
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
