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

from k8s_diag_agent.ui.server_read_support import (
    _load_proposals_for_run,
    _load_notifications_for_run,
    _scan_external_analysis,
    _build_run_artifact_index,
    _find_review_enrichment,
    _find_next_check_plan,
    _build_execution_history,
    _build_llm_stats_for_run,
    RunArtifactIndex,
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
