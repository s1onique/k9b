"""Tests for report_usefulness_learning.py script.

Tests cover:
- Loading summary files from run-scoped directories
- Aggregating statistics across multiple summaries
- Generating deterministic recommendations
- Output formatting (console and JSON)
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.report_usefulness_learning import (
    FamilyStats,
    Recommendation,
    ReportData,
    aggregate_summaries,
    format_report,
    generate_recommendations,
    load_summary_files,
    report_to_dict,
)


class TestLoadSummaryFiles(unittest.TestCase):
    """Tests for loading summary files."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.diagnostic_packs_dir = self.health_dir / "diagnostic-packs"
        self.diagnostic_packs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_summary(self, run_id: str, usefulness_counts: dict[str, int]) -> Path:
        """Create a mock usefulness_summary.json."""
        summary = {
            "schema_version": "usefulness-summary/v1",
            "run_id": run_id,
            "generated_at": "2026-04-15T17:30:00+00:00",
            "statistics": {
                "total_entries": sum(usefulness_counts.values()),
                "successfully_imported": sum(usefulness_counts.values()),
                "errors": 0,
            },
            "usefulness_class_counts": usefulness_counts,
            "command_family_counts": {"kubectl-logs": sum(usefulness_counts.values())},
            "context_aggregates": {
                "by_command_family": {
                    "kubectl-logs": usefulness_counts,
                },
            },
        }
        run_dir = self.diagnostic_packs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "usefulness_summary.json"
        path.write_text(json.dumps(summary), encoding="utf-8")
        return path

    def test_loads_no_summaries_when_none_exist(self) -> None:
        """Test that empty list is returned when no summaries exist."""
        summaries = load_summary_files(self.runs_dir)
        self.assertEqual(summaries, [])

    def test_loads_single_summary(self) -> None:
        """Test that a single summary file is loaded."""
        self._create_summary("test-run-1", {"useful": 3, "noisy": 1})

        summaries = load_summary_files(self.runs_dir)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["run_id"], "test-run-1")

    def test_loads_multiple_summaries(self) -> None:
        """Test that multiple summary files are loaded."""
        self._create_summary("test-run-1", {"useful": 3})
        self._create_summary("test-run-2", {"noisy": 2})
        self._create_summary("test-run-3", {"partial": 1})

        summaries = load_summary_files(self.runs_dir)
        self.assertEqual(len(summaries), 3)
        run_ids = {s["run_id"] for s in summaries}
        self.assertEqual(run_ids, {"test-run-1", "test-run-2", "test-run-3"})

    def test_respects_limit(self) -> None:
        """Test that limit parameter is respected."""
        self._create_summary("test-run-1", {"useful": 1})
        self._create_summary("test-run-2", {"useful": 2})
        self._create_summary("test-run-3", {"useful": 3})

        summaries = load_summary_files(self.runs_dir, limit=2)
        self.assertEqual(len(summaries), 2)

    def test_skips_non_directory_entries(self) -> None:
        """Test that non-directory entries are skipped."""
        # Create a summary in a direct file (not in a directory) - should be ignored
        (self.diagnostic_packs_dir / "not-a-dir-summary.json").write_text(
            json.dumps({"run_id": "ignored"}), encoding="utf-8"
        )

        self._create_summary("test-run-1", {"useful": 1})

        summaries = load_summary_files(self.runs_dir)
        self.assertEqual(len(summaries), 1)

    def test_handles_invalid_json_gracefully(self) -> None:
        """Test that invalid JSON files are skipped."""
        run_dir = self.diagnostic_packs_dir / "invalid-run"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "usefulness_summary.json").write_text("not valid json", encoding="utf-8")

        self._create_summary("test-run-1", {"useful": 1})

        summaries = load_summary_files(self.runs_dir)
        self.assertEqual(len(summaries), 1)


