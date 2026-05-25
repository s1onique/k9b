"""Unit tests for check_llm_friendly_files.py."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path for imports (must be before module imports)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))  # noqa: E402

from check_llm_friendly_files import (  # noqa: E402
    ALLOWLIST,
    check_file,
    count_physical_lines,
    is_allowlisted,
    is_excluded,
)


class TestCountPhysicalLines(unittest.TestCase):
    """Tests for count_physical_lines function."""

    def test_counts_physical_lines(self):
        """Count all physical lines including empty."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\nline2\n\nline4\n")
            f.flush()
            path = Path(f.name)

        try:
            count = count_physical_lines(path)
            self.assertEqual(count, 4)  # All 4 lines, including empty
        finally:
            os.unlink(f.name)

    def test_counts_whitespace_only_lines(self):
        """Physical lines with whitespace are counted."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("line1\n   \n\n")
            f.flush()
            path = Path(f.name)

        try:
            count = count_physical_lines(path)
            self.assertEqual(count, 3)  # All 3 physical lines
        finally:
            os.unlink(f.name)

    def test_returns_zero_for_binary(self):
        """Binary files return 0."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            f.flush()
            path = Path(f.name)

        try:
            count = count_physical_lines(path)
            self.assertEqual(count, 0)
        finally:
            os.unlink(f.name)


class TestIsExcluded(unittest.TestCase):
    """Tests for is_excluded function."""

    def setUp(self):
        """Create a temporary root directory."""
        self.root = Path(tempfile.mkdtemp())

    def test_excludes_git_directory(self):
        """Files in .git are excluded."""
        path = self.root / ".git" / "config"
        self.assertTrue(is_excluded(path, self.root))

    def test_excludes_node_modules(self):
        """Files in node_modules are excluded."""
        path = self.root / "node_modules" / "package" / "index.js"
        self.assertTrue(is_excluded(path, self.root))

    def test_excludes_venv(self):
        """Files in .venv are excluded."""
        path = self.root / ".venv" / "lib" / "site.py"
        self.assertTrue(is_excluded(path, self.root))

    def test_excludes_runs_directory(self):
        """Files in runs/ are excluded."""
        path = self.root / "runs" / "health" / "artifact.json"
        self.assertTrue(is_excluded(path, self.root))

    def test_excludes_package_lock(self):
        """package-lock.json is excluded."""
        path = self.root / "package-lock.json"
        self.assertTrue(is_excluded(path, self.root))

    def test_includes_regular_python_file(self):
        """Regular Python files are not excluded."""
        path = self.root / "src" / "module.py"
        self.assertFalse(is_excluded(path, self.root))

    def test_includes_regular_typescript_file(self):
        """Regular TypeScript files are not excluded."""
        path = self.root / "frontend" / "src" / "App.tsx"
        self.assertFalse(is_excluded(path, self.root))

    def test_includes_regular_shell_file(self):
        """Regular shell scripts are not excluded."""
        path = self.root / "scripts" / "build.sh"
        self.assertFalse(is_excluded(path, self.root))

    def test_includes_fixtures_directory(self):
        """Files in fixtures/ are NOT excluded (fixture modules need checking)."""
        path = self.root / "fixtures" / "data.py"
        self.assertFalse(is_excluded(path, self.root))

    def test_includes_snapshots_directory(self):
        """Files in snapshots/ are NOT excluded (data files need checking)."""
        path = self.root / "snapshots" / "baseline.json"
        self.assertFalse(is_excluded(path, self.root))

    def test_includes_evals_directory(self):
        """Files in evals/ are NOT excluded (test data needs checking)."""
        path = self.root / "evals" / "test_scenario.yaml"
        self.assertFalse(is_excluded(path, self.root))


class TestIsAllowlisted(unittest.TestCase):
    """Tests for is_allowlisted function."""

    def setUp(self):
        """Create a temporary root directory."""
        self.root = Path(tempfile.mkdtemp())

    def test_not_allowlisted_without_entry(self):
        """Files not in allowlist return False."""
        path = self.root / "src" / "module.py"
        is_allowed, reason = is_allowlisted(path, self.root, ALLOWLIST)
        self.assertFalse(is_allowed)
        self.assertIsNone(reason)

    def test_allowlisted_with_entry(self):
        """Files in allowlist return True with reason."""
        original_allowlist = ALLOWLIST.copy()
        try:
            ALLOWLIST.clear()
            ALLOWLIST.append((str(self.root / "src" / "legacy.py"), "[EXTRACTION] Legacy module"))

            path = self.root / "src" / "legacy.py"
            is_allowed, reason = is_allowlisted(path, self.root, ALLOWLIST)
            self.assertTrue(is_allowed)
            self.assertEqual(reason, "[EXTRACTION] Legacy module")
        finally:
            ALLOWLIST.clear()
            ALLOWLIST.extend(original_allowlist)


