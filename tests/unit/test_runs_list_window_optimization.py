"""Test that /api/runs execution count derivation only parses artifacts for returned window.

This test verifies the key optimization: execution artifact parsing is limited
to runs within the returned window, not all discovered runs.

For a dataset with 150 runs where limit=100:
- Default build should parse only execution artifacts for latest 100 run_ids
- Old execution artifacts for runs 101-150 should be skipped
- execution_files_parsed should be << total execution files
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import (
    RunsListPayload,
    build_runs_list,
)


class RunsListWindowOptimizationTests(unittest.TestCase):
    """Tests for execution count derivation optimization based on returned window."""

    def test_execution_files_parsed_only_for_window_runs(self) -> None:
        """Test that execution artifacts are only parsed for runs in the returned window.

        With 150 runs and limit=100, only execution artifacts for the first 100 runs
        should be parsed. Execution artifacts for runs 101-150 should be skipped.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"

            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create 150 runs with timestamps spanning 150 days
            # Runs 0-99: recent (last 100 days)
            # Runs 100-149: old (days 101-150 ago)
            base_time = datetime(2026, 4, 28, tzinfo=UTC)

            for i in range(150):
                run_id = f"run-{i:03d}"
                # Earlier runs have earlier timestamps (sorted descending = newest first)
                days_ago = i
                timestamp = (base_time - timedelta(days=days_ago)).isoformat()

                # Create review artifact
                review_content = {
                    "run_id": run_id,
                    "run_label": f"Run {i}",
                    "timestamp": timestamp,
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"{run_id}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

                # Create execution artifact for EVERY run (50 execution artifacts per run)
                for exec_idx in range(50):
                    exec_content = {
                        "run_id": run_id,
                        "purpose": "next-check-execution",
                        "status": "success",
                        "payload": {"candidateIndex": exec_idx},
                    }
                    exec_path = external_analysis_dir / f"{run_id}-next-check-execution-{exec_idx:03d}.json"
                    exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

                # Create run-scoped diagnostic pack review artifact
                run_pack_dir = diagnostic_packs_dir / run_id
                run_pack_dir.mkdir(parents=True, exist_ok=True)
                review_data = {"run_id": run_id, "entries": []}
                (run_pack_dir / "next_check_usefulness_review.json").write_text(
                    json.dumps(review_data), encoding="utf-8"
                )

            # Build runs list with default limit=100 and timings
            raw_result = build_runs_list(runs_dir, limit=100, _timings=True)
            assert isinstance(raw_result, tuple), "Expected tuple with timings"
            result, timings = raw_result

            # Verify basic counts
            self.assertEqual(result["totalCount"], 150)
            self.assertEqual(result["returnedCount"], 100)
            self.assertTrue(result["hasMore"])

            # Key assertions for the window-driven lookup optimization
            self.assertEqual(timings.get("execution_lookup_strategy"), "window_glob")
            self.assertEqual(timings.get("execution_run_prefixes_queried"), 100)

            # Window-driven: only files for window runs are found
            execution_files_found_total = timings.get("execution_files_found_total", 0)
            self.assertEqual(execution_files_found_total, 5000)  # 100 runs * 50 files

            # No need to consider files outside window
            execution_files_considered = timings.get("execution_files_considered", 0)
            self.assertEqual(execution_files_considered, 5000)  # Should match found

            # We parse all found files (all are window files)
            execution_files_parsed = timings.get("execution_files_parsed", 0)
            self.assertEqual(execution_files_parsed, 5000)

            # No files skipped in window mode
            execution_files_skipped = timings.get("execution_files_skipped_outside_window", 0)
            self.assertEqual(execution_files_skipped, 0)

            # Critical assertion: no global scan of historical files
            # execution_files_found_total should be 5000 (NOT 7500)
            self.assertEqual(execution_files_found_total, 5000)
            # Total historical files would have been 150 * 50 = 7500
            # We only queried files for 100 runs = 5000, so we avoided 2500 file lookups

    def test_include_expensive_affects_batch_eligibility_not_execution_parsing(self) -> None:
        """Test that include_expensive affects batch eligibility, not execution parsing.

        Execution count derivation ALWAYS uses window optimization (parses only window files).
        The include_expensive flag only affects batch eligibility computation.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"

            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create 30 runs with 10 execution artifacts each
            base_time = datetime(2026, 4, 28, tzinfo=UTC)

            for i in range(30):
                run_id = f"run-{i:03d}"
                timestamp = (base_time - timedelta(days=i)).isoformat()

                # Create review artifact
                review_content = {
                    "run_id": run_id,
                    "run_label": f"Run {i}",
                    "timestamp": timestamp,
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"{run_id}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

                # Create execution artifact for EVERY run
                for exec_idx in range(10):
                    exec_content = {
                        "run_id": run_id,
                        "purpose": "next-check-execution",
                        "status": "success",
                        "payload": {"candidateIndex": exec_idx},
                    }
                    exec_path = external_analysis_dir / f"{run_id}-next-check-execution-{exec_idx:03d}.json"
                    exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

                # Create execution batch plan artifact
                batch_plan_content = {
                    "run_id": run_id,
                    "purpose": "next-check-plan",
                    "status": "completed",
                    "payload": {
                        "runs": [],
                    },
                }
                batch_plan_path = external_analysis_dir / f"{run_id}-next-check-plan.json"
                batch_plan_path.write_text(json.dumps(batch_plan_content), encoding="utf-8")

                # Create run-scoped diagnostic pack review artifact
                run_pack_dir = diagnostic_packs_dir / run_id
                run_pack_dir.mkdir(parents=True, exist_ok=True)
                review_data = {"run_id": run_id, "entries": []}
                (run_pack_dir / "next_check_usefulness_review.json").write_text(
                    json.dumps(review_data), encoding="utf-8"
                )

            # Build with include_expensive=True
            raw_result = build_runs_list(runs_dir, limit=10, include_expensive=True, _timings=True)
            assert isinstance(raw_result, tuple), "Expected tuple with timings"
            result, timings = raw_result

            # Verify window-driven lookup strategy
            self.assertEqual(timings.get("execution_lookup_strategy"), "window_glob")
            self.assertEqual(timings.get("execution_run_prefixes_queried"), 10)

            # Window-driven: only files for window runs are found (10 * 10 = 100)
            execution_files_found = timings.get("execution_files_found_total", 0)
            self.assertEqual(execution_files_found, 100)

            # CRITICAL: Execution count derivation ALWAYS uses window optimization
            # regardless of include_expensive. This is the key optimization.
            # With limit=10, we should parse only 100 files for count derivation
            execution_files_parsed = timings.get("execution_files_parsed", 0)
            self.assertEqual(execution_files_parsed, 100)

            # The include_expensive flag affects batch eligibility computation,
            # not execution count derivation. Both cases should parse same amount.

    def test_execution_counts_correct_for_returned_runs(self) -> None:
        """Test that execution counts are correctly derived for runs in the window."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"

            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create 5 runs with known execution counts
            base_time = datetime(2026, 4, 28, tzinfo=UTC)

            run_configs = [
                ("run-000", 3, 2),  # 3 executions, 2 reviewed
                ("run-001", 5, 0),   # 5 executions, 0 reviewed
                ("run-002", 1, 1),   # 1 execution, 1 reviewed
                ("run-003", 0, 0),   # 0 executions
                ("run-004", 4, 4),  # 4 executions, 4 reviewed
            ]

            for i, (run_id, exec_count, reviewed_count) in enumerate(run_configs):
                timestamp = (base_time - timedelta(days=i)).isoformat()

                # Create review artifact
                review_content = {
                    "run_id": run_id,
                    "run_label": f"Run {run_id}",
                    "timestamp": timestamp,
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"{run_id}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

                # Create execution artifacts
                for exec_idx in range(exec_count):
                    exec_content = {
                        "run_id": run_id,
                        "purpose": "next-check-execution",
                        "status": "success",
                        "payload": {"candidateIndex": exec_idx},
                    }
                    # Add usefulness_class for reviewed executions
                    if exec_idx < reviewed_count:
                        exec_content["usefulness_class"] = "useful"
                    exec_path = external_analysis_dir / f"{run_id}-next-check-execution-{exec_idx:03d}.json"
                    exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

                # Create run-scoped diagnostic pack review artifact
                run_pack_dir = diagnostic_packs_dir / run_id
                run_pack_dir.mkdir(parents=True, exist_ok=True)
                review_data = {"run_id": run_id, "entries": []}
                (run_pack_dir / "next_check_usefulness_review.json").write_text(
                    json.dumps(review_data), encoding="utf-8"
                )

            # Build runs list
            result = cast(RunsListPayload, build_runs_list(runs_dir, limit=None))

            # Verify execution counts for each run
            run_counts = {run["runId"]: (run["executionCount"], run["reviewedCount"]) for run in result["runs"]}

            for run_id, expected_exec, expected_reviewed in run_configs:
                actual_exec, actual_reviewed = run_counts[run_id]
                self.assertEqual(
                    actual_exec, expected_exec,
                    f"{run_id}: expected {expected_exec} executions, got {actual_exec}"
                )
                self.assertEqual(
                    actual_reviewed, expected_reviewed,
                    f"{run_id}: expected {expected_reviewed} reviewed, got {actual_reviewed}"
                )

    def test_timings_include_execution_window_metrics(self) -> None:
        """Test that timing metrics include the new execution window optimization fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            diagnostic_packs_dir = runs_health_dir / "diagnostic-packs"

            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)
            diagnostic_packs_dir.mkdir(parents=True)

            # Create a few runs with execution artifacts
            base_time = datetime(2026, 4, 28, tzinfo=UTC)

            for i in range(5):
                run_id = f"run-{i:03d}"
                timestamp = (base_time - timedelta(days=i)).isoformat()

                review_content = {
                    "run_id": run_id,
                    "run_label": f"Run {i}",
                    "timestamp": timestamp,
                    "cluster_count": 2,
                }
                review_path = reviews_dir / f"{run_id}-review.json"
                review_path.write_text(json.dumps(review_content), encoding="utf-8")

                for exec_idx in range(3):
                    exec_content = {
                        "run_id": run_id,
                        "purpose": "next-check-execution",
                        "status": "success",
                        "payload": {"candidateIndex": exec_idx},
                    }
                    exec_path = external_analysis_dir / f"{run_id}-next-check-execution-{exec_idx:03d}.json"
                    exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

                run_pack_dir = diagnostic_packs_dir / run_id
                run_pack_dir.mkdir(parents=True, exist_ok=True)
                review_data = {"run_id": run_id, "entries": []}
                (run_pack_dir / "next_check_usefulness_review.json").write_text(
                    json.dumps(review_data), encoding="utf-8"
                )

            raw_result = build_runs_list(runs_dir, limit=3, _timings=True)
            assert isinstance(raw_result, tuple), "Expected tuple with timings"
            result, timings = raw_result

            # Verify new timing metrics are present
            self.assertIn("execution_lookup_strategy", timings)
            self.assertIn("execution_run_prefixes_queried", timings)
            self.assertIn("execution_files_found_total", timings)
            self.assertIn("execution_files_considered", timings)
            self.assertIn("execution_files_parsed", timings)
            self.assertIn("execution_lookup_ms", timings)

            # Verify values reflect window-driven lookup
            self.assertEqual(timings["execution_lookup_strategy"], "window_glob")
            self.assertEqual(timings["execution_run_prefixes_queried"], 3)  # limit=3
            # Only 3 run prefixes queried, files found = 3 * 3 = 9
            self.assertEqual(timings["execution_files_found_total"], 9)
            # Considered = found (no filtering needed)
            self.assertEqual(timings["execution_files_considered"], 9)
            # All found files are parsed
            self.assertEqual(timings["execution_files_parsed"], 9)
            # No files skipped in window mode
            self.assertEqual(timings["execution_files_skipped_outside_window"], 0)
            self.assertGreaterEqual(timings["execution_lookup_ms"], 0)


if __name__ == "__main__":
    unittest.main()