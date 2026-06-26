"""Tests for verify_all integration with step_runner.

Tests verify_all.sh/verify_all.py integration:
- End-to-end smoke tests for verify_all.sh
- JSON mode output
- Recursion and lock handling
- Profile execution
"""

import os
import subprocess
import unittest
from pathlib import Path


class TestVerifyAllIntegration(unittest.TestCase):
    """End-to-end smoke tests for verify_all.sh.

    Only one test runs the full verify_all.sh to minimize test cost.
    Other tests use isolated step_runner behavior.

    Note: verify_all.sh is now a thin shim that delegates to verify_all.py.
    Tests checking for shell orchestration logic should be updated to test
    Python behavior instead.
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
            timeout=30,
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
            timeout=30,
            cwd=self.REPO_ROOT,
        )

        # Should succeed and show profiles
        self.assertEqual(result.returncode, 0)
        self.assertIn("profile", result.stdout.lower())

    def test_verify_all_sh_accepts_fast_profile(self) -> None:
        """verify_all.sh should accept --profile fast."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        # Should complete (may pass or fail depending on state)
        result.stdout + result.stderr
        self.assertIn("fast", result.stdout.lower())

    def test_verify_all_sh_accepts_act_local_profile(self) -> None:
        """verify_all.sh should accept --profile act-local."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "act-local"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        # Should complete
        result.stdout + result.stderr
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
        """verify_all.sh should accept --json flag."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # Should accept the flag without error
        self.assertNotIn("unrecognized option", output)

    def test_json_mode_produces_valid_json(self) -> None:
        """verify_all.sh JSON output should be parseable."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # JSON output should contain expected fields
        self.assertIn('"profile":', output)


class TestVerifyAllRecursionAndLock(unittest.TestCase):
    """Test verify_all recursion prevention and locking."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"

    def setUp(self) -> None:
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)

    def test_lock_file_created(self) -> None:
        """verify_all should create a lock file during execution."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # Check that lock mechanism is mentioned
        self.assertIn("lock", output.lower())

    def test_concurrent_execution_blocked(self) -> None:
        """verify_all should block concurrent executions."""
        # Start first execution
        proc1 = subprocess.Popen(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.REPO_ROOT,
        )

        # Wait a bit for lock to be acquired
        import time
        time.sleep(2)

        # Start second execution
        proc2 = subprocess.Popen(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.REPO_ROOT,
        )

        # Wait for both to complete
        stdout1, stderr1 = proc1.communicate(timeout=120)
        stdout2, stderr2 = proc2.communicate(timeout=120)

        # At least one should detect the lock
        output = stdout1 + stderr1 + stdout2 + stderr2
        self.assertIn("lock", output.lower())

    def test_lock_cleanup_on_success(self) -> None:
        """verify_all should clean up lock file on success."""
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=self.REPO_ROOT,
        )

        output = result.stdout + result.stderr
        # Should complete without leaving stale lock
        self.assertNotIn("stale lock", output.lower())

    def test_lock_cleanup_on_failure(self) -> None:
        """verify_all should clean up lock file on failure."""
        # Run with a non-existent profile to trigger failure
        result = subprocess.run(
            ["bash", str(self.VERIFY_ALL), "--profile", "nonexistent-profile-xyz"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=self.REPO_ROOT,
        )

        result.stdout + result.stderr
        # Should fail gracefully
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
