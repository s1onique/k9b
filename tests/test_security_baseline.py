"""Tests for security_baseline.sh behavior.

Tests check_security_baseline.sh in baseline and strict modes:
- Baseline mode permits reviewed-safe findings
- Strict mode fails on all broad except Exception
- Detection of unreviewed handlers

Optimization: Use tiny temp trees instead of full repo scans for most tests.
Keep one CLI smoke test for real shell script behavior.
"""

import os
import shutil
import subprocess
import tempfile as temp_module
import unittest
from pathlib import Path


class TestSecurityBaseline(unittest.TestCase):
    """Test security_baseline.sh behavior in baseline and strict modes.

    Key optimizations:
    - Use tiny temp trees for pattern detection tests (avoids full repo scan)
    - Keep one CLI smoke test for real shell script integration
    - Cache script permissions check in setUp
    """

    REPO_ROOT = Path(__file__).parent.parent
    BASELINE_SCRIPT = REPO_ROOT / "scripts" / "check_security_baseline.sh"
    _script_available = None

    @classmethod
    def setUpClass(cls) -> None:
        """Set up once for all tests."""
        if cls.BASELINE_SCRIPT.exists():
            os.chmod(cls.BASELINE_SCRIPT, 0o755)
            cls._script_available = True
        else:
            cls._script_available = False

    def test_help_flag_succeeds(self) -> None:
        """Script should respond to --help (smoke test)."""
        if not self._script_available:
            self.skipTest("check_security_baseline.sh not found")
        result = subprocess.run(
            [str(self.BASELINE_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )
        self.assertEqual(result.returncode, 0, "Help flag should succeed")
        self.assertIn("baseline", result.stdout)

    def test_unreviewed_handler_fails_baseline(self) -> None:
        """An unreviewed handler should fail baseline mode."""
        if not self._script_available:
            self.skipTest("check_security_baseline.sh not found")

        tmp_dir = temp_module.mkdtemp(prefix="test_security_")
        test_file = Path(tmp_dir) / "k8s_diag_agent" / "test_module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        # Write an unreviewed bare except - should fail
        test_file.write_text('''
def test_func():
    try:
        pass
    except Exception as exc:  # Unreviewed - should trigger failure
        pass
''')

        try:
            allowlist = Path(tmp_dir) / "allowlist.txt"
            allowlist.write_text("# Empty allowlist\n")

            script_content = self.BASELINE_SCRIPT.read_text()
            modified_script = script_content.replace(
                'ALLOWLIST="$SCRIPT_DIR/security_baseline_allowlist.txt"',
                f'ALLOWLIST="{allowlist}"'
            )
            modified_script = modified_script.replace(
                '$REPO_ROOT/src/',
                f'{tmp_dir}/'
            )

            modified_script_file = Path(tmp_dir) / "test_baseline.sh"
            modified_script_file.write_text(modified_script)

            result = subprocess.run(
                ["bash", str(modified_script_file), "--mode", "baseline"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr
            # Should fail because the test file has an unreviewed except
            self.assertIn("FOUND", output)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_except_exception_as_e_is_detected_and_fails_unallowlisted(self) -> None:
        """Script should detect 'except Exception as e:' when not in allowlist."""
        if not self._script_available:
            self.skipTest("check_security_baseline.sh not found")

        tmp_dir = temp_module.mkdtemp(prefix="test_security_")
        test_file = Path(tmp_dir) / "k8s_diag_agent" / "test_module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text('''
def test_func():
    try:
        pass
    except Exception as e:  # This should be detected now - not excluded
        pass
''')

        try:
            allowlist = Path(tmp_dir) / "allowlist.txt"
            allowlist.write_text("# Empty - nothing is allowlisted\n")

            script_content = self.BASELINE_SCRIPT.read_text()
            modified_script = script_content.replace(
                'ALLOWLIST="$SCRIPT_DIR/security_baseline_allowlist.txt"',
                f'ALLOWLIST="{allowlist}"'
            )
            modified_script = modified_script.replace(
                '$REPO_ROOT/src/',
                f'{tmp_dir}/'
            )

            modified_script_file = Path(tmp_dir) / "test_baseline.sh"
            modified_script_file.write_text(modified_script)

            result = subprocess.run(
                ["bash", str(modified_script_file), "--mode", "baseline"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr
            self.assertIn("FOUND", output,
                "except Exception as e: should be detected when not allowlisted")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_strict_mode_fails_with_allowlisted_bare_except(self) -> None:
        """Strict mode should fail on allowlisted bare except patterns."""
        if not self._script_available:
            self.skipTest("check_security_baseline.sh not found")

        tmp_dir = temp_module.mkdtemp(prefix="test_security_")
        # Create a file with bare except that IS allowlisted
        test_file = Path(tmp_dir) / "k8s_diag_agent" / "test_module.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text('''
def safe_handler():
    try:
        pass
    except Exception as e:
        pass
''')

        try:
            # Allowlist the pattern
            allowlist = Path(tmp_dir) / "allowlist.txt"
            allowlist.write_text("k8s_diag_agent/test_module.py except Exception as e\n")

            script_content = self.BASELINE_SCRIPT.read_text()
            modified_script = script_content.replace(
                'ALLOWLIST="$SCRIPT_DIR/security_baseline_allowlist.txt"',
                f'ALLOWLIST="{allowlist}"'
            )
            modified_script = modified_script.replace(
                '$REPO_ROOT/src/',
                f'{tmp_dir}/'
            )

            modified_script_file = Path(tmp_dir) / "test_baseline.sh"
            modified_script_file.write_text(modified_script)

            result = subprocess.run(
                ["bash", str(modified_script_file), "--mode", "strict"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.REPO_ROOT,
            )

            output = result.stdout + result.stderr
            # Strict mode should fail even on allowlisted bare except
            self.assertNotEqual(result.returncode, 0, "Strict mode should fail with allowlisted findings")
            self.assertIn("FOUND", output)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
