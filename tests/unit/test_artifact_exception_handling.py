"""Tests for artifact exception handling in read-model paths.

These tests verify that malformed/unreadable artifacts are skipped
with appropriate logging, rather than causing failures or silent drops.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest import TestCase

from k8s_diag_agent.health.summary import (
    _collect_comparison_summaries,
    _load_json,
)
from k8s_diag_agent.health.ui import (
    _build_promotions_index,
    _build_recent_runs_summary,
    _collect_review_timestamps,
    _write_proposal_status_summary_to_review,
)
from k8s_diag_agent.ui.server_read_support import (
    _build_execution_history,
    _build_llm_stats_for_run,
    _build_run_artifact_index,
    _find_next_check_plan,
    _find_review_enrichment,
    _load_notifications_for_run,
    _load_proposals_for_run,
    _scan_external_analysis,
)


class TestArtifactExceptionHandling(TestCase):
    """Test that artifact scan loops handle malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_proposal_is_skipped_with_warning(self) -> None:
        """Malformed JSON proposal artifact is skipped, valid ones still load."""
        proposals_dir = self.tmpdir / "proposals"
        proposals_dir.mkdir()

        # Write valid proposal
        valid_proposal = proposals_dir / f"{self.run_id}-proposal-1.json"
        valid_proposal.write_text(json.dumps({"proposal_id": "p1", "target": "test"}), encoding="utf-8")

        # Write malformed JSON
        malformed_proposal = proposals_dir / f"{self.run_id}-proposal-2.json"
        malformed_proposal.write_text("{ invalid json", encoding="utf-8")

        # Write another valid proposal
        valid_proposal2 = proposals_dir / f"{self.run_id}-proposal-3.json"
        valid_proposal2.write_text(json.dumps({"proposal_id": "p3", "target": "test2"}), encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            proposals, count = _load_proposals_for_run(proposals_dir, self.run_id)

        # Should have loaded 2 valid proposals
        self.assertEqual(count, 2)
        self.assertEqual(len(proposals), 2)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed proposal artifact" in msg for msg in cm.output))
        self.assertTrue(any("proposal-2.json" in msg for msg in cm.output))

    def test_malformed_json_notification_is_skipped_with_warning(self) -> None:
        """Malformed JSON notification artifact is skipped, valid ones still load."""
        notifications_dir = self.tmpdir / "notifications"
        notifications_dir.mkdir()

        # Write valid notification
        valid_notif = notifications_dir / "notif-1.json"
        valid_notif.write_text(json.dumps({"kind": "info", "summary": "test"}), encoding="utf-8")

        # Write malformed JSON
        malformed_notif = notifications_dir / "notif-2.json"
        malformed_notif.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            notifications, count = _load_notifications_for_run(notifications_dir, self.run_id)

        # Should have loaded 1 valid notification
        self.assertEqual(count, 1)
        self.assertEqual(len(notifications), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed notification artifact" in msg for msg in cm.output))
        self.assertTrue(any("notif-2.json" in msg for msg in cm.output))

    def test_malformed_json_external_analysis_is_skipped_with_warning(self) -> None:
        """Malformed JSON external-analysis artifact is skipped, valid ones still load."""
        external_analysis_dir = self.tmpdir / "external-analysis"
        external_analysis_dir.mkdir()

        # Write valid artifact
        valid_artifact = external_analysis_dir / f"{self.run_id}-drilldown-1.json"
        valid_artifact.write_text(json.dumps({"status": "success", "run_id": self.run_id}), encoding="utf-8")

        # Write malformed JSON
        malformed_artifact = external_analysis_dir / f"{self.run_id}-drilldown-2.json"
        malformed_artifact.write_text("not json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            result = _scan_external_analysis(external_analysis_dir, self.run_id)

        # Should have scanned 1 valid artifact
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["artifacts"]), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed external-analysis artifact" in msg for msg in cm.output))
        self.assertTrue(any("drilldown-2.json" in msg for msg in cm.output))

    def test_unreadable_artifact_is_skipped_with_warning(self) -> None:
        """Unreadable artifact (permission denied) is skipped with warning."""
        proposals_dir = self.tmpdir / "proposals"
        proposals_dir.mkdir()

        # Write valid proposal
        valid_proposal = proposals_dir / f"{self.run_id}-proposal-1.json"
        valid_proposal.write_text(json.dumps({"proposal_id": "p1", "target": "test"}), encoding="utf-8")

        # Create unreadable file (simulates OSError from disk I/O errors)
        unreadable_proposal = proposals_dir / f"{self.run_id}-proposal-2.json"
        unreadable_proposal.write_text(json.dumps({"proposal_id": "p2"}), encoding="utf-8")
        unreadable_proposal.chmod(0o000)

        try:
            with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
                proposals, count = _load_proposals_for_run(proposals_dir, self.run_id)

            # Should have loaded 1 valid proposal
            self.assertEqual(count, 1)

            # Should have logged a warning for the unreadable artifact
            self.assertTrue(any("Skipped malformed proposal artifact" in msg for msg in cm.output))
            self.assertTrue(any("proposal-2.json" in msg for msg in cm.output))
        finally:
            # Restore permissions for cleanup
            unreadable_proposal.chmod(0o644)

    def test_valid_artifacts_still_load_correctly(self) -> None:
        """Valid artifacts load without warnings or errors."""
        proposals_dir = self.tmpdir / "proposals"
        proposals_dir.mkdir()

        # Write multiple valid proposals
        for i in range(3):
            proposal = proposals_dir / f"{self.run_id}-proposal-{i}.json"
            proposal.write_text(json.dumps({"proposal_id": f"p{i}", "target": f"test{i}"}), encoding="utf-8")

        # Should not produce any warning logs
        with self.assertNoLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING):
            proposals, count = _load_proposals_for_run(proposals_dir, self.run_id)

        self.assertEqual(count, 3)
        self.assertEqual(len(proposals), 3)


class TestBuildRunArtifactIndexExceptionHandling(TestCase):
    """Test _build_run_artifact_index handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.external_analysis_dir = self.tmpdir / "external-analysis"
        self.external_analysis_dir.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_in_index_scan_is_skipped_with_warning(self) -> None:
        """Malformed JSON in _build_run_artifact_index is skipped with warning."""
        # Write valid artifact
        valid_artifact = self.external_analysis_dir / f"{self.run_id}-review-enrichment-1.json"
        valid_artifact.write_text(
            json.dumps({"purpose": "review-enrichment", "status": "success"}),
            encoding="utf-8",
        )

        # Write malformed JSON
        malformed_artifact = self.external_analysis_dir / f"{self.run_id}-review-enrichment-2.json"
        malformed_artifact.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Should have indexed 1 valid artifact
        self.assertEqual(len(index.review_enrichment), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed artifact in index scan" in msg for msg in cm.output))
        self.assertTrue(any("review-enrichment-2.json" in msg for msg in cm.output))

    def test_valid_artifacts_in_index_load_correctly(self) -> None:
        """Valid artifacts in _build_run_artifact_index load correctly."""
        # Write valid artifacts
        for i in range(2):
            artifact = self.external_analysis_dir / f"{self.run_id}-review-enrichment-{i}.json"
            artifact.write_text(
                json.dumps({"purpose": "review-enrichment", "status": "success"}),
                encoding="utf-8",
            )

        with self.assertNoLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING):
            index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        self.assertEqual(len(index.review_enrichment), 2)


class TestFindReviewEnrichmentExceptionHandling(TestCase):
    """Test _find_review_enrichment handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.external_analysis_dir = self.tmpdir / "external-analysis"
        self.external_analysis_dir.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_in_review_enrichment_scan_is_skipped(self) -> None:
        """Malformed JSON in _find_review_enrichment fallback scan is skipped with warning."""
        # Write valid artifact
        valid_artifact = self.external_analysis_dir / f"{self.run_id}-review-enrichment-1.json"
        valid_artifact.write_text(
            json.dumps({"purpose": "review-enrichment", "status": "success"}),
            encoding="utf-8",
        )

        # Write malformed JSON
        malformed_artifact = self.external_analysis_dir / f"{self.run_id}-review-enrichment-2.json"
        malformed_artifact.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            result = _find_review_enrichment(self.external_analysis_dir, self.run_id)

        # Should have found the valid artifact
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "success")

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed review-enrichment artifact" in msg for msg in cm.output))
        self.assertTrue(any("review-enrichment-2.json" in msg for msg in cm.output))


