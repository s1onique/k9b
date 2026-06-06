"""Unit tests for structured output line checker.

Tests cover:
- valid JSON object line passes
- multiple valid JSON object lines pass
- blank lines pass
- malformed JSON fails
- JSON array fails
- JSON string fails
- raw Forbidden line fails
- Kubernetes Forbidden stderr-style line fails
- traceback line fails
- default Python logger text line fails
- arbitrary print line fails
- diagnostics include line number and rejected content
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Import the checker module
from scripts.check_structured_output_lines import check_file, check_line, check_stdin


class TestStructuredOutputChecker(unittest.TestCase):
    """Tests for structured output line checker."""

    def test_valid_json_object_line_passes(self) -> None:
        """Valid JSON object line should pass."""
        line = '{"event":"health_loop.tick.completed","level":"info"}'
        accepted, _ = check_line(line, "test", 1)
        self.assertTrue(accepted)

    def test_valid_json_object_with_metadata_passes(self) -> None:
        """Valid JSON object with multiple fields should pass."""
        line = '{"timestamp":"2026-01-01T00:00:00Z","component":"health-loop","severity":"INFO","message":"Health run started","run_label":"test"}'
        accepted, _ = check_line(line, "test", 1)
        self.assertTrue(accepted)

    def test_multiple_valid_json_object_lines_pass(self) -> None:
        """Multiple valid JSON object lines should all pass."""
        lines = [
            '{"event":"start","level":"info"}',
            '{"event":"snapshot","level":"info"}',
            '{"event":"complete","level":"info"}',
        ]
        for i, line in enumerate(lines, start=1):
            accepted, _ = check_line(line, "test", i)
            self.assertTrue(accepted, f"Line {i} should pass: {line}")

    def test_blank_lines_pass(self) -> None:
        """Blank lines should pass."""
        accepted, _ = check_line("", "test", 1)
        self.assertTrue(accepted)
        accepted, _ = check_line("   ", "test", 1)
        self.assertTrue(accepted)
        accepted, _ = check_line("\t", "test", 1)
        self.assertTrue(accepted)

    def test_malformed_json_fails(self) -> None:
        """Malformed JSON should fail."""
        line = '{not valid json}'
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_json_array_fails(self) -> None:
        """JSON array should fail."""
        line = '["json", "array"]'
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected JSON array", diag)

    def test_json_string_fails(self) -> None:
        """JSON string should fail."""
        line = '"json string"'
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected JSON string", diag)

    def test_raw_forbidden_line_fails(self) -> None:
        """Raw Forbidden line should fail."""
        line = "Forbidden"
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_kubernetes_forbidden_stderr_style_fails(self) -> None:
        """Kubernetes Forbidden stderr-style line should fail."""
        line = "Error from server (Forbidden): pods is forbidden"
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_traceback_line_fails(self) -> None:
        """Traceback line should fail."""
        line = 'Traceback (most recent call last):'
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_default_python_logger_text_line_fails(self) -> None:
        """Default Python logger text line should fail."""
        line = "WARNING:k8s_diag_agent.external_analysis.foo: Forbidden"
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_arbitrary_print_line_fails(self) -> None:
        """Arbitrary print line should fail."""
        line = "plain print output"
        accepted, diag = check_line(line, "test", 1)
        self.assertFalse(accepted)
        self.assertIn("rejected non-JSON", diag)

    def test_diagnostics_include_line_number(self) -> None:
        """Diagnostics should include line number."""
        line = "forbidden"
        _, diag = check_line(line, "testfile.txt", 42)
        self.assertIn("42", diag)
        self.assertIn("testfile.txt", diag)

    def test_diagnostics_include_rejected_content(self) -> None:
        """Diagnostics should include rejected content."""
        line = "Error from server: some error message"
        _, diag = check_line(line, "test", 1)
        self.assertIn("Error from server: some error message", diag)

    def test_diagnostics_truncate_long_lines(self) -> None:
        """Diagnostics should truncate long lines to 100 chars."""
        long_line = "x" * 200
        _, diag = check_line(long_line, "test", 1)
        self.assertIn("xxx", diag)
        self.assertLessEqual(len(diag.split(": ")[-1]), 100)


class TestStructuredOutputCheckerFileMode(unittest.TestCase):
    """Tests for structured output checker file mode."""

    def test_check_file_all_valid(self) -> None:
        """File with all valid JSON objects should pass."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write('{"event":"start"}\n')
            f.write('{"event":"complete"}\n')
            f.write("\n")
            f.write('{"event":"next"}\n')
            temp_path = Path(f.name)

        try:
            passed, failed, diagnostics = check_file(temp_path)
            # 4 lines total: 3 valid JSON + 1 blank line (blank lines also pass)
            self.assertEqual(passed, 4)
            self.assertEqual(failed, 0)
            self.assertEqual(diagnostics, [])
        finally:
            temp_path.unlink()

    def test_check_file_with_rejections(self) -> None:
        """File with some invalid lines should fail."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write('{"event":"valid"}\n')
            f.write("Forbidden\n")
            f.write('{"event":"also_valid"}\n')
            f.write("Error: something failed\n")
            temp_path = Path(f.name)

        try:
            passed, failed, diagnostics = check_file(temp_path)
            self.assertEqual(passed, 2)
            self.assertEqual(failed, 2)
            self.assertEqual(len(diagnostics), 2)
            self.assertTrue(any("Forbidden" in d for d in diagnostics))
            self.assertTrue(any("Error: something failed" in d for d in diagnostics))
        finally:
            temp_path.unlink()

    def test_check_file_includes_path_in_diagnostics(self) -> None:
        """Diagnostics should include the file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("bad line\n")
            temp_path = Path(f.name)

        try:
            _, _, diagnostics = check_file(temp_path)
            self.assertEqual(len(diagnostics), 1)
            self.assertIn(str(temp_path), diagnostics[0])
        finally:
            temp_path.unlink()


class TestStructuredOutputCheckerStdinMode(unittest.TestCase):
    """Tests for structured output checker stdin mode."""

    def test_stdin_valid_lines(self) -> None:
        """Valid JSON from stdin should pass."""
        import io

        input_data = '{"event":"start"}\n{"event":"complete"}\n'
        stdin_mock = io.StringIO(input_data)
        old_stdin = sys.stdin
        sys.stdin = stdin_mock

        try:
            passed, failed, diagnostics = check_stdin()
            self.assertEqual(passed, 2)
            self.assertEqual(failed, 0)
        finally:
            sys.stdin = old_stdin

    def test_stdin_mixed_lines(self) -> None:
        """Mixed valid/invalid JSON from stdin should count failures."""
        import io

        input_data = '{"valid":true}\nForbidden\nalso valid: true\n'
        stdin_mock = io.StringIO(input_data)
        old_stdin = sys.stdin
        sys.stdin = stdin_mock

        try:
            passed, failed, diagnostics = check_stdin()
            self.assertEqual(passed, 1)
            self.assertEqual(failed, 2)
            self.assertTrue(any("Forbidden" in d for d in diagnostics))
            self.assertTrue(any("also valid" in d for d in diagnostics))
        finally:
            sys.stdin = old_stdin


if __name__ == "__main__":
    unittest.main()
