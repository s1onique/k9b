"""Tests for index-backed super fast path in build_runs_list().

These tests verify the key contract:
- When ui-index.json exists with recent_runs_summary, default /api/runs
  must use index_super_fast_path and parse zero review files.
- Empty recent_runs_summary is a valid fast result, not fallback.
- Fallback remains available when index is absent/malformed.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import build_runs_list

from .test_ui_api import RunsListTests


class TestIndexSuperFastPath(RunsListTests):
    """Regression tests for index-backed super fast path."""

    def test_index_path_parses_zero_review_files(self) -> None:
        """When ui-index.json has recent_runs_summary, should parse zero review files.

        This is the key contract: the index path must not scan review files.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            reviews_dir = health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create ui-index.json with recent_runs_summary (no review files needed)
            ui_index = {
                "run": {
                    "run_id": "latest-run",
                    "run_label": "Latest Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "collector_version": "1.0.0",
                    "cluster_count": 5,
                },
                "recent_runs_summary": {
                    "runs": [
                        {
                            "run_id": "run-20260430T120000Z",
                            "run_label": "Run 2026-04-30",
                            "timestamp": "2026-04-30T12:00:00Z",
                            "cluster_count": 5,
                        },
                        {
                            "run_id": "run-20260429T120000Z",
                            "run_label": "Run 2026-04-29",
                            "timestamp": "2026-04-29T12:00:00Z",
                            "cluster_count": 4,
                        },
                    ],
                    "total_count": 2,
                    "generated_at": "2026-04-30T12:00:00Z",
                    "version": 1,
                },
            }
            (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

            # Create review files that would be expensive to parse
            # They should NOT be touched by the index path
            for i in range(20):
                review_path = reviews_dir / f"run-2026-04-{25+i:02d}T120000Z-review.json"
                review_path.write_text(json.dumps({
                    "run_id": f"run-2026-04-{25+i:02d}T120000Z",
                    "timestamp": f"2026-04-{25+i:02d}T12:00:00Z",
                    "run_label": f"Old Run {i}",
                    "cluster_count": i,
                    "data": "x" * 1000,  # Make it expensive
                }), encoding="utf-8")

            # Call build_runs_list without _timings
            result = build_runs_list(runs_dir, limit=10)

            # Verify results come from index
            self.assertEqual(len(result["runs"]), 2)
            self.assertEqual(result["totalCount"], 2)
            self.assertEqual(result["returnedCount"], 2)
            self.assertFalse(result["hasMore"])

            # Verify run data matches index
            run_ids = {r["runId"] for r in result["runs"]}
            self.assertIn("run-20260430T120000Z", run_ids)
            self.assertIn("run-20260429T120000Z", run_ids)

    def test_index_path_with_timings_verifies_zero_files(self) -> None:
        """Verify index path produces correct timings metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            reviews_dir = health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create ui-index.json with recent_runs_summary
            ui_index = {
                "run": {
                    "run_id": "latest-run",
                    "run_label": "Latest Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "collector_version": "1.0.0",
                    "cluster_count": 5,
                },
                "recent_runs_summary": {
                    "runs": [
                        {
                            "run_id": "run-20260430T120000Z",
                            "run_label": "Run 2026-04-30",
                            "timestamp": "2026-04-30T12:00:00Z",
                            "cluster_count": 5,
                        },
                    ],
                    "total_count": 1,
                    "generated_at": "2026-04-30T12:00:00Z",
                    "version": 1,
                },
            }
            (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

            # Create review files that should NOT be touched
            for i in range(50):
                review_path = reviews_dir / f"run-2026-04-{i:02d}T120000Z-review.json"
                review_path.write_text(json.dumps({
                    "run_id": f"run-2026-04-{i:02d}T120000Z",
                    "timestamp": f"2026-04-{i:02d}T12:00:00Z",
                    "run_label": f"Old Run {i}",
                    "cluster_count": i,
                }), encoding="utf-8")

            result, timings = build_runs_list(runs_dir, _timings=True)

            # Key assertions: index path must show zero review activity
            self.assertEqual(timings.get("path_strategy"), "index_super_fast_path")
            self.assertEqual(timings.get("reviews_parsed"), 0)
            self.assertEqual(timings.get("reviews_files_found"), 0)
            self.assertEqual(timings.get("batch_plan_files_found"), 0)
            self.assertEqual(timings.get("batch_exec_files_found"), 0)
            self.assertEqual(timings.get("rows_returned"), 1)
            self.assertEqual(timings.get("rows_considered"), 1)

    def test_empty_index_is_valid_result_not_fallback(self) -> None:
        """Empty recent_runs_summary should return valid result via index path.

        This is critical: a fresh install with no runs should not fall back
        to scanning review files (which would be empty anyway but wasteful).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            reviews_dir = health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create ui-index.json with empty recent_runs_summary
            ui_index = {
                "run": {
                    "run_id": "latest-run",
                    "run_label": "Latest Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "collector_version": "1.0.0",
                    "cluster_count": 0,
                },
                "recent_runs_summary": {
                    "runs": [],
                    "total_count": 0,
                    "generated_at": "2026-04-30T12:00:00Z",
                    "version": 1,
                },
            }
            (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

            # Create review files that should NOT be touched
            for i in range(10):
                review_path = reviews_dir / f"run-2026-04-{i:02d}T120000Z-review.json"
                review_path.write_text(json.dumps({
                    "run_id": f"run-2026-04-{i:02d}T120000Z",
                    "timestamp": f"2026-04-{i:02d}T12:00:00Z",
                    "run_label": f"Old Run {i}",
                    "cluster_count": i,
                }), encoding="utf-8")

            result, timings = build_runs_list(runs_dir, _timings=True)

            # Must use index path, not fallback
            self.assertEqual(timings.get("path_strategy"), "index_super_fast_path")
            self.assertEqual(timings.get("reviews_parsed"), 0)

            # Verify empty result
            self.assertEqual(len(result["runs"]), 0)
            self.assertEqual(result["totalCount"], 0)
            self.assertFalse(result["hasMore"])

    def test_fallback_when_index_absent(self) -> None:
        """When ui-index.json is absent, should fall back to review streaming."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            reviews_dir = health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create review files (no ui-index.json)
            for i in range(3):
                review_path = reviews_dir / f"run-2026-04-{i:02d}T120000Z-review.json"
                review_path.write_text(json.dumps({
                    "run_id": f"run-2026-04-{i:02d}T120000Z",
                    "timestamp": f"2026-04-{i:02d}T12:00:00Z",
                    "run_label": f"Run {i}",
                    "cluster_count": i + 1,
                }), encoding="utf-8")

            result, timings = build_runs_list(runs_dir, _timings=True)

            # Must use fallback path
            self.assertEqual(timings.get("path_strategy"), "review_streaming_super_fast_path")
            self.assertGreater(timings.get("reviews_parsed", 0), 0)
            self.assertGreater(timings.get("reviews_files_found", 0), 0)

            # Verify results
            self.assertEqual(len(result["runs"]), 3)

    def test_fallback_when_index_malformed(self) -> None:
        """When ui-index.json is malformed, should fall back to review streaming."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            reviews_dir = health_dir / "reviews"
            reviews_dir.mkdir(parents=True)

            # Create malformed ui-index.json (no recent_runs_summary)
            (health_dir / "ui-index.json").write_text(json.dumps({
                "run": {"run_id": "latest"},
                # Missing recent_runs_summary
            }), encoding="utf-8")

            # Create review files
            for i in range(2):
                review_path = reviews_dir / f"run-2026-04-{i:02d}T120000Z-review.json"
                review_path.write_text(json.dumps({
                    "run_id": f"run-2026-04-{i:02d}T120000Z",
                    "timestamp": f"2026-04-{i:02d}T12:00:00Z",
                    "run_label": f"Run {i}",
                    "cluster_count": i + 1,
                }), encoding="utf-8")

            result, timings = build_runs_list(runs_dir, _timings=True)

            # Must use fallback path
            self.assertEqual(timings.get("path_strategy"), "review_streaming_super_fast_path")

    def test_index_path_skips_batch_eligibility(self) -> None:
        """Index path should always skip batch eligibility computation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            health_dir = runs_dir / "health"
            health_dir.mkdir(parents=True)

            # Create ui-index.json with recent_runs_summary
            ui_index = {
                "run": {"run_id": "latest", "run_label": "Latest", "timestamp": "2026-04-30T12:00:00Z", "collector_version": "1.0.0", "cluster_count": 5},
                "recent_runs_summary": {
                    "runs": [{"run_id": "run-20260430T120000Z", "run_label": "Run", "timestamp": "2026-04-30T12:00:00Z", "cluster_count": 5}],
                    "total_count": 1,
                    "generated_at": "2026-04-30T12:00:00Z",
                    "version": 1,
                },
            }
            (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

            result, timings = build_runs_list(runs_dir, _timings=True)

            # Index path should not look at batch files
            self.assertEqual(timings.get("batch_plan_files_found"), 0)
            self.assertEqual(timings.get("batch_exec_files_found"), 0)

            # Results should have unknown batch eligibility
            run = result["runs"][0]
            self.assertEqual(run["batchEligibility"], "unknown")
            self.assertFalse(run["batchExecutable"])
            self.assertEqual(run["batchEligibleCount"], 0)