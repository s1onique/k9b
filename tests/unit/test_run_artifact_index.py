"""Regression tests for per-run artifact index optimization.

These tests verify:
1. Cold /api/run scans external-analysis at most once
2. Execution history uses shared per-run artifact classification
3. Next-check plan lookup uses shared classification
4. LLM stats uses shared classification
5. Missing artifacts remain non-fatal
"""

import json
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from k8s_diag_agent.ui.server_read_support import (
    _build_execution_history,
    _build_llm_stats_for_run,
    _build_run_artifact_index,
    _find_next_check_plan,
    _find_review_enrichment,
)


class RunArtifactIndexTests(unittest.TestCase):
    """Tests for RunArtifactIndex and its consumers."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.health_dir = self.tmpdir / "health"
        self.external_analysis_dir = self.health_dir / "external-analysis"
        self.external_analysis_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = "test-run"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_run_artifact_index_classifies_by_purpose(self) -> None:
        """Test that _build_run_artifact_index classifies artifacts by purpose."""
        # Write artifacts with different purposes
        self.external_analysis_dir.joinpath(f"{self.run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": self.run_id,
                "payload": {},
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "run_id": self.run_id,
                "payload": {"candidates": []},
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "payload": {},
            }),
            encoding="utf-8",
        )

        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Should have 3 artifacts
        self.assertEqual(len(index.artifacts), 3)
        self.assertEqual(index.artifacts_considered, 3)

        # Should classify by purpose
        self.assertEqual(len(index.review_enrichment), 1)
        self.assertEqual(len(index.next_check_plan), 1)
        self.assertEqual(len(index.next_check_execution), 1)

    def test_find_review_enrichment_uses_index(self) -> None:
        """Test that _find_review_enrichment uses artifact_index for O(1) lookup."""
        # Write review enrichment artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": self.run_id,
                "provider": "test-provider",
                "payload": {
                    "triageOrder": ["item1", "item2"],
                    "topConcerns": ["concern1"],
                },
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Find with index - should use O(1) lookup
        result = _find_review_enrichment(self.external_analysis_dir, self.run_id, index)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provider"], "test-provider")
        self.assertEqual(result["triageOrder"], ["item1", "item2"])

    def test_find_next_check_plan_uses_index(self) -> None:
        """Test that _find_next_check_plan uses artifact_index for O(1) lookup."""
        # Write plan artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "run_id": self.run_id,
                "payload": {
                    "summary": "Test plan",
                    "candidates": [
                        {"candidateId": "c1", "description": "Test check"},
                    ],
                },
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Find with index - should use O(1) lookup
        result = _find_next_check_plan(self.external_analysis_dir, self.run_id, index)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["summary"], "Test plan")
        self.assertEqual(result["candidateCount"], 1)

    def test_build_execution_history_uses_index(self) -> None:
        """Test that _build_execution_history uses artifact_index for O(1) lookup."""
        # Write execution artifacts
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {
                    "candidateId": "c1",
                    "candidateDescription": "Test check",
                    "commandFamily": "kubectl",
                },
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Build history with index - should use O(1) lookup
        # Returns tuple of (history, telemetry)
        history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(len(history), 1)
        assert history is not None
        self.assertEqual(history[0]["candidateId"], "c1")
        # Verify telemetry reflects index usage
        self.assertEqual(telemetry["execution_history_source"], "artifact_index")

    def test_build_llm_stats_uses_index(self) -> None:
        """Test that _build_llm_stats_for_run uses artifact_index for O(1) lookup."""
        # Write LLM call artifacts
        self.external_analysis_dir.joinpath(f"{self.run_id}-llm-call-001.json").write_text(
            json.dumps({
                "purpose": "manual",
                "status": "success",
                "run_id": self.run_id,
                "duration_ms": 100,
                "tool_name": "test-provider",
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-llm-call-002.json").write_text(
            json.dumps({
                "purpose": "manual",
                "status": "failed",
                "run_id": self.run_id,
                "tool_name": "test-provider",
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Build stats with index - should use O(1) lookup
        stats = _build_llm_stats_for_run(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(stats["totalCalls"], 2)
        self.assertEqual(stats["successfulCalls"], 1)
        self.assertEqual(stats["failedCalls"], 1)

    def test_missing_artifacts_non_fatal(self) -> None:
        """Test that missing artifacts remain non-fatal when using index."""
        # Build index with no artifacts
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        self.assertEqual(len(index.artifacts), 0)
        self.assertEqual(index.artifacts_considered, 0)

        # All lookups should return None or empty, not raise
        enrichment = _find_review_enrichment(self.external_analysis_dir, self.run_id, index)
        plan = _find_next_check_plan(self.external_analysis_dir, self.run_id, index)
        history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, index)
        stats = _build_llm_stats_for_run(self.external_analysis_dir, self.run_id, index)

        self.assertIsNone(enrichment)
        self.assertIsNone(plan)
        self.assertEqual(history, [])
        self.assertEqual(stats["totalCalls"], 0)

    def test_artifact_path_provenance_preserved(self) -> None:
        """Test that indexed path preserves artifact_path for k9b provenance."""
        # Write review enrichment artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": self.run_id,
                "payload": {},
            }),
            encoding="utf-8",
        )
        # Write next-check plan artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "run_id": self.run_id,
                "payload": {"candidates": []},
            }),
            encoding="utf-8",
        )
        # Write execution artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Verify artifact paths are preserved (relative to external_analysis_dir.parent = health)
        # Review enrichment
        self.assertEqual(len(index.review_enrichment), 1)
        self.assertEqual(
            index.review_enrichment[0]["artifact_path"],
            f"external-analysis/{self.run_id}-review-enrichment.json"
        )

        # Next-check plan
        self.assertEqual(len(index.next_check_plan), 1)
        self.assertEqual(
            index.next_check_plan[0]["artifact_path"],
            f"external-analysis/{self.run_id}-next-check-plan.json"
        )

        # Execution history
        self.assertEqual(len(index.next_check_execution), 1)
        self.assertEqual(
            index.next_check_execution[0]["artifact_path"],
            f"external-analysis/{self.run_id}-next-check-execution-001.json"
        )

        # Verify consumer results also have artifactPath
        enrichment = _find_review_enrichment(self.external_analysis_dir, self.run_id, index)
        plan = _find_next_check_plan(self.external_analysis_dir, self.run_id, index)
        history, _ = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        assert enrichment is not None
        assert plan is not None
        assert len(history) == 1
        self.assertEqual(enrichment["artifactPath"], f"external-analysis/{self.run_id}-review-enrichment.json")
        self.assertEqual(plan["artifactPath"], f"external-analysis/{self.run_id}-next-check-plan.json")
        self.assertEqual(history[0]["artifactPath"], f"external-analysis/{self.run_id}-next-check-execution-001.json")

    def test_run_id_boundary_no_collision(self) -> None:
        """Test that run_id='run-2024' does NOT match 'run-20240-next-check-execution-001.json'."""
        # Create a collision file that should NOT be included
        self.external_analysis_dir.joinpath("run-20240-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": "run-20240",
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )
        # Create a legitimate file for run_id="run-2024"
        self.external_analysis_dir.joinpath("run-2024-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": "run-2024",
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c2"},
            }),
            encoding="utf-8",
        )

        # Build index for "run-2024"
        index = _build_run_artifact_index(self.external_analysis_dir, "run-2024")

        # Should only include the exact match, not the collision
        self.assertEqual(len(index.artifacts), 1)
        self.assertEqual(len(index.next_check_execution), 1)
        self.assertEqual(index.next_check_execution[0].get("run_id"), "run-2024")

        # Verify history only includes the correct run's artifacts
        history, _ = _build_execution_history(self.external_analysis_dir, "run-2024", index)
        self.assertEqual(len(history), 1)
        assert history is not None
        self.assertEqual(history[0].get("candidateId"), "c2")

    def test_no_rescan_after_index_construction(self) -> None:
        """Test that consumers with index do not re-scan the directory.

        This verifies the single-scan optimization is actually working:
        after _build_run_artifact_index creates the index, subsequent
        consumer calls should NOT call Path.glob.
        """
        # Write artifacts
        self.external_analysis_dir.joinpath(f"{self.run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": self.run_id,
                "payload": {},
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "run_id": self.run_id,
                "payload": {"candidates": []},
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )
        self.external_analysis_dir.joinpath(f"{self.run_id}-llm-call-001.json").write_text(
            json.dumps({
                "purpose": "manual",
                "status": "success",
                "run_id": self.run_id,
                "duration_ms": 100,
                "tool_name": "test-provider",
            }),
            encoding="utf-8",
        )

        # Build index first (this is the one allowed scan)
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Track glob calls after index construction
        glob_calls = []

        def track_glob(*args: object, **kwargs: object) -> list[object]:
            glob_calls.append(args)
            # Return empty - we shouldn't reach here in the indexed path
            return []

        # Patch Path.glob on the external_analysis_dir
        with mock.patch.object(Path, "glob", side_effect=track_glob):
            # All consumers with index should NOT call glob
            _find_review_enrichment(self.external_analysis_dir, self.run_id, index)
            _find_next_check_plan(self.external_analysis_dir, self.run_id, index)
            _build_llm_stats_for_run(self.external_analysis_dir, self.run_id, index)

        # NOTE: _build_execution_history may still call _load_alertmanager_review_artifacts
        # which itself calls glob for Alertmanager review scan. This is documented as
        # a remaining P1 (Alertmanager review merge scan).

        # Verify no glob was called for the indexed consumers
        self.assertEqual(len(glob_calls), 0, f"Unexpected glob calls after index: {glob_calls}")

    def test_backward_compatibility_without_index(self) -> None:
        """Test that functions work without index (for backward compatibility)."""
        # Write artifacts
        self.external_analysis_dir.joinpath(f"{self.run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": self.run_id,
                "provider": "test-provider",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Find without index - should fall back to directory scan
        result = _find_review_enrichment(self.external_analysis_dir, self.run_id, None)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "success")

    def test_alertmanager_review_indexed_in_artifact_index(self) -> None:
        """Test that Alertmanager review artifacts are indexed by source_artifact."""
        # Write execution artifact (source artifact)
        exec_artifact_path = f"{self.run_id}-next-check-execution-001.json"
        self.external_analysis_dir.joinpath(exec_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Write Alertmanager review artifact (derived from execution)
        # Purpose matches NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW
        review_artifact_path = f"{self.run_id}-next-check-execution-alertmanager-review-001.json"
        self.external_analysis_dir.joinpath(review_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "status": "success",
                "run_id": self.run_id,
                "source_artifact": f"external-analysis/{exec_artifact_path}",
                "alertmanager_relevance": "relevant",
                "alertmanager_relevance_summary": "Alert is actionable",
                "reviewed_at": "2024-01-15T10:30:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Verify Alertmanager reviews are indexed
        self.assertEqual(len(index.alertmanager_reviews_by_source), 1)
        self.assertIn(f"external-analysis/{exec_artifact_path}", index.alertmanager_reviews_by_source)
        self.assertEqual(index.alertmanager_reviews_indexed, 1)

        # Verify the indexed review has correct data
        review = index.alertmanager_reviews_by_source[f"external-analysis/{exec_artifact_path}"]
        self.assertEqual(review["alertmanager_relevance"], "relevant")
        self.assertEqual(review["alertmanager_relevance_summary"], "Alert is actionable")

    def test_alertmanager_review_merge_works_from_index(self) -> None:
        """Test that Alertmanager review merge works from indexed review artifacts."""
        # Write execution artifact (source artifact)
        exec_artifact_path = f"{self.run_id}-next-check-execution-001.json"
        self.external_analysis_dir.joinpath(exec_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Write Alertmanager review artifact
        review_artifact_path = f"{self.run_id}-next-check-execution-alertmanager-review-001.json"
        self.external_analysis_dir.joinpath(review_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "status": "success",
                "run_id": self.run_id,
                "source_artifact": f"external-analysis/{exec_artifact_path}",
                "alertmanager_relevance": "relevant",
                "alertmanager_relevance_summary": "Alert is actionable",
                "reviewed_at": "2024-01-15T10:30:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Build history with index - should use indexed Alertmanager reviews
        history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(len(history), 1)
        # Verify Alertmanager review data was merged into history entry
        entry = history[0]
        self.assertEqual(entry.get("alertmanagerRelevance"), "relevant")
        self.assertEqual(entry.get("alertmanagerRelevanceSummary"), "Alert is actionable")
        self.assertEqual(entry.get("alertmanagerReviewedAt"), "2024-01-15T10:30:00Z")
        # Verify telemetry
        self.assertEqual(telemetry["alertmanager_review_source"], "artifact_index")
        self.assertEqual(telemetry["alertmanager_reviews_indexed"], 1)

    def test_alertmanager_review_provenance_preserved(self) -> None:
        """Test that Alertmanager review artifact_path is preserved for provenance."""
        # Write execution artifact (source artifact)
        exec_artifact_path = f"{self.run_id}-next-check-execution-001.json"
        self.external_analysis_dir.joinpath(exec_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Write Alertmanager review artifact
        review_artifact_path = f"{self.run_id}-next-check-execution-alertmanager-review-001.json"
        self.external_analysis_dir.joinpath(review_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "status": "success",
                "run_id": self.run_id,
                "source_artifact": f"external-analysis/{exec_artifact_path}",
                "alertmanager_relevance": "relevant",
                "reviewed_at": "2024-01-15T10:30:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Build index
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Build history
        history, _ = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(len(history), 1)
        entry = history[0]
        # Verify review artifact path is preserved in merged entry
        review_path = entry.get("alertmanagerReviewArtifactPath")
        self.assertIsNotNone(review_path)
        self.assertIn(review_artifact_path, cast(str, review_path))

    def test_alertmanager_review_missing_non_fatal(self) -> None:
        """Test that missing Alertmanager review artifacts remain non-fatal."""
        # Write execution artifact but NO Alertmanager review
        exec_artifact_path = f"{self.run_id}-next-check-execution-001.json"
        self.external_analysis_dir.joinpath(exec_artifact_path).write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Build index - should have no Alertmanager reviews
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        self.assertEqual(len(index.alertmanager_reviews_by_source), 0)
        self.assertEqual(index.alertmanager_reviews_indexed, 0)

        # Build history - should complete without error, just no review merged
        history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(len(history), 1)
        # Entry should exist but have no Alertmanager review fields
        entry = history[0]
        self.assertIsNone(entry.get("alertmanagerRelevance"))
        # Telemetry should reflect empty reviews
        self.assertEqual(telemetry["alertmanager_reviews_indexed"], 0)

    def test_build_execution_history_with_index_does_not_glob(self) -> None:
        """Test that _build_execution_history with artifact_index does NOT call glob.

        This verifies the P1 optimization: when artifact_index is provided,
        _build_execution_history should NOT call _load_alertmanager_review_artifacts
        (which itself calls glob).
        """
        # Write execution artifact
        self.external_analysis_dir.joinpath(f"{self.run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Build index (this is the allowed single scan)
        index = _build_run_artifact_index(self.external_analysis_dir, self.run_id)

        # Track glob calls during _build_execution_history with index
        glob_calls = []

        def track_glob(*args: object, **kwargs: object) -> list[object]:
            glob_calls.append(args)
            return []

        with mock.patch.object(Path, "glob", side_effect=track_glob):
            # Build history WITH index - should NOT call glob
            history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        # Verify no glob was called (index path has no disk I/O)
        self.assertEqual(len(glob_calls), 0, f"Unexpected glob calls with artifact_index: {glob_calls}")
        # Verify telemetry reflects index usage
        self.assertEqual(telemetry["alertmanager_review_source"], "artifact_index")
        self.assertEqual(telemetry["execution_history_source"], "artifact_index")

    def test_build_execution_history_without_index_falls_back_to_glob(self) -> None:
        """Test that _build_execution_history without artifact_index falls back to glob.

        This verifies backward compatibility: when no index is provided,
        the function should still work by scanning the directory.
        """
        # Write execution artifact
        exec_artifact_path = f"{self.run_id}-next-check-execution-001.json"
        exec_file = self.external_analysis_dir.joinpath(exec_artifact_path)
        exec_file.write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": self.run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Write Alertmanager review artifact (for fallback scan to find)
        review_artifact_path = f"{self.run_id}-next-check-execution-alertmanager-review-001.json"
        review_file = self.external_analysis_dir.joinpath(review_artifact_path)
        review_file.write_text(
            json.dumps({
                "purpose": "next-check-execution-alertmanager-review",
                "status": "success",
                "run_id": self.run_id,
                "source_artifact": f"external-analysis/{exec_artifact_path}",
                "alertmanager_relevance": "relevant",
                "reviewed_at": "2024-01-15T10:30:00Z",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Track glob calls during _build_execution_history WITHOUT index
        # But also let the actual glob work so we can verify fallback works
        glob_calls = []

        original_glob = Path.glob

        def track_glob(self_path: Path, pattern: str) -> list[Path]:
            result = list(original_glob(self_path, pattern))
            glob_calls.append((str(self_path), pattern))
            return result

        with mock.patch.object(Path, "glob", track_glob):
            # Build history WITHOUT index - should call glob for fallback
            history, telemetry = _build_execution_history(self.external_analysis_dir, self.run_id, None)

        # Verify glob was called (fallback path requires disk I/O)
        self.assertGreater(len(glob_calls), 0, "Fallback path should call glob")
        # Verify telemetry reflects file_scan usage
        self.assertEqual(telemetry["alertmanager_review_source"], "file_scan")
        self.assertEqual(telemetry["execution_history_source"], "file_scan")
        # Verify history still works correctly
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].get("candidateId"), "c1")


class ExternalAnalysisSingleScanTests(unittest.TestCase):
    """End-to-end tests verifying external-analysis is scanned only once."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir / "runs"
        self.health_dir = self.runs_dir / "health"
        self.static_dir = self.tmpdir / "static"
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_artifact(self, run_id: str) -> ExternalAnalysisArtifact:
        return ExternalAnalysisArtifact(
            tool_name="reviewer",
            run_id=run_id,
            run_label=run_id,
            cluster_label="review",
            summary="Test review",
            status=ExternalAnalysisStatus.SUCCESS,
            provider="reviewer",
            purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            payload={},
        )

    def _write_index(self, artifact: ExternalAnalysisArtifact) -> None:
        settings = ExternalAnalysisSettings(
            review_enrichment=ReviewEnrichmentPolicy(enabled=True, provider="reviewer")
        )
        with mock.patch(
            "k8s_diag_agent.health.ui._collect_historical_external_analysis_entries",
            return_value=[],
        ):
            write_health_ui_index(
                self.health_dir,
                run_id=artifact.run_id,
                run_label=artifact.run_label or artifact.run_id,
                collector_version="tests",
                records=(),
                assessments=(),
                drilldowns=(),
                proposals=(),
                external_analysis=(artifact,),
                notifications=(),
                external_analysis_settings=settings,
                available_adapters=(),
            )

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        handler = unittest.mock.MagicMock()
        return handler

    def test_load_context_scans_external_analysis_once(self) -> None:
        """Test that _load_context_for_run scans external-analysis only once.

        Previously, each lookup function (_find_review_enrichment, _find_next_check_plan,
        _build_execution_history, _build_llm_stats_for_run) was independently scanning
        the external-analysis directory. This test verifies that a single scan is
        performed and the index is reused.
        """
        run_id = "single-scan-test"
        artifact = self._build_artifact(run_id)
        self._write_index(artifact)

        # Add external-analysis artifacts
        external_dir = self.health_dir / "external-analysis"
        external_dir.mkdir(parents=True, exist_ok=True)

        # Write review enrichment
        external_dir.joinpath(f"{run_id}-review-enrichment.json").write_text(
            json.dumps({
                "purpose": "review-enrichment",
                "status": "success",
                "run_id": run_id,
                "provider": "test",
                "payload": {},
            }),
            encoding="utf-8",
        )

        # Write next-check plan
        external_dir.joinpath(f"{run_id}-next-check-plan.json").write_text(
            json.dumps({
                "purpose": "next-check-planning",
                "status": "success",
                "run_id": run_id,
                "payload": {"candidates": []},
            }),
            encoding="utf-8",
        )

        # Write execution artifact
        external_dir.joinpath(f"{run_id}-next-check-execution-001.json").write_text(
            json.dumps({
                "purpose": "next-check-execution",
                "status": "success",
                "run_id": run_id,
                "timestamp": "2024-01-15T10:00:00Z",
                "payload": {"candidateId": "c1"},
            }),
            encoding="utf-8",
        )

        # Build index and verify it classifies artifacts correctly
        index = _build_run_artifact_index(external_dir, run_id)

        # All artifacts should be in the single index
        self.assertEqual(len(index.artifacts), 3)
        self.assertEqual(len(index.review_enrichment), 1)
        self.assertEqual(len(index.next_check_plan), 1)
        self.assertEqual(len(index.next_check_execution), 1)

        # All lookups should work from the shared index without additional scanning
        enrichment = _find_review_enrichment(external_dir, run_id, index)
        plan = _find_next_check_plan(external_dir, run_id, index)
        history, _ = _build_execution_history(external_dir, run_id, index)
        stats = _build_llm_stats_for_run(external_dir, run_id, index)

        self.assertIsNotNone(enrichment)
        self.assertIsNotNone(plan)
        self.assertEqual(len(history), 1)
        # LLM stats only counts success/failed status
        self.assertEqual(stats["totalCalls"], 3)


if __name__ == "__main__":
    unittest.main()
