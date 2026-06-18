"""Tests for is_safe_next_check_run_id function.

These tests verify that potentially unsafe run_ids are rejected
to prevent path traversal attacks through artifact paths.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.incident_next_check_artifacts import (
    is_safe_next_check_run_id,
    load_next_check_plan_payloads_for_incident,
)

from .incident_next_check_artifact_fixtures import (
    make_basic_plan_payload,
    make_incident_with_run_ids,
    write_plan_artifact,
)


class TestSafeNextCheckRunId(unittest.TestCase):
    """Tests for is_safe_next_check_run_id function."""

    def test_valid_run_id_accepted(self) -> None:
        """Valid run_ids must be accepted."""
        valid_ids = [
            "run-123",
            "run_abc",
            "RUN-123",
            "run.abc",
            "a",
            "A",
            "0",
            "run-123_abc.DEF",
        ]
        for run_id in valid_ids:
            with self.subTest(run_id=run_id):
                self.assertTrue(
                    is_safe_next_check_run_id(run_id),
                    f"Expected {run_id!r} to be safe",
                )

    def test_path_traversal_rejected(self) -> None:
        """Path traversal run_ids must be rejected."""
        self.assertFalse(is_safe_next_check_run_id("../evil"))
        self.assertFalse(is_safe_next_check_run_id(".."))

    def test_subdirectory_escaping_rejected(self) -> None:
        """Subdirectory escaping run_ids must be rejected."""
        self.assertFalse(is_safe_next_check_run_id("subdir/run-123"))
        self.assertFalse(is_safe_next_check_run_id("subdir\\run-123"))
        self.assertFalse(is_safe_next_check_run_id("sub/dir/run-123"))

    def test_absolute_path_rejected(self) -> None:
        """Absolute path run_ids must be rejected."""
        self.assertFalse(is_safe_next_check_run_id("/tmp/run-123"))
        self.assertFalse(is_safe_next_check_run_id("/absolute/path"))
        self.assertFalse(is_safe_next_check_run_id("C:\\windows\\path"))

    def test_empty_run_id_rejected(self) -> None:
        """Empty run_id must be rejected."""
        self.assertFalse(is_safe_next_check_run_id(""))
        self.assertFalse(is_safe_next_check_run_id(None))

    def test_special_characters_rejected(self) -> None:
        """Special characters must be rejected."""
        special_chars = [
            ("run$123", "$"),
            ("run!123", "!"),
            ("run@123", "@"),
            ("run#123", "#"),
            ("run%123", "%"),
            ("run&123", "&"),
            ("run*123", "*"),
            ("run(123", "("),
            ("run)123", ")"),
        ]
        for run_id, char in special_chars:
            with self.subTest(run_id=run_id, char=char):
                self.assertFalse(
                    is_safe_next_check_run_id(run_id),
                    f"Expected {run_id!r} to be rejected (contains {char!r})",
                )

    def test_whitespace_rejected(self) -> None:
        """Whitespace in run_id must be rejected."""
        self.assertFalse(is_safe_next_check_run_id("run 123"))
        self.assertFalse(is_safe_next_check_run_id("run\t123"))
        self.assertFalse(is_safe_next_check_run_id("run\n123"))

    def test_loader_skips_unsafe_run_ids(self) -> None:
        """Loader must skip unsafe run_ids without path construction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            external_dir.mkdir(parents=True, exist_ok=True)

            # Create incident with mixed safe/unsafe run_ids
            incident = make_incident_with_run_ids([
                "run-safe",  # Safe
                "../evil",   # Unsafe - should be skipped
                "run-safe-2",  # Safe
            ])

            # Write only safe artifacts
            write_plan_artifact(external_dir, "run-safe", make_basic_plan_payload("run-safe"))
            write_plan_artifact(external_dir, "run-safe-2", make_basic_plan_payload("run-safe-2"))

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            # Should only load 2 safe artifacts, skip the unsafe one
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["run_id"], "run-safe")
            self.assertEqual(result[1]["run_id"], "run-safe-2")


if __name__ == "__main__":
    unittest.main()