class TestCheckFile(unittest.TestCase):
    """Tests for check_file function."""

    def setUp(self):
        """Create a temporary root directory."""
        self.root = Path(tempfile.mkdtemp())

    def test_passes_small_file(self):
        """Files under warning threshold pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Small module\n")
            for i in range(50):
                f.write(f"def func_{i}():\n    pass\n")
            f.flush()
            path = Path(f.name)

        try:
            passed, msg = check_file(path, self.root, 300, 500, ALLOWLIST)
            self.assertTrue(passed)
            self.assertIn("OK", msg)
        finally:
            os.unlink(f.name)

    def test_warns_above_warning_threshold(self):
        """Files above warning threshold trigger warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Generate ~250 physical lines (under 500 max but over 300 warn)
            for i in range(250):
                f.write(f"def func_{i}():\n    pass\n")
            f.flush()
            path = Path(f.name)

        try:
            passed, msg = check_file(path, self.root, 300, 500, ALLOWLIST)
            self.assertFalse(passed)
            # Message should indicate warning threshold exceeded
            self.assertIn("warn >", msg)
        finally:
            os.unlink(f.name)

    def test_fails_above_max_threshold(self):
        """Files above max threshold cause failure."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            for i in range(600):
                f.write(f"def func_{i}():\n    pass\n")
            f.flush()
            path = Path(f.name)

        try:
            passed, msg = check_file(path, self.root, 300, 500, ALLOWLIST)
            self.assertFalse(passed)
            self.assertIn("exceeds", msg)
        finally:
            os.unlink(f.name)

    def test_allowlisted_file_passes(self):
        """Allowlisted files always pass."""
        original_allowlist = ALLOWLIST.copy()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                for i in range(1000):
                    f.write(f"def func_{i}():\n    pass\n")
                f.flush()
                path = Path(f.name)

            try:
                # Add the actual temp file path to allowlist
                ALLOWLIST.clear()
                ALLOWLIST.append((str(path), "[EXTRACTION] Legacy module pending extraction"))

                passed, msg = check_file(path, self.root, 300, 500, ALLOWLIST)
                self.assertTrue(passed)
                self.assertIn("allowlisted", msg)
            finally:
                os.unlink(f.name)
        finally:
            ALLOWLIST.clear()
            ALLOWLIST.extend(original_allowlist)

    def test_binary_file_skipped(self):
        """Binary files are skipped (no count)."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02" * 100)
            f.flush()
            path = Path(f.name)

        try:
            passed, msg = check_file(path, self.root, 300, 500, ALLOWLIST)
            self.assertTrue(passed)
            self.assertIn("binary", msg)
        finally:
            os.unlink(f.name)


class TestAllowlistValidation(unittest.TestCase):
    """Tests for allowlist validation."""

    def test_entries_need_sufficient_reason(self):
        """Allowlist entries without sufficient reason cause error."""
        from check_llm_friendly_files import validate_allowlist

        original_allowlist = ALLOWLIST.copy()
        try:
            ALLOWLIST.clear()
            ALLOWLIST.append(("src/legacy.py", "TODO"))  # Reason too short

            errors = validate_allowlist(Path("/tmp"), ALLOWLIST)
            self.assertGreater(len(errors), 0)
            self.assertTrue(any("insufficient" in err for err in errors))
        finally:
            ALLOWLIST.clear()
            ALLOWLIST.extend(original_allowlist)

    def test_valid_entries_pass(self):
        """Valid allowlist entries pass validation."""
        from check_llm_friendly_files import validate_allowlist

        original_allowlist = ALLOWLIST.copy()
        try:
            ALLOWLIST.clear()
            ALLOWLIST.append(("src/k8s_diag_agent/llm/__init__.py", "[EXTRACTION] Pending extraction to focused modules"))

            # Use project root where the file exists
            errors = validate_allowlist(Path(__file__).parent.parent.parent, ALLOWLIST)
            self.assertEqual(len(errors), 0)
        finally:
            ALLOWLIST.clear()
            ALLOWLIST.extend(original_allowlist)


if __name__ == "__main__":
    unittest.main()