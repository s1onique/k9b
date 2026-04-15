"""Tests for select_review_candidate_runs.py.

Tests cover:
- Mixed success/failure scoring
- Repeated family across clusters scoring
- Minimum entry count filtering
- Deterministic ranking
- JSON output shape
"""

import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.select_review_candidate_runs import (  # noqa: E402
    RankedRun,
    RunMetrics,
    compute_review_priority_score,
    compute_run_metrics,
    format_json_output,
    format_ranked_table,
    is_generic_digest,
    load_review_exports,
    rank_runs,
)


class TestIsGenericDigest(unittest.TestCase):
    """Tests for generic digest detection."""

    def test_ok_digest_is_generic(self) -> None:
        """Test that 'OK' digests are flagged as generic."""
        self.assertTrue(is_generic_digest("OK"))
        self.assertTrue(is_generic_digest("OK (8194B)"))
        self.assertTrue(is_generic_digest("ok"))
        self.assertTrue(is_generic_digest("ok (123B)"))

    def test_success_is_generic(self) -> None:
        """Test that 'success' is flagged as generic."""
        self.assertTrue(is_generic_digest("SUCCESS"))
        self.assertTrue(is_generic_digest("success"))

    def test_skipped_is_generic(self) -> None:
        """Test that 'skipped' is flagged as generic."""
        self.assertTrue(is_generic_digest("SKIPPED"))
        self.assertTrue(is_generic_digest("skipped"))

    def test_none_is_generic(self) -> None:
        """Test that None is flagged as generic."""
        self.assertTrue(is_generic_digest(None))

    def test_error_digest_not_generic(self) -> None:
        """Test that error digests are NOT generic."""
        self.assertFalse(is_generic_digest("Error from server (NotFound): pod not found"))
        self.assertFalse(is_generic_digest("TIMED_OUT"))
        self.assertFalse(is_generic_digest("FAILED: exit_code=1"))