class TestAggregateSummaries(unittest.TestCase):
    """Tests for aggregating summary statistics."""

    def test_aggregates_usefulness_counts(self) -> None:
        """Test that usefulness counts are aggregated correctly."""
        summaries = [
            {
                "run_id": "run-1",
                "statistics": {"total_entries": 10},
                "context_aggregates": {
                    "by_command_family": {
                        "kubectl-logs": {"useful": 3, "noisy": 2},
                        "kubectl-get": {"useful": 1, "partial": 1},
                    },
                },
            },
            {
                "run_id": "run-2",
                "statistics": {"total_entries": 8},
                "context_aggregates": {
                    "by_command_family": {
                        "kubectl-logs": {"useful": 1, "noisy": 1},
                        "kubectl-describe": {"partial": 2, "empty": 1},
                    },
                },
            },
        ]

        report = aggregate_summaries(summaries)

        self.assertEqual(report.summaries_loaded, 2)
        self.assertEqual(report.total_entries, 18)

        # Check kubectl-logs aggregation
        self.assertIn("kubectl-logs", report.families)
        self.assertEqual(report.families["kubectl-logs"].useful_count, 4)
        self.assertEqual(report.families["kubectl-logs"].noisy_count, 3)
        self.assertEqual(report.families["kubectl-logs"].total_count, 7)

    def test_aggregates_workstream_context(self) -> None:
        """Test that workstream context is aggregated."""
        summaries = [
            {
                "run_id": "run-1",
                "statistics": {"total_entries": 10},
                "context_aggregates": {
                    "by_command_family_workstream": {
                        "kubectl-logs:incident": {"useful": 2, "noisy": 1},
                        "kubectl-get:drift": {"useful": 3, "partial": 1},
                    },
                },
            },
        ]

        report = aggregate_summaries(summaries)

        self.assertIn("kubectl-logs", report.families)
        self.assertIn("kubectl-get", report.families)

        # kubectl-logs: incident
        self.assertEqual(report.families["kubectl-logs"].incident_count, 3)
        self.assertEqual(report.families["kubectl-logs"].incident_useful, 2)
        self.assertEqual(report.families["kubectl-logs"].incident_noisy, 1)

        # kubectl-get: drift
        self.assertEqual(report.families["kubectl-get"].drift_count, 4)
        self.assertEqual(report.families["kubectl-get"].drift_useful, 3)

    def test_aggregates_review_stage_context(self) -> None:
        """Test that review stage context is aggregated."""
        summaries = [
            {
                "run_id": "run-1",
                "statistics": {"total_entries": 10},
                "context_aggregates": {
                    "by_command_family_review_stage": {
                        "kubectl-logs:initial_triage": {"noisy": 3},
                        "kubectl-get:parity_validation": {"useful": 2, "partial": 1},
                    },
                },
            },
        ]

        report = aggregate_summaries(summaries)

        # kubectl-logs: initial_triage (noisy)
        self.assertEqual(report.families["kubectl-logs"].initial_triage_count, 3)
        self.assertEqual(report.families["kubectl-logs"].initial_triage_noisy, 3)

        # kubectl-get: parity_validation
        self.assertEqual(report.families["kubectl-get"].parity_validation_count, 3)
        self.assertEqual(report.families["kubectl-get"].parity_validation_useful, 2)

    def test_tracks_runs_per_family(self) -> None:
        """Test that runs are tracked per family."""
        summaries = [
            {
                "run_id": "run-1",
                "statistics": {"total_entries": 5},
                "context_aggregates": {
                    "by_command_family": {"kubectl-logs": {"useful": 2}},
                },
            },
            {
                "run_id": "run-2",
                "statistics": {"total_entries": 5},
                "context_aggregates": {
                    "by_command_family": {"kubectl-logs": {"useful": 1}},
                },
            },
        ]

        report = aggregate_summaries(summaries)

        self.assertIn("run-1", report.families["kubectl-logs"].run_ids)
        self.assertIn("run-2", report.families["kubectl-logs"].run_ids)

    def test_handles_empty_summaries_list(self) -> None:
        """Test that empty summaries list produces empty report."""
        report = aggregate_summaries([])

        self.assertEqual(report.summaries_loaded, 0)
        self.assertEqual(report.total_entries, 0)
        self.assertEqual(len(report.families), 0)


