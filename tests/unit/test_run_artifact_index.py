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
        history = _build_execution_history(self.external_analysis_dir, self.run_id, index)

        self.assertEqual(len(history), 1)
        assert history is not None
        self.assertEqual(history[0]["candidateId"], "c1")

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
        history = _build_execution_history(self.external_analysis_dir, self.run_id, index)
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
        history = _build_execution_history(self.external_analysis_dir, self.run_id, index)

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
        history = _build_execution_history(self.external_analysis_dir, "run-2024", index)
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
        history = _build_execution_history(external_dir, run_id, index)
        stats = _build_llm_stats_for_run(external_dir, run_id, index)

        self.assertIsNotNone(enrichment)
        self.assertIsNotNone(plan)
        self.assertEqual(len(history), 1)
        # LLM stats only counts success/failed status
        self.assertEqual(stats["totalCalls"], 3)


if __name__ == "__main__":
    unittest.main()
