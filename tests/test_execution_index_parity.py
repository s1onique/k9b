"""Tests for execution index parity between index-backed and fresh worklist paths.

These tests verify that both paths use the same execution artifact discovery,
ensuring consistent execution summaries in Recent Runs.

Regression tests for: https://github.com/s1onique/k9b/issues/XXX
(Recent Runs latest-row execution summary lags behind Work list)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.health.ui import _build_recent_runs_summary
from k8s_diag_agent.ui.execution_index_utils import (
    _extract_run_id_from_filename,
    collect_execution_indices_for_all_runs,
    collect_execution_indices_for_run,
)


def _summary_runs(summary: dict[str, object]) -> list[dict[str, object]]:
    runs = summary.get("runs")
    assert isinstance(runs, list)
    assert all(isinstance(run, dict) for run in runs)
    return cast(list[dict[str, object]], runs)


class TestExtractRunIdFromFilename:
    """Tests for run_id extraction from execution artifact filenames."""

    def test_extracts_run_id_from_numbered_execution(self) -> None:
        """Should extract run_id from numbered execution artifacts."""
        filename = "health-run-20260515T215749Z-next-check-execution-0.json"
        assert _extract_run_id_from_filename(filename) == "health-run-20260515T215749Z"

    def test_extracts_run_id_from_plain_execution(self) -> None:
        """Should extract run_id from plain execution artifacts."""
        filename = "health-run-20260515T215749Z-next-check-execution.json"
        assert _extract_run_id_from_filename(filename) == "health-run-20260515T215749Z"

    def test_handles_run_id_with_hyphens(self) -> None:
        """Should handle run_ids that contain hyphens."""
        filename = "test-run-with-hyphens-next-check-execution-5.json"
        assert _extract_run_id_from_filename(filename) == "test-run-with-hyphens"

    def test_returns_none_for_invalid_filename(self) -> None:
        """Should return None for filenames without execution marker."""
        assert _extract_run_id_from_filename("random-file.json") is None
        assert _extract_run_id_from_filename("health-run-plan.json") is None


class TestCollectExecutionIndicesForAllRuns:
    """Tests for the shared one-pass collector."""

    def test_collects_execution_indices_for_all_runs(self, tmp_path: Path) -> None:
        """Should collect execution indices for all runs in one pass."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create execution artifacts for two runs
        run1_exec = {
            "purpose": "next-check-execution",
            "run_id": "run-test-001",
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        (ea_dir / "run-test-001-next-check-execution-0.json").write_text(
            json.dumps(run1_exec), encoding="utf-8"
        )

        run2_exec = {
            "purpose": "next-check-execution",
            "run_id": "run-test-002",
            "status": "failed",
            "payload": {"candidateIndex": 1},
        }
        (ea_dir / "run-test-002-next-check-execution-1.json").write_text(
            json.dumps(run2_exec), encoding="utf-8"
        )

        # Collect all indices
        execution_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Verify both runs are captured
        assert "run-test-001" in execution_indices
        assert "run-test-002" in execution_indices

        # Verify indices and status
        assert execution_indices["run-test-001"][0] == "success"
        assert execution_indices["run-test-002"][1] == "failed"

        # Verify diagnostics
        assert diagnostics["total_execution_artifacts_found"] == 2
        assert diagnostics["total_execution_artifacts_matched"] == 2
        run_ids_discovered = diagnostics["run_ids_discovered"]
        assert isinstance(run_ids_discovered, list)
        assert "run-test-001" in run_ids_discovered
        assert "run-test-002" in run_ids_discovered

    def test_prefers_artifact_run_id_over_filename(self, tmp_path: Path) -> None:
        """Should use artifact run_id field as primary, filename as fallback."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create execution artifact where filename run_id differs from artifact field
        execution = {
            "purpose": "next-check-execution",
            "run_id": "actual-run-id",  # Primary: from artifact field
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        # Filename has different run_id
        (ea_dir / "filename-run-id-next-check-execution-0.json").write_text(
            json.dumps(execution), encoding="utf-8"
        )

        # Collect all indices
        execution_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Should use artifact field's run_id
        assert "actual-run-id" in execution_indices
        assert "filename-run-id" not in execution_indices
        assert execution_indices["actual-run-id"][0] == "success"

    def test_skips_artifacts_with_invalid_purpose(self, tmp_path: Path) -> None:
        """Should skip artifacts with non-execution purpose."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create execution artifact with wrong purpose
        # IMPORTANT: Filename must match the glob pattern *-next-check-execution*.json
        # to be scanned by the collector
        execution = {
            "purpose": "alertmanager-review",  # Wrong purpose
            "run_id": "run-test",
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        # Filename matches glob pattern so it will be scanned, then skipped by purpose check
        (ea_dir / "run-test-next-check-execution-0.json").write_text(
            json.dumps(execution), encoding="utf-8"
        )

        # Collect all indices
        execution_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Should be skipped due to purpose mismatch
        assert "run-test" not in execution_indices
        # The artifact matches the glob but has wrong purpose, so it's skipped
        assert diagnostics["total_execution_artifacts_skipped_purpose_mismatch"] == 1

    def test_handles_ten_execution_artifacts(self, tmp_path: Path) -> None:
        """Should correctly collect 10 execution artifacts (regression test)."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260515T215749Z"

        # Create 10 execution artifacts (10 candidates, all executed)
        # 9 success, 1 failed
        statuses = {
            0: "success",
            1: "success",
            2: "success",
            3: "success",
            4: "failed",  # 1 failed
            5: "success",
            6: "success",
            7: "success",
            8: "success",
            9: "success",
        }

        for idx, status in statuses.items():
            execution = {
                "purpose": "next-check-execution",
                "run_id": run_id,
                "status": status,
                "payload": {"candidateIndex": idx},
            }
            (ea_dir / f"{run_id}-next-check-execution-{idx}.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )

        # Collect all indices
        execution_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Verify all 10 executions are captured
        assert run_id in execution_indices
        run_indices = execution_indices[run_id]
        assert len(run_indices) == 10, f"Expected 10, got {len(run_indices)}"

        # Verify all indices are present
        for idx in range(10):
            assert idx in run_indices, f"Index {idx} missing"

        # Verify statuses
        assert run_indices[0] == "success"
        assert run_indices[4] == "failed"  # The failed one

        # Verify diagnostics
        assert diagnostics["total_execution_artifacts_matched"] == 10
        assert diagnostics["total_execution_artifacts_found"] == 10


class TestExecutionIndexParity:
    """Tests for parity between index-backed and fresh worklist paths."""

    def test_ten_execution_artifact_parity(self, tmp_path: Path) -> None:
        """Regression test: 10 execution artifacts should be found by both paths.

        This test verifies the exact scenario from the bug report:
        - Run: health-run-20260515T215749Z
        - 10 candidates, all executed
        - 1 failed
        - Fresh worklist path finds all 10, index path finds 0

        After the fix, both paths should find all 10.
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260515T215749Z"

        # Create review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps({
                "run_id": run_id,
                "run_label": "Latest Run",
                "timestamp": "2026-05-15T21:57:49Z",
                "cluster_count": 1,
            }),
            encoding="utf-8",
        )

        # Create plan with 10 candidates
        plan = {
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": f"Check {i}",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                }
                for i in range(10)
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create 10 execution artifacts (9 success, 1 failed)
        statuses = {
            0: "success",
            1: "success",
            2: "success",
            3: "success",
            4: "failed",  # 1 failed
            5: "success",
            6: "success",
            7: "success",
            8: "success",
            9: "success",
        }

        for idx, status in statuses.items():
            execution = {
                "purpose": "next-check-execution",
                "run_id": run_id,
                "status": status,
                "payload": {"candidateIndex": idx},
            }
            (ea_dir / f"{run_id}-next-check-execution-{idx}.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )

        # Test index-backed path
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        execution_indices_obj = summary.get("_execution_indices", {})
        assert isinstance(execution_indices_obj, dict)
        execution_indices = cast(dict[str, dict[int, str]], execution_indices_obj)

        # CRITICAL: Index path should find all 10 executions
        assert run_id in execution_indices, f"run_id {run_id} should be in execution_indices"
        run_exec_indices = execution_indices[run_id]
        assert len(run_exec_indices) == 10, f"Expected 10, got {len(run_exec_indices)}"

        # Test per-run collector (used by index path)
        per_run_indices = collect_execution_indices_for_run(ea_dir, run_id)
        assert len(per_run_indices) == 10, f"Per-run collector: expected 10, got {len(per_run_indices)}"

        # Test one-pass collector (used by fresh worklist path)
        all_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)
        assert run_id in all_indices, "One-pass collector: run_id should be found"
        assert len(all_indices[run_id]) == 10, f"One-pass collector: expected 10, got {len(all_indices[run_id])}"

        # Verify batch eligibility computed correctly
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibility"] == "computed"
        # All 10 executed, so batchEligibleCount should be 0
        assert run["batchEligibleCount"] == 0, f"Expected 0 eligible, got {run['batchEligibleCount']}"
        assert run["batchExecutable"] is False

    def test_mixed_run_execution_artifacts(self, tmp_path: Path) -> None:
        """Should correctly separate execution artifacts across multiple runs."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run1_id = "health-run-20260515T213738Z"
        run2_id = "health-run-20260515T215749Z"

        # Create reviews for both runs
        for run_id in [run1_id, run2_id]:
            (reviews_dir / f"{run_id}-review.json").write_text(
                json.dumps({
                    "run_id": run_id,
                    "run_label": f"Run {run_id}",
                    "timestamp": "2026-05-15T21:00:00Z",
                    "cluster_count": 1,
                }),
                encoding="utf-8",
            )

        # Create plans for both runs
        for run_id in [run1_id, run2_id]:
            plan = {
                "purpose": "next-check-planning",
                "candidates": [
                    {
                        "suggestedCommandFamily": "kubectl",
                        "description": "Check 1",
                        "targetContext": "default/cluster-a",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                    }
                ],
            }
            (ea_dir / f"{run_id}-next-check-plan.json").write_text(
                json.dumps(plan), encoding="utf-8"
            )

        # Create 3 executions for run1, 5 for run2
        for idx in range(3):
            execution = {
                "purpose": "next-check-execution",
                "run_id": run1_id,
                "status": "success",
                "payload": {"candidateIndex": idx},
            }
            (ea_dir / f"{run1_id}-next-check-execution-{idx}.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )

        for idx in range(5):
            execution = {
                "purpose": "next-check-execution",
                "run_id": run2_id,
                "status": "success",
                "payload": {"candidateIndex": idx},
            }
            (ea_dir / f"{run2_id}-next-check-execution-{idx}.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )

        # Test one-pass collector
        all_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Both runs should have their respective execution counts
        assert len(all_indices.get(run1_id, {})) == 3, f"Run1 should have 3, got {len(all_indices.get(run1_id, {}))}"
        assert len(all_indices.get(run2_id, {})) == 5, f"Run2 should have 5, got {len(all_indices.get(run2_id, {}))}"

        # Diagnostics should show total of 8 found
        assert diagnostics["total_execution_artifacts_matched"] == 8

    def test_execution_artifacts_without_run_id_field(self, tmp_path: Path) -> None:
        """Should fall back to filename parsing when run_id field is missing."""
        ea_dir = tmp_path / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "test-run-no-run-id-field"

        # Create execution artifact WITHOUT run_id field
        execution = {
            "purpose": "next-check-execution",
            # No run_id field - should fall back to filename
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        (ea_dir / f"{run_id}-next-check-execution-0.json").write_text(
            json.dumps(execution), encoding="utf-8"
        )

        # Collect all indices
        execution_indices, diagnostics = collect_execution_indices_for_all_runs(ea_dir)

        # Should still find it via filename parsing
        assert run_id in execution_indices, f"run_id {run_id} should be found via filename"
        assert execution_indices[run_id][0] == "success"


class TestBatchEligibilityWithExecutionParity:
    """Tests for batch eligibility computation with execution parity."""

    def test_fully_executed_run_shows_zero_eligible(self, tmp_path: Path) -> None:
        """A fully executed run should show batchEligibleCount=0."""
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "fully-executed-run"

        # Create review
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps({
                "run_id": run_id,
                "run_label": "Fully Executed Run",
                "timestamp": "2026-05-15T22:00:00Z",
                "cluster_count": 1,
            }),
            encoding="utf-8",
        )

        # Create plan with 5 executable candidates
        plan = {
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": f"Check {i}",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                }
                for i in range(5)
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create execution artifacts for all 5 candidates
        for idx in range(5):
            execution = {
                "purpose": "next-check-execution",
                "run_id": run_id,
                "status": "success" if idx < 4 else "failed",
                "payload": {"candidateIndex": idx},
            }
            (ea_dir / f"{run_id}-next-check-execution-{idx}.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )

        # Build summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        runs = _summary_runs(summary)
        run = runs[0]

        # All candidates executed, so no eligible remain
        assert run["batchEligibility"] == "computed"
        assert run["batchEligibleCount"] == 0
        assert run["batchExecutable"] is False

        # Verify execution indices captured correctly
        execution_indices_obj = summary.get("_execution_indices", {})
        execution_indices = cast(dict[str, dict[int, str]], execution_indices_obj)
        assert len(execution_indices[run_id]) == 5
        # 1 failed
        assert sum(1 for status in execution_indices[run_id].values() if status == "failed") == 1