class TestFamilyStats(unittest.TestCase):
    """Tests for FamilyStats calculations."""

    def test_useful_rate_calculation(self) -> None:
        """Test that useful_rate is calculated correctly."""
        stats = FamilyStats(total_count=10, useful_count=3)
        self.assertAlmostEqual(stats.useful_rate, 0.3)

    def test_useful_rate_zero_count(self) -> None:
        """Test that useful_rate is 0 when total_count is 0."""
        stats = FamilyStats()
        self.assertEqual(stats.useful_rate, 0.0)

    def test_noisy_rate_calculation(self) -> None:
        """Test that noisy_rate is calculated correctly."""
        stats = FamilyStats(total_count=10, noisy_count=7)
        self.assertAlmostEqual(stats.noisy_rate, 0.7)

    def test_context_sensitivity_with_single_context(self) -> None:
        """Test sensitivity is 0 with only one context."""
        stats = FamilyStats(context_scores={"cf:kubectl-logs": {"useful": 2}})
        self.assertEqual(stats.context_sensitivity, 0.0)

    def test_context_sensitivity_with_varied_contexts(self) -> None:
        """Test sensitivity is higher with more variation."""
        stats = FamilyStats(
            context_scores={
                "cf:kubectl-logs": {"useful": 10, "noisy": 0},  # 100% useful
                "ws:kubectl-logs:incident": {"useful": 0, "noisy": 10},  # 0% useful
            }
        )
        # Should have non-zero sensitivity due to variation
        self.assertGreater(stats.context_sensitivity, 0.0)


class TestGenerateRecommendations(unittest.TestCase):
    """Tests for recommendation generation."""

    def test_demote_highly_noisy_family(self) -> None:
        """Test that highly noisy families are recommended for demotion."""
        report = ReportData()
        # Create a family with 60% noisy rate and 15% useful rate
        stats = FamilyStats(
            total_count=20,
            useful_count=3,
            noisy_count=12,  # 60% noisy
        )
        report.families["kubectl-get-crd"] = stats

        recommendations = generate_recommendations(report)

        demote_recs = [r for r in recommendations if r.action == "demote"]
        self.assertEqual(len(demote_recs), 1)
        self.assertEqual(demote_recs[0].family, "kubectl-get-crd")

    def test_promote_universally_useful_family(self) -> None:
        """Test that universally useful families are recommended for promotion."""
        report = ReportData()
        stats = FamilyStats(
            total_count=30,
            useful_count=20,  # ~67% useful
            noisy_count=3,  # 10% noisy
            incident_count=15,
            incident_useful=10,  # 67% useful in incident
            drift_count=10,
            drift_useful=7,  # 70% useful in drift
        )
        report.families["kubectl-describe"] = stats

        recommendations = generate_recommendations(report)

        promote_recs = [r for r in recommendations if r.action == "promote"]
        self.assertEqual(len(promote_recs), 1)
        self.assertEqual(promote_recs[0].family, "kubectl-describe")

    def test_keep_context_gated_for_sensitive_family(self) -> None:
        """Test that context-sensitive families are kept gated."""
        report = ReportData()
        stats = FamilyStats(
            total_count=20,
            useful_count=5,
            noisy_count=5,
            incident_count=10,
            incident_useful=7,  # 70% useful in incident
            incident_noisy=1,
            initial_triage_count=10,
            initial_triage_noisy=8,  # 80% noisy in triage
            context_scores={
                "cf:kubectl-get-crd": {"useful": 5, "noisy": 5},
                "ws:kubectl-get-crd:incident": {"useful": 7, "noisy": 1},
                "stage:kubectl-get-crd:initial_triage": {"useful": 1, "noisy": 8},
            },
        )
        report.families["kubectl-get-crd"] = stats

        recommendations = generate_recommendations(report)

        gated_recs = [r for r in recommendations if r.action == "keep_context_gated"]
        self.assertEqual(len(gated_recs), 1)
        self.assertEqual(gated_recs[0].family, "kubectl-get-crd")

    def test_no_recommendations_for_insufficient_data(self) -> None:
        """Test that no recommendations are made for families with < 3 observations."""
        report = ReportData()
        stats = FamilyStats(total_count=2)  # Less than minimum
        report.families["kubectl-logs"] = stats

        recommendations = generate_recommendations(report)

        self.assertEqual(len(recommendations), 0)

    def test_recommendations_sorted_by_priority(self) -> None:
        """Test that recommendations are sorted by action priority."""
        report = ReportData()

        # Demote candidate
        demote_stats = FamilyStats(total_count=20, useful_count=2, noisy_count=12)
        report.families["demote-me"] = demote_stats

        # Promote candidate
        promote_stats = FamilyStats(
            total_count=30,
            useful_count=20,
            noisy_count=3,
            incident_count=15,
            incident_useful=10,
            drift_count=10,
            drift_useful=7,
        )
        report.families["promote-me"] = promote_stats

        recommendations = generate_recommendations(report)

        # Demote should come before promote (action_order: demote=0, promote=1)
        self.assertEqual(recommendations[0].action, "demote")
        self.assertEqual(recommendations[0].family, "demote-me")
        self.assertEqual(recommendations[1].action, "promote")
        self.assertEqual(recommendations[1].family, "promote-me")