class TestFindNextCheckPlanExceptionHandling(TestCase):
    """Test _find_next_check_plan handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.external_analysis_dir = self.tmpdir / "external-analysis"
        self.external_analysis_dir.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_in_next_check_plan_scan_is_skipped(self) -> None:
        """Malformed JSON in _find_next_check_plan fallback scan is skipped with warning."""
        # Write valid artifact
        valid_artifact = self.external_analysis_dir / f"{self.run_id}-next-check-plan-1.json"
        valid_artifact.write_text(
            json.dumps({"purpose": "next-check-planning", "status": "success"}),
            encoding="utf-8",
        )

        # Write malformed JSON
        malformed_artifact = self.external_analysis_dir / f"{self.run_id}-next-check-plan-2.json"
        malformed_artifact.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            result = _find_next_check_plan(self.external_analysis_dir, self.run_id)

        # Should have found the valid artifact
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "success")

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed next-check-plan artifact" in msg for msg in cm.output))
        self.assertTrue(any("next-check-plan-2.json" in msg for msg in cm.output))


class TestBuildExecutionHistoryExceptionHandling(TestCase):
    """Test _build_execution_history handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.external_analysis_dir = self.tmpdir / "external-analysis"
        self.external_analysis_dir.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_in_execution_history_scan_is_skipped(self) -> None:
        """Malformed JSON in _build_execution_history fallback scan is skipped with warning."""
        # Write valid artifact
        valid_artifact = self.external_analysis_dir / f"{self.run_id}-next-check-execution-1.json"
        valid_artifact.write_text(
            json.dumps({"purpose": "next-check-execution", "status": "success"}),
            encoding="utf-8",
        )

        # Write malformed JSON
        malformed_artifact = self.external_analysis_dir / f"{self.run_id}-next-check-execution-2.json"
        malformed_artifact.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id)

        # Should have found 1 valid execution entry
        self.assertEqual(len(history), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed next-check-execution artifact" in msg for msg in cm.output))
        self.assertTrue(any("next-check-execution-2.json" in msg for msg in cm.output))


class TestBuildLlmStatsExceptionHandling(TestCase):
    """Test _build_llm_stats_for_run handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "health-run-20260501T063733Z"
        self.external_analysis_dir = self.tmpdir / "external-analysis"
        self.external_analysis_dir.mkdir()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_in_llm_stats_scan_is_skipped(self) -> None:
        """Malformed JSON in _build_llm_stats_for_run fallback scan is skipped with warning."""
        # Write valid artifact
        valid_artifact = self.external_analysis_dir / f"{self.run_id}-drilldown-1.json"
        valid_artifact.write_text(
            json.dumps({"status": "success", "run_id": self.run_id}),
            encoding="utf-8",
        )

        # Write malformed JSON
        malformed_artifact = self.external_analysis_dir / f"{self.run_id}-drilldown-2.json"
        malformed_artifact.write_text("{ malformed", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING) as cm:
            stats = _build_llm_stats_for_run(self.external_analysis_dir, self.run_id)

        # Should have counted 1 valid artifact
        self.assertEqual(stats["totalCalls"], 1)
        self.assertEqual(stats["successfulCalls"], 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed artifact in llm_stats scan" in msg for msg in cm.output))
        self.assertTrue(any("drilldown-2.json" in msg for msg in cm.output))

    def test_valid_artifacts_in_llm_stats_load_correctly(self) -> None:
        """Valid artifacts in _build_llm_stats_for_run load correctly."""
        # Write valid artifacts
        for i in range(2):
            artifact = self.external_analysis_dir / f"{self.run_id}-drilldown-{i}.json"
            artifact.write_text(
                json.dumps({"status": "success", "run_id": self.run_id}),
                encoding="utf-8",
            )

        with self.assertNoLogs("k8s_diag_agent.ui.server_read_support", level=logging.WARNING):
            stats = _build_llm_stats_for_run(self.external_analysis_dir, self.run_id)

        self.assertEqual(stats["totalCalls"], 2)
        self.assertEqual(stats["successfulCalls"], 2)

# =============================================================================
# Tests for health/summary.py exception handlers
# =============================================================================


class TestLoadJsonExceptionHandling(TestCase):
    """Test _load_json handles malformed/unreadable artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_json_returns_empty_dict_with_warning(self) -> None:
        """Malformed JSON returns empty dict and logs warning."""
        malformed_file = self.tmpdir / "malformed-assessment.json"
        malformed_file.write_text("{ invalid json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.health.summary", level=logging.WARNING) as cm:
            result = _load_json(malformed_file)

        self.assertEqual(result, {})
        self.assertTrue(any("Skipped malformed assessment artifact" in msg for msg in cm.output))
        self.assertTrue(any("malformed-assessment.json" in msg for msg in cm.output))

    def test_unreadable_file_returns_empty_dict_with_warning(self) -> None:
        """Unreadable file (permission denied) returns empty dict and logs warning."""
        unreadable_file = self.tmpdir / "unreadable-assessment.json"
        unreadable_file.write_text('{"valid": "json"}', encoding="utf-8")
        unreadable_file.chmod(0o000)

        try:
            with self.assertLogs("k8s_diag_agent.health.summary", level=logging.WARNING) as cm:
                result = _load_json(unreadable_file)

            self.assertEqual(result, {})
            self.assertTrue(any("Skipped malformed assessment artifact" in msg for msg in cm.output))
            self.assertTrue(any("unreadable-assessment.json" in msg for msg in cm.output))
        finally:
            unreadable_file.chmod(0o644)

    def test_valid_json_loads_correctly(self) -> None:
        """Valid JSON loads without warnings."""
        valid_file = self.tmpdir / "valid-assessment.json"
        valid_file.write_text(json.dumps({"findings": ["test"]}), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.summary", level=logging.WARNING):
            result = _load_json(valid_file)

        self.assertEqual(result, {"findings": ["test"]})

    def test_non_mapping_json_returns_empty_dict(self) -> None:
        """JSON that is not a mapping returns empty dict without warning."""
        array_file = self.tmpdir / "array-assessment.json"
        array_file.write_text(json.dumps(["not", "a", "mapping"]), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.summary", level=logging.WARNING):
            result = _load_json(array_file)

        self.assertEqual(result, {})


class TestCollectComparisonSummariesExceptionHandling(TestCase):
    """Test _collect_comparison_summaries handles malformed comparison-decisions artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "comparison-test-20260501T063733Z"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_comparison_decisions_returns_empty_list_with_warning(self) -> None:
        """Malformed comparison-decisions artifact returns empty list and logs warning."""
        comparison_file = self.tmpdir / f"{self.run_id}-comparison-decisions.json"
        comparison_file.write_text("{ invalid json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.health.summary", level=logging.WARNING) as cm:
            result = _collect_comparison_summaries(self.tmpdir, self.run_id)

        self.assertEqual(result, [])
        self.assertTrue(
            any("Skipped malformed comparison-decisions artifact" in msg for msg in cm.output)
        )
        self.assertTrue(any(f"{self.run_id}-comparison-decisions.json" in msg for msg in cm.output))

    def test_unreadable_comparison_decisions_returns_empty_list_with_warning(self) -> None:
        """Unreadable comparison-decisions file returns empty list and logs warning."""
        comparison_file = self.tmpdir / f"{self.run_id}-comparison-decisions.json"
        comparison_file.write_text(json.dumps([]), encoding="utf-8")
        comparison_file.chmod(0o000)

        try:
            with self.assertLogs("k8s_diag_agent.health.summary", level=logging.WARNING) as cm:
                result = _collect_comparison_summaries(self.tmpdir, self.run_id)

            self.assertEqual(result, [])
            self.assertTrue(
                any("Skipped malformed comparison-decisions artifact" in msg for msg in cm.output)
            )
        finally:
            comparison_file.chmod(0o644)

    def test_valid_comparison_decisions_loads_correctly(self) -> None:
        """Valid comparison-decisions artifact loads without warnings."""
        comparison_file = self.tmpdir / f"{self.run_id}-comparison-decisions.json"
        comparison_file.write_text(
            json.dumps([
                {
                    "primary_label": "cluster-alpha",
                    "secondary_label": "cluster-beta",
                    "policy_eligible": True,
                    "triggered": True,
                    "comparison_intent": "test",
                    "reason": "test comparison",
                }
            ]),
            encoding="utf-8",
        )

        with self.assertNoLogs("k8s_diag_agent.health.summary", level=logging.WARNING):
            result = _collect_comparison_summaries(self.tmpdir, self.run_id)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].primary_label, "cluster-alpha")
        self.assertEqual(result[0].secondary_label, "cluster-beta")

    def test_nonexistent_comparison_decisions_returns_empty_list(self) -> None:
        """Nonexistent comparison-decisions file returns empty list without warning."""
        with self.assertNoLogs("k8s_diag_agent.health.summary", level=logging.WARNING):
            result = _collect_comparison_summaries(self.tmpdir, "nonexistent-20260501T063733Z")

        self.assertEqual(result, [])

    def test_non_sequence_comparison_decisions_returns_empty_list(self) -> None:
        """Non-sequence comparison-decisions returns empty list without warning."""
        comparison_file = self.tmpdir / f"{self.run_id}-comparison-decisions.json"
        comparison_file.write_text(json.dumps({"not": "a sequence"}), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.summary", level=logging.WARNING):
            result = _collect_comparison_summaries(self.tmpdir, self.run_id)

        self.assertEqual(result, [])


# =============================================================================
# Tests for health/ui.py exception handlers
# =============================================================================


class TestCollectReviewTimestampsExceptionHandling(TestCase):
    """Test _collect_review_timestamps handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_review_timestamp_artifact_is_skipped_with_warning(self) -> None:
        """Malformed JSON in review timestamp artifact is skipped with warning."""
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir()

        # Write valid review
        valid_review = reviews_dir / "run-1-20260101T000000Z-review.json"
        valid_review.write_text(json.dumps({
            "run_id": "run-1",
            "timestamp": "2026-01-01T00:00:00Z",
        }), encoding="utf-8")

        # Write malformed JSON
        malformed_review = reviews_dir / "run-2-20260102T000000Z-review.json"
        malformed_review.write_text("{ malformed json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.health.ui", level=logging.WARNING) as cm:
            timestamps = _collect_review_timestamps(reviews_dir)

        # Should have collected 1 valid timestamp
        self.assertEqual(len(timestamps), 1)
        self.assertIn("run-1", timestamps)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed review timestamp artifact" in msg for msg in cm.output))
        self.assertTrue(any("run-2" in msg or "review.json" in msg for msg in cm.output))

    def test_valid_review_timestamps_load_correctly(self) -> None:
        """Valid review timestamps load without warnings."""
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir()

        # Write valid reviews
        for i in range(3):
            review = reviews_dir / f"run-{i}-2026010{i+1}T000000Z-review.json"
            review.write_text(json.dumps({
                "run_id": f"run-{i}",
                "timestamp": f"2026-01-0{i+1}T00:00:00Z",
            }), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.ui", level=logging.WARNING):
            timestamps = _collect_review_timestamps(reviews_dir)

        self.assertEqual(len(timestamps), 3)


class TestBuildRecentRunsSummaryExceptionHandling(TestCase):
    """Test _build_recent_runs_summary handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_recent_run_artifact_is_skipped_with_warning(self) -> None:
        """Malformed JSON in recent runs summary is skipped with warning."""
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir()

        # Write valid review
        valid_review = reviews_dir / "run-1-20260101T000000Z-review.json"
        valid_review.write_text(json.dumps({
            "run_id": "run-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "run_label": "Test Run 1",
            "cluster_count": 2,
        }), encoding="utf-8")

        # Write malformed JSON
        malformed_review = reviews_dir / "run-2-20260102T000000Z-review.json"
        malformed_review.write_text("{ malformed json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.health.ui", level=logging.WARNING) as cm:
            result = _build_recent_runs_summary(reviews_dir)

        # Should have processed 1 valid run
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["runs"]), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed recent-run artifact" in msg for msg in cm.output))
        self.assertTrue(any("run-2" in msg or "review.json" in msg for msg in cm.output))

    def test_valid_recent_runs_load_correctly(self) -> None:
        """Valid recent runs load without warnings."""
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir()

        # Write valid reviews
        for i in range(3):
            review = reviews_dir / f"run-{i}-2026010{i+1}T000000Z-review.json"
            review.write_text(json.dumps({
                "run_id": f"run-{i}",
                "timestamp": f"2026-01-0{i+1}T00:00:00Z",
                "run_label": f"Test Run {i}",
                "cluster_count": i + 1,
            }), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.ui", level=logging.WARNING):
            result = _build_recent_runs_summary(reviews_dir)

        self.assertEqual(result["total_count"], 3)
        self.assertEqual(len(result["runs"]), 3)


class TestBuildPromotionsIndexExceptionHandling(TestCase):
    """Test _build_promotions_index handles malformed artifacts gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.run_id = "promo-run-20260101T000000Z"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_malformed_promotion_artifact_is_skipped_with_warning(self) -> None:
        """Malformed JSON in promotion artifact is skipped with warning."""
        external_analysis_dir = self.tmpdir / "external-analysis"
        external_analysis_dir.mkdir()

        # Write valid promotion artifact
        valid_promo = external_analysis_dir / f"{self.run_id}-next-check-promotion-1.json"
        valid_promo.write_text(json.dumps({
            "status": "success",
            "run_id": self.run_id,
            "payload": {
                "candidateId": "candidate-1",
                "promotionIndex": 0,
                "description": "Test promotion",
                "clusterLabel": "cluster-a",
            },
        }), encoding="utf-8")

        # Write malformed JSON
        malformed_promo = external_analysis_dir / f"{self.run_id}-next-check-promotion-2.json"
        malformed_promo.write_text("{ malformed json", encoding="utf-8")

        with self.assertLogs("k8s_diag_agent.health.ui", level=logging.WARNING) as cm:
            result = _build_promotions_index(external_analysis_dir, self.run_id)

        # Should have indexed 1 valid promotion
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["promotions"]), 1)

        # Should have logged a warning for the malformed artifact
        self.assertTrue(any("Skipped malformed promotion artifact" in msg for msg in cm.output))
        self.assertTrue(any("promotion-2" in msg for msg in cm.output))

    def test_valid_promotions_load_correctly(self) -> None:
        """Valid promotion artifacts load without warnings."""
        external_analysis_dir = self.tmpdir / "external-analysis"
        external_analysis_dir.mkdir()

        # Write valid promotions
        for i in range(2):
            promo = external_analysis_dir / f"{self.run_id}-next-check-promotion-{i}.json"
            promo.write_text(json.dumps({
                "status": "success",
                "run_id": self.run_id,
                "payload": {
                    "candidateId": f"candidate-{i}",
                    "promotionIndex": i,
                    "description": f"Test promotion {i}",
                    "clusterLabel": "cluster-a",
                },
            }), encoding="utf-8")

        with self.assertNoLogs("k8s_diag_agent.health.ui", level=logging.WARNING):
            result = _build_promotions_index(external_analysis_dir, self.run_id)

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(len(result["promotions"]), 2)


class TestWriteProposalStatusSummaryExceptionHandling(TestCase):
    """Test _write_proposal_status_summary_to_review handles write failures gracefully."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_text_oserror_is_skipped_with_warning(self) -> None:
        """write_text OSError is logged as warning and does not raise."""
        reviews_dir = self.tmpdir / "reviews"
        reviews_dir.mkdir()

        # Create a review file
        run_id = "write-test-20260101T000000Z"
        review_path = reviews_dir / f"{run_id}-review.json"
        review_path.write_text(json.dumps({
            "run_id": run_id,
            "timestamp": "2026-01-01T00:00:00Z",
        }), encoding="utf-8")

        # Make file unreadable to simulate write failure
        review_path.chmod(0o000)

        try:
            with self.assertLogs("k8s_diag_agent.health.ui", level=logging.WARNING) as cm:
                # This should NOT raise - it should be caught and logged
                _write_proposal_status_summary_to_review(
                    self.tmpdir,
                    run_id,
                    {"test": "summary"},
                )

            # Should have logged a warning
            self.assertTrue(any("Failed to write proposal status summary" in msg for msg in cm.output))
            self.assertTrue(any(review_path.name in msg for msg in cm.output))
        finally:
            # Restore permissions for cleanup
            review_path.chmod(0o644)

    def test_nonexistent_review_does_not_raise(self) -> None:
        """Nonexistent review file does not raise, just returns."""
        # Should not raise any exception
        _write_proposal_status_summary_to_review(
            self.tmpdir,
            "nonexistent-20260101T000000Z",
            {"test": "summary"},
        )
