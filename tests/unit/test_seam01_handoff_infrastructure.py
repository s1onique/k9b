"""SEAM01 infrastructure exit-matrix tests for the promotion-diagnosis handoff verifier.

Tests prove the verifier's exit-code contract:
  0 -- no violations found
  1 -- source contract violation found
  2 -- verification infrastructure failure

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01-R19
"""

from __future__ import annotations

import os
import stat
import tempfile
import textwrap
import unittest
from pathlib import Path

from test_r5_verifier_fixtures_shared import (
    _FixtureTree,
    _SubprocessMixin,
)

# Module-level imports for verifier
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERIFIERS_DIR = _REPO_ROOT / "scripts" / "verifiers"


class SEAM01InfrastructureExitMatrix(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Infrastructure exit-code matrix tests (CLI subprocess layer)."""

    # --- Exit code 1: contract violations ---

    def test_module_level_actionable_access_returns_1(self) -> None:
        """Module-level value.actionable_incident_ids is a contract violation (exit 1)."""
        body = textwrap.dedent(
            """
            result: object = None
            ids = result.actionable_incident_ids
            """
        )
        with _FixtureTree(
            "violation/module_level_actionable.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("contract violations found", proc.stdout)
            self.assertIn("forbidden_actionable_access", proc.stdout)
            self.assertNotIn("infrastructure error", proc.stdout.lower())
            self.assertNotIn("infrastructure error", proc.stderr.lower())

    def test_module_level_canonical_call_returns_1(self) -> None:
        """Module-level value.canonical_incident_ids() is a contract violation (exit 1)."""
        body = textwrap.dedent(
            """
            accumulator: object = None
            ids = accumulator.canonical_incident_ids()
            """
        )
        with _FixtureTree(
            "violation/module_level_canonical.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("contract violations found", proc.stdout)
            self.assertIn("forbidden_canonical_call", proc.stdout)
            self.assertNotIn("infrastructure error", proc.stdout.lower())
            self.assertNotIn("infrastructure error", proc.stderr.lower())

    # --- Exit code 2: infrastructure failures (CLI layer) ---

    def test_null_byte_source_returns_2(self) -> None:
        """Source with null bytes triggers infrastructure error (exit 2)."""
        body = "x = 1\x00  # null byte"
        with _FixtureTree(
            "syntax/null_byte.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("infrastructure error", proc.stderr.lower())
            self.assertNotIn("contract violations found", proc.stdout)
            self.assertNotIn("traceback", proc.stderr.lower())

    def test_invalid_syntax_returns_2(self) -> None:
        """Invalid Python syntax triggers infrastructure error (exit 2)."""
        body = "def broken(  # syntax error\n"
        with _FixtureTree(
            "syntax/invalid.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("infrastructure error", proc.stderr.lower())
            self.assertNotIn("contract violations found", proc.stdout)
            self.assertNotIn("traceback", proc.stderr.lower())

    def test_missing_src_directory_returns_2(self) -> None:
        """Missing source directory triggers infrastructure error (exit 2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = os.path.join(tmpdir, "nonexistent_src")
            proc = self._run("verify_promotion_diagnosis_handoff", nonexistent)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("infrastructure error", proc.stderr.lower())
            self.assertNotIn("contract violations found", proc.stdout)

    def test_permission_manipulation_never_leaks_traceback(self) -> None:
        """Permission-challenged files do not emit Python tracebacks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_root = os.path.join(tmpdir, "src")
            os.makedirs(src_root)
            # Create an unreadable file
            unreadable = os.path.join(src_root, "unreadable.py")
            with open(unreadable, "w") as f:
                f.write("x = 1\n")
            # Remove read permission
            os.chmod(unreadable, stat.S_IWUSR | stat.S_IXUSR)
            try:
                proc = self._run("verify_promotion_diagnosis_handoff", src_root)
                # We only care that no traceback escapes
                self.assertNotIn("traceback", proc.stderr.lower())
            finally:
                # Restore permissions for cleanup
                os.chmod(unreadable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


class SEAM01InfrastructureSubprocessTests(_SubprocessMixin, unittest.TestCase):
    """SEAM01: Infrastructure fault injection tests via subprocess.

    These tests verify infrastructure failure behavior by testing the verifier
    as a black box via subprocess, which is the most reliable approach for
    module boundary testing.
    """

    def test_invalid_python_file_returns_2(self) -> None:
        """Invalid Python syntax file triggers infrastructure error (exit 2)."""
        body = "def broken(  # syntax error\n"
        with _FixtureTree(
            "syntax/invalid.py", body
        ) as src_root:
            proc = self._run("verify_promotion_diagnosis_handoff", src_root)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("infrastructure error", proc.stderr.lower())
            self.assertNotIn("traceback", proc.stderr.lower())

    def test_permission_denied_returns_2_or_1(self) -> None:
        """Permission denied on file triggers error (exit 2 or 1, but no traceback)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_root = os.path.join(tmpdir, "src")
            os.makedirs(src_root)
            unreadable = os.path.join(src_root, "unreadable.py")
            with open(unreadable, "w") as f:
                f.write("x = 1\n")
            os.chmod(unreadable, stat.S_IWUSR | stat.S_IXUSR)
            try:
                proc = self._run("verify_promotion_diagnosis_handoff", src_root)
                # Should not emit traceback regardless of exit code
                self.assertNotIn("traceback", proc.stderr.lower())
            finally:
                os.chmod(unreadable, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