class TestFormatReport(unittest.TestCase):
    """Tests for report formatting."""

    def test_output_contains_all_sections(self) -> None:
        """Test that formatted output contains all expected sections."""
        report = ReportData()
        report.summaries_loaded = 3
        report.runs_analyzed = {"run-1", "run-2", "run-3"}
        report.total_entries = 44
        report.families = {
            "kubectl-logs": FamilyStats(total_count=10, useful_count=2, noisy_count=3),
            "kubectl-get-crd": FamilyStats(total_count=20, useful_count=5, noisy_count=15),
        }

        formatted = format_report(report, [])

        self.assertIn("PLANNER IMPROVEMENT REPORT", formatted)
        self.assertIn("Summaries analyzed: 3", formatted)
        self.assertIn("Unique command families: 2", formatted)
        self.assertIn("BEST COMMAND FAMILIES FOR INCIDENT + INITIAL_TRIAGE", formatted)
        self.assertIn("WORST COMMAND FAMILIES FOR INCIDENT + INITIAL_TRIAGE", formatted)
        self.assertIn("BEST COMMAND FAMILIES FOR PARITY_VALIDATION + DRIFT", formatted)
        self.assertIn("FAMILIES WITH LARGEST CONTEXT SENSITIVITY", formatted)
        self.assertIn("FAMILIES WITH HIGHEST NOISY RATE", formatted)
        self.assertIn("FAMILIES WITH HIGHEST USEFUL RATE", formatted)
        self.assertIn("CANDIDATE RECOMMENDATIONS", formatted)
        self.assertIn("END OF REPORT", formatted)

    def test_shows_recommendations_when_present(self) -> None:
        """Test that recommendations are displayed when present."""
        report = ReportData()
        report.summaries_loaded = 1
        report.runs_analyzed = {"run-1"}
        report.total_entries = 10
        report.families = {}

        recommendations = [
            Recommendation(
                family="kubectl-get-crd",
                action="demote",
                reason="Highly noisy",
                evidence={"noisy_rate": 0.75},
            )
        ]

        formatted = format_report(report, recommendations)

        self.assertIn("DEMOTE (reduce priority):", formatted)
        self.assertIn("kubectl-get-crd", formatted)
        self.assertIn("Highly noisy", formatted)

    def test_shows_no_data_message_when_empty(self) -> None:
        """Test that 'No data' message is shown for empty categories."""
        report = ReportData()
        report.summaries_loaded = 1
        report.runs_analyzed = {"run-1"}
        report.total_entries = 0
        report.families = {}

        formatted = format_report(report, [])

        self.assertIn("No data for this category", formatted)


