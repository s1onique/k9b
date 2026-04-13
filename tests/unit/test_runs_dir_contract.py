"""Tests for the runs-dir contract normalization and validation.

This module tests that the UI/backend correctly handle the runs_dir contract:
- Canonical: parent 'runs' directory
- Internal: 'runs/health/' subdirectory

The doubled-path bug occurs when users mistakenly pass runs/health (the internal
subdirectory) instead of runs (the parent directory). This causes the UI to look
for runs/health/health/... which doesn't exist.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.ui.server import _normalize_runs_dir, _validate_runs_dir


class TestRunsDirNormalization(unittest.TestCase):
    """Tests for runs_dir normalization logic."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_normalize_returns_parent_when_passed_health_leaf(self) -> None:
        """If user passes runs/health, normalize to parent runs."""
        runs_health = self.tmpdir / "runs" / "health"
        runs_health.mkdir(parents=True)

        result = _normalize_runs_dir(runs_health)

        # Verify name is "runs" after normalization
        self.assertEqual(result.name, "runs")

    def test_normalize_passes_through_parent_runs(self) -> None:
        """If user passes parent runs, return unchanged."""
        runs_dir = self.tmpdir / "runs"
        runs_dir.mkdir(parents=True)

        result = _normalize_runs_dir(runs_dir)

        # Should be a "runs" directory
        self.assertEqual(result.name, "runs")

    def test_normalize_handles_deeply_nested_health(self) -> None:
        """If user passes runs/health (and it resolves to a health dir), normalize."""
        # Create runs/health structure
        runs_dir = self.tmpdir / "runs"
        health_dir = runs_dir / "health"
        health_dir.mkdir(parents=True)

        # Also create a deeper health dir to test - this should NOT normalize
        # because runs/health is already the expected structure
        deeper_dir = self.tmpdir / "runs" / "health" / "nested"
        deeper_dir.mkdir(parents=True)

        result = _normalize_runs_dir(health_dir)

        # Should be normalized to "runs" (parent of "health")
        self.assertEqual(result.name, "runs")


class TestRunsDirValidation(unittest.TestCase):
    """Tests for runs_dir validation logic."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_validate_passes_for_canonical_structure(self) -> None:
        """Valid runs dir has runs/health/ subdirectory."""
        runs_dir = self.tmpdir / "runs"
        health_dir = runs_dir / "health"
        health_dir.mkdir(parents=True)

        # Should not raise any exception
        _validate_runs_dir(runs_dir)

    def test_validate_warns_for_empty_runs_dir(self) -> None:
        """Warn when runs dir doesn't exist yet (fresh startup case)."""
        runs_dir = self.tmpdir / "runs"

        # Should not raise but may log warning
        _validate_runs_dir(runs_dir)

    def test_validate_warns_for_misconfigured_runs(self) -> None:
        """Warn when runs exists but no health subdir (potential misconfig)."""
        runs_dir = self.tmpdir / "runs"
        runs_dir.mkdir(parents=True)
        # Create some content but no health subdir
        (runs_dir / "some-other-dir").mkdir()

        # Should not raise but may log warning
        _validate_runs_dir(runs_dir)


class TestRunsDirContractIntegration(unittest.TestCase):
    """Integration tests for the runs_dir contract with actual UI flow.

    These tests verify that the normalization works correctly when the
    server processes requests.
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ui_index_loaded_from_normalized_runs_dir(self) -> None:
        """When runs_dir is normalized, server loads ui-index.json from runs/health/."""
        from k8s_diag_agent.health.ui import write_health_ui_index
        from k8s_diag_agent.ui.model import load_ui_index

        # Create canonical structure: runs/ with health/ subdirectory
        runs_dir = self.tmpdir / "runs"
        health_dir = runs_dir / "health"
        health_dir.mkdir(parents=True)

        # Write ui-index.json to the health directory (the correct location)
        write_health_ui_index(
            health_dir,
            run_id="test-run",
            run_label="test",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
        )

        # Normalize - this is what the server does
        normalized = _normalize_runs_dir(health_dir)

        # The server now adds /health suffix when loading ui-index.json
        # So we test that load_ui_index(normalized / "health") finds the file
        index = load_ui_index(normalized / "health")

        self.assertIsNotNone(index)
        assert isinstance(index, dict)
        assert isinstance(index.get("run"), dict)
        self.assertEqual(index["run"]["run_id"], "test-run")

    def test_doubled_path_bug_prevented(self) -> None:
        """Simulate the doubled-path bug: passes runs/health and expects it to work.

        Before the fix, passing runs/health would cause the server to look for
        runs/health/health/ui-index.json (doubled path). After the fix, it should
        normalize to runs and find runs/health/ui-index.json correctly.
        """
        from k8s_diag_agent.health.ui import write_health_ui_index
        from k8s_diag_agent.ui.model import load_ui_index

        # Create the canonical structure
        runs_dir = self.tmpdir / "runs"
        health_dir = runs_dir / "health"
        health_dir.mkdir(parents=True)

        # Write index to the correct location
        write_health_ui_index(
            health_dir,
            run_id="doubled-path-test",
            run_label="doubled-path-test",
            collector_version="1.0.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[],
        )

        # Simulate user mistakenly passing runs/health
        leaf_path = health_dir  # This is runs/health

        # Normalize - this is what the server should do
        normalized = _normalize_runs_dir(leaf_path)

        # The server now adds /health suffix when loading ui-index.json
        # This is what prevents the doubled-path bug
        index = load_ui_index(normalized / "health")

        self.assertIsNotNone(index)
        assert isinstance(index, dict)
        assert isinstance(index.get("run"), dict)
        self.assertEqual(index["run"]["run_id"], "doubled-path-test")
        # Before the fix, the server would have looked in
        # runs/health/health/ui-index.json which doesn't exist


if __name__ == "__main__":
    unittest.main()