class TestComputeRunMetrics(unittest.TestCase):
    """Tests for run metrics computation."""

    def test_counts_execution_statuses(self) -> None:
        """Test that execution statuses are counted correctly."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"execution_status": "success", "timed_out": False},
                {"execution_status": "success", "timed_out": False},
                {"execution_status": "failed", "timed_out": False},
                {"execution_status": "timed-out", "timed_out": True},
                {"execution_status": "skipped", "timed_out": False},
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(metrics.entry_count, 5)
        self.assertEqual(metrics.success_count, 2)
        self.assertEqual(metrics.failed_count, 1)
        self.assertEqual(metrics.timed_out_count, 1)
        self.assertEqual(metrics.skipped_count, 1)

    def test_tracks_command_families(self) -> None:
        """Test that command families are tracked."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"command_family": "kubectl-logs", "cluster_label": "cluster-a"},
                {"command_family": "kubectl-logs", "cluster_label": "cluster-a"},
                {"command_family": "kubectl-get", "cluster_label": "cluster-a"},
                {"command_family": "kubectl-describe", "cluster_label": "cluster-b"},
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(metrics.command_family_counts["kubectl-logs"], 2)
        self.assertEqual(metrics.command_family_counts["kubectl-get"], 1)
        self.assertEqual(metrics.command_family_counts["kubectl-describe"], 1)
        self.assertEqual(len(metrics.command_family_counts), 3)

    def test_tracks_cluster_labels(self) -> None:
        """Test that cluster labels are tracked."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"cluster_label": "cluster-a"},
                {"cluster_label": "cluster-b"},
                {"cluster_label": "cluster-a"},
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(len(metrics.cluster_labels), 2)
        self.assertIn("cluster-a", metrics.cluster_labels)
        self.assertIn("cluster-b", metrics.cluster_labels)

    def test_tracks_cross_cluster_families(self) -> None:
        """Test that family-to-cluster mapping is tracked."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"command_family": "kubectl-logs", "cluster_label": "cluster-a"},
                {"command_family": "kubectl-logs", "cluster_label": "cluster-b"},
                {"command_family": "kubectl-logs", "cluster_label": "cluster-c"},
                {"command_family": "kubectl-get", "cluster_label": "cluster-a"},
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(len(metrics.family_to_clusters["kubectl-logs"]), 3)
        self.assertEqual(len(metrics.family_to_clusters["kubectl-get"]), 1)

    def test_tracks_signal_markers(self) -> None:
        """Test that signal markers are counted."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"signal_markers": ["OOMKilled", "CrashLoopBackOff"]},
                {"signal_markers": ["OOMKilled"]},
                {"signal_markers": []},
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(metrics.signal_marker_counts["OOMKilled"], 2)
        self.assertEqual(metrics.signal_marker_counts["CrashLoopBackOff"], 1)

    def test_computes_digest_richness(self) -> None:
        """Test that digest richness is computed."""
        run_data = {
            "run_id": "test-run",
            "entries": [
                {"result_digest": "OK (100B)"},  # generic
                {"result_digest": "Error: pod not found"},  # non-generic
                {"result_digest": "OK (200B)"},  # generic
                {"result_digest": "Error: connection refused"},  # non-generic
            ],
        }
        metrics = compute_run_metrics(run_data)

        self.assertEqual(metrics.generic_digest_count, 2)
        self.assertEqual(metrics.non_generic_digest_count, 2)


class TestComputeReviewPriorityScore(unittest.TestCase):
    """Tests for review priority score computation."""

    def test_low_entry_count_zero_score(self) -> None:
        """Test that runs with < 5 entries get 0 entry score."""
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 3
        score, reasons = compute_review_priority_score(metrics)
        self.assertEqual(score, 0.0)
        self.assertNotIn("entry_count", reasons[0] if reasons else "")

    def test_high_entry_count_scores(self) -> None:
        """Test that runs with >= 5 entries get positive score."""
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 10
        score, reasons = compute_review_priority_score(metrics)
        self.assertGreater(score, 0)
        self.assertTrue(any("entry_count=10" in r for r in reasons))

    def test_mixed_outcomes_scores_high(self) -> None:
        """Test that mixed success/failure runs score higher."""
        # 50% failure rate is in the ideal range
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 10
        metrics.success_count = 5
        metrics.failed_count = 5
        score, reasons = compute_review_priority_score(metrics)

        self.assertTrue(any("mixed_outcomes" in r for r in reasons))

    def test_all_success_low_score(self) -> None:
        """Test that all-success runs score lower."""
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 10
        metrics.success_count = 10
        score_all, _ = compute_review_priority_score(metrics)

        metrics.failed_count = 2
        score_mixed, _ = compute_review_priority_score(metrics)

        self.assertGreater(score_mixed, score_all)

    def test_cross_cluster_families_score(self) -> None:
        """Test that cross-cluster families contribute to score."""
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 10
        metrics.family_to_clusters = {
            "kubectl-logs": {"cluster-a", "cluster-b"},
            "kubectl-get": {"cluster-a", "cluster-b"},
        }
        score, reasons = compute_review_priority_score(metrics)

        self.assertTrue(any("cross_cluster_families" in r for r in reasons))

    def test_signal_markers_score(self) -> None:
        """Test that signal markers contribute to score."""
        metrics = RunMetrics(run_id="test")
        metrics.entry_count = 10
        metrics.signal_marker_counts = Counter({"OOMKilled": 3, "CrashLoopBackOff": 2})
        score, reasons = compute_review_priority_score(metrics)

        self.assertTrue(any("signal_markers=5" in r for r in reasons))


class TestRankRuns(unittest.TestCase):
    """Tests for run ranking."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_filters_by_min_entry_count(self) -> None:
        """Test that runs below min_entry_count are filtered."""
        runs_data = [
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "run-1", "entries": [{"a": 1}]},
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "run-2", "entries": [{"a": 1}, {"b": 2}]},
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "run-3", "entries": [{"a": 1}, {"b": 2}, {"c": 3}]},
        ]

        ranked = rank_runs(runs_data, min_entry_count=3)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].run_id, "run-3")

    def test_filters_by_mixed_outcomes(self) -> None:
        """Test that runs without mixed outcomes are filtered."""
        runs_data = [
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "all-success", "entries": [
                {"execution_status": "success"},
                {"execution_status": "success"},
            ]},
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "mixed", "entries": [
                {"execution_status": "success"},
                {"execution_status": "failed"},
            ]},
        ]

        ranked = rank_runs(runs_data, require_mixed_outcomes=True)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].run_id, "mixed")

    def test_ranks_by_score_descending(self) -> None:
        """Test that runs are ranked by score descending."""
        runs_data: list[dict[str, Any]] = [
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "low", "entries": [
                {"execution_status": "success"},
            ]},
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "high", "entries": [
                {"execution_status": "success"},
                {"execution_status": "failed"},
                {"command_family": "kubectl-logs", "cluster_label": "a"},
                {"command_family": "kubectl-logs", "cluster_label": "b"},
                {"command_family": "kubectl-get", "cluster_label": "a"},
                {"result_digest": "Error: not found"},
                {"result_digest": "Error: timeout"},
                {"signal_markers": ["OOMKilled"]},
            ]},
        ]

        ranked = rank_runs(runs_data)
        self.assertEqual(len(ranked), 2)
        # High should come first due to more scoring factors
        self.assertEqual(ranked[0].run_id, "high")

    def test_skips_wrong_schema_version(self) -> None:
        """Test that runs with wrong schema version are skipped."""
        runs_data = [
            {"schema_version": "wrong-schema/v1", "run_id": "wrong", "entries": [{"a": 1}] * 10},
        ]

        ranked = rank_runs(runs_data)
        self.assertEqual(len(ranked), 0)

    def test_deterministic_ranking(self) -> None:
        """Test that ranking is deterministic (same input = same output)."""
        runs_data = [
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "run-a", "entries": [
                {"execution_status": "success"},
                {"execution_status": "failed"},
            ]},
            {"schema_version": "next-check-usefulness-review/v1", "run_id": "run-b", "entries": [
                {"execution_status": "success"},
                {"execution_status": "failed"},
            ]},
        ]

        ranked1 = rank_runs(runs_data)
        ranked2 = rank_runs(runs_data)

        self.assertEqual(
            [r.run_id for r in ranked1],
            [r.run_id for r in ranked2],
        )
        self.assertEqual(
            [r.overall_review_priority_score for r in ranked1],
            [r.overall_review_priority_score for r in ranked2],
        )