class TestReportToDict(unittest.TestCase):
    """Tests for JSON report generation."""

    def test_produces_valid_json_serializable_dict(self) -> None:
        """Test that report_to_dict produces valid JSON."""
        report = ReportData()
        report.summaries_loaded = 2
        report.runs_analyzed = {"run-1", "run-2"}
        report.total_entries = 30
        stats = FamilyStats(
            total_count=20,
            useful_count=5,
            noisy_count=10,
            incident_count=10,
            incident_useful=3,
        )
        report.families["kubectl-logs"] = stats

        recommendations = [
            Recommendation(
                family="kubectl-logs",
                action="demote",
                reason="Too noisy",
                evidence={"noisy_rate": 0.5},
            )
        ]

        result = report_to_dict(report, recommendations)

        # Verify schema version
        self.assertEqual(result["schema_version"], "planner-improvement-report/v1")

        # Verify summary data
        self.assertEqual(result["summaries_loaded"], 2)
        self.assertEqual(result["total_entries"], 30)

        # Verify family data structure
        self.assertIn("kubectl-logs", result["command_families"])
        family_data = result["command_families"]["kubectl-logs"]
        self.assertEqual(family_data["total_count"], 20)
        self.assertEqual(family_data["useful_count"], 5)
        self.assertEqual(family_data["noisy_rate"], 0.5)

        # Verify recommendation structure
        self.assertEqual(len(result["recommendations"]), 1)
        self.assertEqual(result["recommendations"][0]["family"], "kubectl-logs")
        self.assertEqual(result["recommendations"][0]["action"], "demote")

    def test_json_output_is_valid(self) -> None:
        """Test that the dict can be serialized to JSON."""
        report = ReportData()
        report.summaries_loaded = 1
        report.runs_analyzed = {"run-1"}
        report.total_entries = 5
        report.families = {}

        result = report_to_dict(report, [])

        # Should not raise
        json_str = json.dumps(result, indent=2)
        self.assertIsInstance(json_str, str)
        self.assertIn("planner-improvement-report/v1", json_str)


class TestIntegration(unittest.TestCase):
    """Integration tests for the full workflow."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.diagnostic_packs_dir = self.health_dir / "diagnostic-packs"
        self.diagnostic_packs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_summary(self, run_id: str, context_aggregates: dict[str, Any]) -> None:
        """Create a summary file with given context aggregates."""
        summary = {
            "schema_version": "usefulness-summary/v1",
            "run_id": run_id,
            "generated_at": "2026-04-15T17:30:00+00:00",
            "statistics": {"total_entries": 10},
            "usefulness_class_counts": {"useful": 5, "noisy": 5},
            "command_family_counts": {"kubectl-logs": 10},
            "context_aggregates": context_aggregates,
        }
        run_dir = self.diagnostic_packs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "usefulness_summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def test_full_workflow(self) -> None:
        """Test the complete workflow from loading to output."""
        # Create test summaries
        self._create_summary(
            "run-1",
            {
                "by_command_family": {"kubectl-logs": {"useful": 3, "noisy": 2}},
                "by_command_family_workstream": {
                    "kubectl-logs:incident": {"useful": 2, "noisy": 2},
                    "kubectl-logs:drift": {"useful": 1, "noisy": 0},
                },
                "by_command_family_review_stage": {
                    "kubectl-logs:initial_triage": {"noisy": 2},
                    "kubectl-logs:parity_validation": {"useful": 1},
                },
            },
        )
        self._create_summary(
            "run-2",
            {
                "by_command_family": {"kubectl-logs": {"useful": 2, "noisy": 3}},
                "by_command_family_workstream": {
                    "kubectl-logs:incident": {"useful": 1, "noisy": 3},
                    "kubectl-logs:drift": {"useful": 1, "noisy": 0},
                },
            },
        )

        # Run the workflow
        summaries = load_summary_files(self.runs_dir)
        report = aggregate_summaries(summaries)
        recommendations = generate_recommendations(report)
        formatted = format_report(report, recommendations)
        json_dict = report_to_dict(report, recommendations)

        # Verify results
        self.assertEqual(len(summaries), 2)
        self.assertEqual(report.summaries_loaded, 2)
        self.assertIn("kubectl-logs", report.families)

        # Check aggregated stats
        logs_stats = report.families["kubectl-logs"]
        self.assertEqual(logs_stats.total_count, 10)
        self.assertEqual(logs_stats.useful_count, 5)
        self.assertEqual(logs_stats.noisy_count, 5)
        self.assertEqual(logs_stats.incident_count, 8)
        self.assertEqual(logs_stats.drift_count, 2)

        # Verify output is non-empty
        self.assertGreater(len(formatted), 100)
        self.assertIn("PLANNER IMPROVEMENT REPORT", formatted)
        self.assertIn("kubectl-logs", formatted)

        # Verify JSON output
        self.assertEqual(json_dict["schema_version"], "planner-improvement-report/v1")
        self.assertEqual(json_dict["summaries_loaded"], 2)


if __name__ == "__main__":
    unittest.main()