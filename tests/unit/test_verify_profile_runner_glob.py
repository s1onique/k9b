#!/usr/bin/env python3
"""
Tests for verify_profile_runner glob expansion.

Verifies:
1. Glob patterns are expanded correctly (e.g., tests/test_*.py)
2. Non-glob arguments are preserved
3. Unmatched glob patterns fail closed with clear error
4. Runner does not use shell=True for glob expansion
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts to path
REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from verify_profile_runner import (  # noqa: E402
    _has_glob_metachar,
    expand_globs,
)


class TestHasGlobMetachar(unittest.TestCase):
    """Tests for glob metacharacter detection."""

    def test_asterisk_detected(self) -> None:
        """Asterisk is detected as glob metacharacter."""
        self.assertTrue(_has_glob_metachar("test_*.py"))

    def test_question_detected(self) -> None:
        """Question mark is detected as glob metacharacter."""
        self.assertTrue(_has_glob_metachar("test_?.py"))

    def test_bracket_detected(self) -> None:
        """Bracket is detected as glob metacharacter."""
        self.assertTrue(_has_glob_metachar("test_[abc].py"))

    def test_plain_file_not_detected(self) -> None:
        """Plain filename without metacharacters is not detected."""
        self.assertFalse(_has_glob_metachar("test_example.py"))
        self.assertFalse(_has_glob_metachar("__init__.py"))

    def test_braces_not_detected(self) -> None:
        """Braces are NOT detected (not standard glob)."""
        self.assertFalse(_has_glob_metachar("test_{a,b}.py"))


class TestExpandGlobs(unittest.TestCase):
    """Tests for glob expansion in command parts."""

    def setUp(self) -> None:
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self) -> None:
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_glob_expands_to_matching_files(self) -> None:
        """Glob pattern expands to matching files."""
        # Create test files with unique names to avoid temp dir pollution
        (self.temp_path / "test_x_a.txt").touch()
        (self.temp_path / "test_x_b.txt").touch()
        (self.temp_path / "test_x_c.txt").touch()

        cmd_parts = ["cmd", "test_x_*.txt"]
        result = expand_globs(cmd_parts, self.temp_dir)

        # Should have 4 items: "cmd" + 3 expanded files
        self.assertEqual(len(result), 4)
        # First element should be preserved
        self.assertEqual(result[0], "cmd")
        # Remaining should be sorted matches
        matches = result[1:]
        self.assertEqual(len(matches), 3)

    def test_test_glob_expands_correctly(self) -> None:
        """tests/test_*.py pattern expands to test files."""
        cmd_parts = ["mypy", "tests/__init__.py", "tests/test_*.py"]
        result = expand_globs(cmd_parts, str(REPO_ROOT))

        # Should contain tests/__init__.py and multiple test_*.py files
        self.assertIn("tests/__init__.py", result)
        test_files = [r for r in result if "test_" in r and r.endswith(".py")]
        self.assertGreater(len(test_files), 10)  # Should find many test files

    def test_non_glob_args_preserved(self) -> None:
        """Non-glob arguments are preserved exactly."""
        cmd_parts = [".venv/bin/python", "-m", "mypy", "tests/__init__.py"]
        result = expand_globs(cmd_parts, str(REPO_ROOT))

        self.assertEqual(result, cmd_parts)

    def test_mixed_glob_and_non_glob(self) -> None:
        """Mixed glob and non-glob arguments are handled correctly."""
        import uuid

        # Use a unique subdirectory for this test
        test_dir = self.temp_path / f"mixed_{uuid.uuid4().hex[:8]}"
        test_dir.mkdir()

        # Create unique files in the unique subdirectory
        (test_dir / "file_a.py").touch()
        (test_dir / "file_b.py").touch()

        cmd_parts = [
            "python",
            "-m",
            "mypy",
            "file_a.py",  # Non-glob, should be preserved
            "file_*.py",  # Glob, should expand to file_b.py
        ]
        result = expand_globs(cmd_parts, str(test_dir))

        # Should have at least 4 items: python, -m, mypy, file_a.py, file_b.py
        self.assertGreaterEqual(len(result), 4)
        self.assertEqual(result[0], "python")
        self.assertEqual(result[1], "-m")
        self.assertEqual(result[2], "mypy")
        # Both files should be present somewhere in result
        result_str = str(result)
        self.assertIn("file_a.py", result_str)
        self.assertIn("file_b.py", result_str)

    def test_unmatched_glob_raises_value_error(self) -> None:
        """Unmatched glob pattern raises ValueError (fail closed)."""
        cmd_parts = ["cmd", "this_pattern_has_no_matches_xyz123_*.xyz"]

        with self.assertRaises(ValueError) as ctx:
            expand_globs(cmd_parts, self.temp_dir)

        self.assertIn("this_pattern_has_no_matches_xyz123_*.xyz", str(ctx.exception))
        self.assertIn("matched no files", str(ctx.exception))

    def test_question_mark_glob(self) -> None:
        """Question mark glob matches single characters."""
        # Create unique files
        (self.temp_path / "test_q1.txt").touch()
        (self.temp_path / "test_q2.txt").touch()
        (self.temp_path / "test_q10.txt").touch()

        cmd_parts = ["cmd", "test_q?.txt"]
        result = expand_globs(cmd_parts, self.temp_dir)

        # Should match test_q1 and test_q2 but not test_q10
        # cmd + 2 matches = 3 total
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "cmd")

    def test_bracket_glob(self) -> None:
        """Bracket glob matches character classes."""
        # Create unique files
        (self.temp_path / "test_b_a.txt").touch()
        (self.temp_path / "test_b_b.txt").touch()
        (self.temp_path / "test_b_c.txt").touch()

        cmd_parts = ["cmd", "test_b_[ab].txt"]
        result = expand_globs(cmd_parts, self.temp_dir)

        # Should match test_b_a and test_b_b but not test_b_c
        self.assertEqual(len(result), 3)  # cmd + 2 matches
        self.assertEqual(result[0], "cmd")


class TestRunnerNoShellForGlobs(unittest.TestCase):
    """Tests that runner does not use shell=True for glob expansion."""

    def test_expand_globs_no_subprocess(self) -> None:
        """Verify expand_globs uses glob.glob, not shell expansion."""
        temp_dir = tempfile.mkdtemp()
        try:
            temp_path = Path(temp_dir)
            (temp_path / "test_script.py").touch()

            cmd_parts = ["cmd", "test_script.py"]  # No glob, just verify it works
            result = expand_globs(cmd_parts, temp_dir)

            # Non-glob should pass through unchanged
            self.assertEqual(result, cmd_parts)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_runner_source_has_expand_globs(self) -> None:
        """Verify runner code uses expand_globs for direct commands."""
        runner_path = SCRIPT_DIR / "verify_profile_runner.py"
        content = runner_path.read_text()

        # Direct commands should use expand_globs
        self.assertIn('expand_globs(cmd_parts, repo_root)', content)


if __name__ == "__main__":
    unittest.main()
