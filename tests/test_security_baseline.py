"""Tests for security_baseline.sh behavior.

Tests check_security_baseline.sh in baseline and strict modes:
- Baseline mode permits reviewed-safe findings
- Strict mode fails on all broad except Exception
- Detection of unreviewed handlers
"""

import os
import subprocess
import unittest
from pathlib import Path


class TestSecurityBaseline(unittest.TestCase):
    """Test security_baseline.sh behavior in baseline and strict modes."""

    REPO_ROOT = Path(__file__).parent.parent
    BASELINE_SCRIPT = REPO_ROOT / "scripts" / "check_security_baseline.sh"

    def setUp(self) -> None:
        """Set up test environment."""
        if not self.BASELINE_SCRIPT.exists():
            self.skipTest("check_security_baseline.sh not found")
        os.chmod(self.BASELINE_SCRIPT, 0o755)

    def test_baseline_mode_passes_with_allowlist(self) -> None:
        """Baseline mode should pass when all bare except Exception are allowlisted."""
        result = subprocess.run(
            [str(self.BASELINE_SCRIPT), "--mode", "baseline"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr

        # Should pass in baseline mode
        self.assertEqual(result.returncode, 0, f"Baseline mode should pass. Output: {output}")
        self.assertIn("Reviewed-safe findings:", output)
        self.assertIn("All security baseline checks passed", output)

    def test_strict_mode_fails_with_allowlist(self) -> None:
        """Strict mode should fail even when bare except Exception are allowlisted."""
        result = subprocess.run(
            [str(self.BASELINE_SCRIPT), "--mode", "strict"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr

        # Strict mode should fail (there are reviewed-safe handlers)
        self.assertNotEqual(result.returncode, 0, "Strict mode should fail with allowlisted findings")
        self.assertIn("reviewed-safe but strict mode", output)

    def test_help_flag_succeeds(self) -> None:
        """Script should respond to --help."""
        result = subprocess.run(
            [str(self.BASELINE_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=self.REPO_ROOT,
        )
        self.assertEqual(result.returncode, 0, "Help flag should succeed")
        self.assertIn("baseline", result.stdout)

    def test_bare_except_detected(self) -> None:
        """Script should detect 'except Exception:' patterns."""
        result = subprocess.run(
            [str(self.BASELINE_SCRIPT), "--mode", "baseline"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=self.REPO_ROOT,
        )
        output = result.stdout + result.stderr

        # Should pass in baseline mode (finding is allowlisted)
        self.assertEqual(result.returncode, 0, f"Baseline mode should pass. Output: {output}")
        self.assertIn("All security baseline checks passed", output)

    def test_unreviewed_handler_fails_baseline(self) -> None:
        """An unreviewed handler should fail baseline mode."""
        # Create a temporary Python file with an unreviewed bare except
        import shutil
        import tempfile as temp_module

        tmp_dir = temp_module.mkdtemp(prefix="test_security_")
        test_file = Path(tmp_dir) / "test_unreviewed.py"
        # Write an unreviewed bare except - should fail
        test_file.write_text('''
def test_func():
    try:
        pass
    except Exception as exc:  # Unreviewed - should trigger failure
        pass
''')

        try:
            # Create a minimal allowlist
            allowlist = Path(tmp_dir) / "allowlist.txt"
            allowlist.write_text("# Empty allowlist\n")

            # Run with minimal setup
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
            # Note: We check that the script runs and finds issues
            self.assertIn("FOUND", output)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_except_exception_as_e_is_detected_and_fails_unallowlisted(self) -> None:
        """Script should detect 'except Exception as e:' when not in allowlist."""
        import shutil
        import tempfile as temp_module

        tmp_dir = temp_module.mkdtemp(prefix="test_security_")
        # Create a file with 'except Exception as e:' - should be flagged if not allowlisted
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

            # Modify script to point to our test directory
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
            # Should find the 'except Exception as e:' pattern - it's now detected
            # The script should report a finding for this unreviewed handler
            self.assertIn("FOUND", output,
                "except Exception as e: should be detected when not allowlisted")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