class TestLoadReviewExports(unittest.TestCase):
    """Tests for loading review exports."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_loads_from_review_exports_dir(self) -> None:
        """Test loading from review-exports directory."""
        review_exports = self.health_dir / "review-exports"
        review_exports.mkdir()
        (review_exports / "test-run-next_check_usefulness_review.json").write_text(
            json.dumps({"schema_version": "next-check-usefulness-review/v1", "run_id": "test-run", "entries": []}),
            encoding="utf-8",
        )

        data = load_review_exports(self.runs_dir)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["run_id"], "test-run")

    def test_deduplicates_by_run_id(self) -> None:
        """Test that duplicate run_ids are deduplicated."""
        review_exports = self.health_dir / "review-exports"
        review_exports.mkdir()
        (review_exports / "test-run-next_check_usefulness_review.json").write_text(
            json.dumps({"schema_version": "next-check-usefulness-review/v1", "run_id": "test-run", "entries": []}),
            encoding="utf-8",
        )

        # Create canonical path with same run_id
        diagnostic_packs = self.health_dir / "diagnostic-packs" / "test-run"
        diagnostic_packs.mkdir(parents=True)
        (diagnostic_packs / "next_check_usefulness_review.json").write_text(
            json.dumps({"schema_version": "next-check-usefulness-review/v1", "run_id": "test-run", "entries": []}),
            encoding="utf-8",
        )

        data = load_review_exports(self.runs_dir)
        self.assertEqual(len(data), 1)

    def test_handles_invalid_json(self) -> None:
        """Test that invalid JSON files are skipped."""
        review_exports = self.health_dir / "review-exports"
        review_exports.mkdir()
        (review_exports / "invalid-next_check_usefulness_review.json").write_text(
            "not valid json {",
            encoding="utf-8",
        )

        data = load_review_exports(self.runs_dir)
        self.assertEqual(len(data), 0)


class TestFormatJsonOutput(unittest.TestCase):
    """Tests for JSON output formatting."""

    def test_json_output_shape(self) -> None:
        """Test that JSON output has expected structure."""
        ranked_runs = [
            RankedRun(
                run_id="test-run",
                entry_count=10,
                success_count=7,
                failed_count=3,
                timed_out_count=0,
                command_family_counts={"kubectl-logs": 5, "kubectl-get": 5},
                cluster_count=3,
                repeated_family_cross_cluster_count=2,
                digest_richness_score=0.5,
                overall_review_priority_score=75.0,
                why_selected=["entry_count=10", "mixed_outcomes"],
            )
        ]

        output = format_json_output(ranked_runs)
        data = json.loads(output)

        self.assertEqual(data["schema_version"], "review-candidate-selection/v1")
        self.assertEqual(data["total_runs_scanned"], 1)
        self.assertEqual(len(data["runs"]), 1)
        run = data["runs"][0]
        self.assertEqual(run["run_id"], "test-run")
        self.assertEqual(run["entry_count"], 10)
        self.assertEqual(run["overall_review_priority_score"], 75.0)

    def test_json_respects_top_n(self) -> None:
        """Test that JSON output respects top_n parameter."""
        ranked_runs = [
            RankedRun("run-1", 10, 7, 3, 0, {}, 3, 2, 0.5, 75.0, []),
            RankedRun("run-2", 10, 7, 3, 0, {}, 3, 2, 0.5, 70.0, []),
            RankedRun("run-3", 10, 7, 3, 0, {}, 3, 2, 0.5, 65.0, []),
        ]

        output = format_json_output(ranked_runs, top_n=2)
        data = json.loads(output)

        self.assertEqual(data["total_runs_scanned"], 3)
        self.assertEqual(len(data["runs"]), 2)


class TestFormatRankedTable(unittest.TestCase):
    """Tests for human-readable table formatting."""

    def test_table_header(self) -> None:
        """Test that table has correct header."""
        ranked_runs = [
            RankedRun("run-1", 10, 7, 3, 0, {}, 3, 2, 0.5, 75.0, ["entry_count=10"]),
        ]

        output = format_ranked_table(ranked_runs)
        lines = output.split("\n")

        self.assertIn("run_id", lines[0])
        self.assertIn("score", lines[0])
        self.assertIn("entries", lines[0])
        self.assertIn("clusters", lines[0])

    def test_table_shows_runs(self) -> None:
        """Test that table shows ranked runs."""
        ranked_runs = [
            RankedRun("run-1", 10, 7, 3, 0, {}, 3, 2, 0.5, 75.0, ["entry_count=10"]),
            RankedRun("run-2", 8, 5, 3, 0, {}, 2, 1, 0.3, 60.0, ["entry_count=8"]),
        ]

        output = format_ranked_table(ranked_runs)

        self.assertIn("run-1", output)
        self.assertIn("run-2", output)

    def test_table_respects_top_n(self) -> None:
        """Test that table respects top_n parameter."""
        ranked_runs = [
            RankedRun("run-1", 10, 7, 3, 0, {}, 3, 2, 0.5, 75.0, []),
            RankedRun("run-2", 10, 7, 3, 0, {}, 3, 2, 0.5, 70.0, []),
        ]

        output = format_ranked_table(ranked_runs, top_n=1)

        self.assertIn("run-1", output)
        self.assertNotIn("run-2", output)
        self.assertIn("Showing top 1 of 2 runs", output)


if __name__ == "__main__":
    unittest.main()
