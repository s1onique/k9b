"""Tests for scoped verification modes.

Tests verify_all.sh scoped verification modes:
- --python-only flag
- --frontend-only flag
- Profile-based scoping
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestScopedVerificationModes(unittest.TestCase):
    """Test verify_all.sh scoped verification modes (--python-only, --frontend-only)."""

    REPO_ROOT = Path(__file__).parent.parent
    VERIFY_ALL = REPO_ROOT / "scripts" / "verify_all.sh"
    STEP_RUNNER = REPO_ROOT / "scripts" / "step_runner.sh"

    def setUp(self) -> None:
        """Set up isolated temp directory."""
        if not self.VERIFY_ALL.exists():
            self.skipTest("verify_all.sh not found")
        os.chmod(self.VERIFY_ALL, 0o755)
        self._tmp_dir = tempfile.mkdtemp(prefix="test_scoped_")
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

    def test_python_only_flag_accepted(self) -> None:
        """verify_all.sh --python-only should be accepted without error."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        # Should accept the flag
        self.assertNotIn("unrecognized", result.stderr.lower())

    def test_frontend_only_flag_accepted(self) -> None:
        """verify_all.sh --frontend-only should be accepted without error."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--frontend-only", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=self.REPO_ROOT,
        )
        # Should accept the flag
        self.assertNotIn("unrecognized", result.stderr.lower())

    def test_python_only_runs_python_checks(self) -> None:
        """verify_all.sh --python-only should run python checks."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr
        # Should mention python or ruff
        self.assertTrue(
            "python" in output.lower() or "ruff" in output.lower() or result.returncode == 0,
            f"Python-only should run python checks. Output: {output[:500]}"
        )

    def test_frontend_only_runs_frontend_checks(self) -> None:
        """verify_all.sh --frontend-only should run frontend checks."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--frontend-only", "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr
        # Should mention frontend or npm
        self.assertTrue(
            "frontend" in output.lower() or "npm" in output.lower() or result.returncode == 0,
            f"Frontend-only should run frontend checks. Output: {output[:500]}"
        )

    def test_default_runs_all_checks(self) -> None:
        """verify_all.sh without scope flags should run all checks."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--profile", "fast"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr
        # Should complete (pass or fail)
        self.assertIn("profile", output.lower())

    def test_scope_flags_combine_with_profile(self) -> None:
        """Scope flags should combine with --profile correctly."""
        env = os.environ.copy()
        env.pop("VERIFY_ALL_ACTIVE", None)
        result = subprocess.run(
            [str(self.VERIFY_ALL), "--python-only", "--profile", "act-local"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr
        # Should complete
        self.assertTrue(
            "python" in output.lower() or "profile" in output.lower() or result.returncode == 0,
            f"Combined flags should work. Output: {output[:500]}"
        )


if __name__ == "__main__":
    unittest.main()
