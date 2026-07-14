"""SEAM01 exit-code invariant tests for the promotion-diagnosis handoff verifier.

Tests prove the verifier's exit-code invariant properties.

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R19
"""

from __future__ import annotations

import textwrap
import unittest

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)


class SEAM01ExitCodeInvariantTests(_SubprocessMixin, unittest.TestCase):
    """Verify exit-code invariant properties."""

    def test_clean_source_returns_0(self) -> None:
        """Clean source with no violations returns exit 0."""
        body = textwrap.dedent(
            """
            def process(value: int) -> int:
                return value + 1
            """
        )
        with _FixtureTree(
            "clean/valid.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("PASS", proc.stdout)
            self.assertNotIn("FAIL", proc.stdout)

    def test_stderr_empty_on_clean_source(self) -> None:
        """Clean source produces no stderr output."""
        body = textwrap.dedent(
            """
            def foo():
                return 42
            """
        )
        with _FixtureTree(
            "clean/foo.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.stderr, "")

    def test_no_traceback_on_syntax_error(self) -> None:
        """Syntax errors do not emit Python tracebacks."""
        body = "def bad(  \n"
        with _FixtureTree(
            "syntax/bad.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertNotIn("traceback", proc.stderr.lower())
            self.assertNotIn("  File ", proc.stderr)
            self.assertNotIn("    raise", proc.stderr)

    def test_no_traceback_on_null_byte(self) -> None:
        """Null bytes do not emit Python tracebacks."""
        body = "x = 1\x00\n"
        with _FixtureTree(
            "syntax/null.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertNotIn("traceback", proc.stderr.lower())
            self.assertNotIn("  File ", proc.stderr)
            self.assertNotIn("    raise", proc.stderr)


if __name__ == "__main__":
    unittest.main()
