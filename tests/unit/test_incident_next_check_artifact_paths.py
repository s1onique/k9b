"""Tests for next_check_plan_path_for_run function.

These tests verify path construction is correct and returns None
for potentially unsafe run_ids that could cause path traversal.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from k8s_diag_agent.collect.incident_next_check_artifacts import next_check_plan_path_for_run


class TestNextCheckPlanPathForRun(unittest.TestCase):
    """Tests for next_check_plan_path_for_run function."""

    def test_constructs_expected_path(self) -> None:
        """next_check_plan_path_for_run must construct correct path."""
        external_dir = Path("/runs/health/external-analysis")
        result = next_check_plan_path_for_run(external_dir, "run-123")
        self.assertEqual(result, Path("/runs/health/external-analysis/run-123-next-check-plan.json"))

    def test_valid_run_id_complex(self) -> None:
        """next_check_plan_path_for_run must construct path for complex valid run_id."""
        external_dir = Path("/runs/health/external-analysis")
        result = next_check_plan_path_for_run(external_dir, "run-123_abc.DEF")
        self.assertEqual(result, Path("/runs/health/external-analysis/run-123_abc.DEF-next-check-plan.json"))

    def test_returns_none_for_path_traversal(self) -> None:
        """next_check_plan_path_for_run must return None for path traversal run_id."""
        external_dir = Path("/runs/health/external-analysis")
        result = next_check_plan_path_for_run(external_dir, "../evil")
        self.assertIsNone(result)

    def test_returns_none_for_subdirectory(self) -> None:
        """next_check_plan_path_for_run must return None for subdirectory run_id."""
        external_dir = Path("/runs/health/external-analysis")
        result = next_check_plan_path_for_run(external_dir, "subdir/run-123")
        self.assertIsNone(result)

    def test_returns_none_for_absolute_path(self) -> None:
        """next_check_plan_path_for_run must return None for absolute path run_id."""
        external_dir = Path("/runs/health/external-analysis")
        result = next_check_plan_path_for_run(external_dir, "/tmp/run-123")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
