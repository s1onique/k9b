"""Tests for stale index freshness after batch execution.

These tests verify that when execution artifacts are written after ui-index.json
was generated, the API correctly detects stale execution indices and recomputes
them from the filesystem.

The production fix:
- cache key uses max(ui-index mtime, external-analysis mtime)
- if external-analysis is fresher than ui-index, api.py recomputes execution
  indices from filesystem using collect_execution_indices_for_all_runs()
"""

from __future__ import annotations

import json
import os
import time as time_module
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import build_runs_list


def _payload_runs(payload: dict[str, object]) -> list[dict[str, object]]:
    """Helper to narrow payload["runs"] type for mypy."""
    runs = payload.get("runs")
    assert isinstance(runs, list)
    assert all(isinstance(run, dict) for run in runs)
    return cast(list[dict[str, object]], runs)


def _execution_summary(run: dict[str, object]) -> dict[str, object] | None:
    """Helper to extract executionSummary from a run entry."""
    summary = run.get("executionSummary")
    if summary is None:
        return None
    return cast(dict[str, object], summary)


class MockHandler:
    """Mock handler for testing build_runs_list_payload."""

    def __init__(self, runs_dir: Path):
        self.runs_dir = runs_dir
        self._health_root = runs_dir / "health"


def _make_execution_artifact(run_id: str, candidate_index: int, status: str) -> dict[str, object]:
    """Create a next-check-execution artifact."""
    return {
        "purpose": "next-check-execution",
        "run_id": run_id,
        "payload": {"candidateIndex": candidate_index},
        "status": status,
    }


def _make_plan_artifact(run_id: str, candidate_count: int) -> dict[str, object]:
    """Create a next-check-plan artifact with executable candidates."""
    candidates = []
    for i in range(candidate_count):
        candidates.append({
            "description": f"Check {i}",
            "suggestedCommandFamily": "kubectl",
            "safeToAutomate": True,
            "targetContext": "default",
            "requiresOperatorApproval": False,
        })
    return {
        "purpose": "next-check-planning",
        "run_id": run_id,
        "payload": {"candidates": candidates},
    }


class TestStaleIndexAfterBatchExecution:
    """Tests for stale index freshness after batch execution.

    These tests verify that when execution artifacts are written after
    ui-index.json was generated, the API correctly detects stale execution
    indices and recomputes them from the filesystem.
    """

    def test_full_execution_after_stale_index(self, tmp_path: Path) -> None:
        """After all 5 candidates are executed, execution state must be fresh.

        Setup:
        - ui-index with 5 executable candidates, no execution indices
        - stale row: batchExecutable=true, batchEligibleCount=5

        Action:
        - Write 5 execution artifacts (all candidates executed)
        - Force external-analysis mtime > ui-index mtime

        Expected:
        - executionSummary.executedCandidates == 5
        - executionSummary.pendingExecutableCandidates == 0
        - executionSummary.batchExecutionState == "fully-executed"
        - batchExecutable is False
        - batchEligibleCount == 0
        - timings include index_stale_execution_indices=True
        - timings include index_execution_indices_recomputed=True
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact with 5 executable candidates
        plan = _make_plan_artifact("test-run", 5)
        (ea_dir / "test-run-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create ui-index.json with stale execution state
        # _plan_data has 5 candidates, _execution_indices is empty
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
                "_plan_data": {"test-run": plan},
                "_execution_indices": {},  # Empty - stale state
            },
        }
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set ui-index.json mtime to old
        old_time = 1000000000.0
        os.utime(ui_index_path, (old_time, old_time))

        # First call - should return stale state
        runs_dir = tmp_path
        payload1, timings1 = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        payload1 = cast(dict[str, object], payload1)
        runs1 = _payload_runs(payload1)
        assert len(runs1) == 1

        # Verify stale state
        assert runs1[0]["batchExecutable"] is True
        assert runs1[0]["batchEligibleCount"] == 5
        summary1 = _execution_summary(runs1[0])
        assert summary1 is not None
        assert summary1["executedCandidates"] == 0
        assert summary1["pendingExecutableCandidates"] == 5
        assert summary1["batchExecutionState"] == "not-started"

        # Write execution artifacts for all 5 candidates
        time_module.sleep(0.01)
        for i in range(5):
            exec_artifact = _make_execution_artifact("test-run", i, "success")
            (ea_dir / f"test-run-next-check-execution-{i}.json").write_text(
                json.dumps(exec_artifact), encoding="utf-8"
            )

        # Force external-analysis mtime > ui-index mtime
        time_module.sleep(0.01)
        new_time = 1000000100.0
        os.utime(ea_dir, (new_time, new_time))

        # Verify external-analysis is indeed newer
        assert ea_dir.stat().st_mtime > ui_index_path.stat().st_mtime

        # Second call - must return fresh execution state
        payload2, timings2 = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        payload2 = cast(dict[str, object], payload2)
        runs2 = _payload_runs(payload2)
        assert len(runs2) == 1

        # Verify fresh state after full execution
        summary2 = _execution_summary(runs2[0])
        assert summary2 is not None
        assert summary2["executedCandidates"] == 5, (
            f"Expected 5 executed, got {summary2['executedCandidates']}"
        )
        assert summary2["pendingExecutableCandidates"] == 0, (
            f"Expected 0 pending, got {summary2['pendingExecutableCandidates']}"
        )
        assert summary2["batchExecutionState"] == "fully-executed", (
            f"Expected fully-executed, got {summary2['batchExecutionState']}"
        )
        assert runs2[0]["batchExecutable"] is False, (
            "batchExecutable should be False after all executed"
        )
        assert runs2[0]["batchEligibleCount"] == 0, (
            f"batchEligibleCount should be 0, got {runs2[0]['batchEligibleCount']}"
        )

        # Verify timing flags
        assert timings2.get("index_stale_execution_indices") is True, (
            "index_stale_execution_indices should be True"
        )
        assert timings2.get("index_execution_indices_recomputed") is True, (
            "index_execution_indices_recomputed should be True"
        )

    def test_partial_execution_after_stale_index(self, tmp_path: Path) -> None:
        """After 3 of 5 candidates are executed, execution state must be fresh.

        Setup:
        - ui-index with 5 executable candidates, no execution indices
        - stale row: batchExecutable=true, batchEligibleCount=5

        Action:
        - Write 3 execution artifacts (partial execution)
        - Force external-analysis mtime > ui-index mtime

        Expected:
        - executionSummary.executedCandidates == 3
        - executionSummary.pendingExecutableCandidates == 2
        - executionSummary.batchExecutionState == "partially-executed"
        - batchExecutable is True (2 remaining eligible)
        - batchEligibleCount == 2
        - timings include index_stale_execution_indices=True
        - timings include index_execution_indices_recomputed=True
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact with 5 executable candidates
        plan = _make_plan_artifact("test-run", 5)
        (ea_dir / "test-run-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create ui-index.json with stale execution state
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
                "_plan_data": {"test-run": plan},
                "_execution_indices": {},  # Empty - stale state
            },
        }
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set ui-index.json mtime to old
        old_time = 1000000000.0
        os.utime(ui_index_path, (old_time, old_time))

        # First call - should return stale state
        runs_dir = tmp_path
        payload1, timings1 = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        payload1 = cast(dict[str, object], payload1)
        runs1 = _payload_runs(payload1)
        assert len(runs1) == 1

        # Verify stale state
        assert runs1[0]["batchExecutable"] is True
        assert runs1[0]["batchEligibleCount"] == 5
        summary1 = _execution_summary(runs1[0])
        assert summary1 is not None
        assert summary1["executedCandidates"] == 0
        assert summary1["pendingExecutableCandidates"] == 5
        assert summary1["batchExecutionState"] == "not-started"

        # Write execution artifacts for only 3 of 5 candidates (partial execution)
        time_module.sleep(0.01)
        for i in range(3):
            exec_artifact = _make_execution_artifact("test-run", i, "success")
            (ea_dir / f"test-run-next-check-execution-{i}.json").write_text(
                json.dumps(exec_artifact), encoding="utf-8"
            )

        # Force external-analysis mtime > ui-index mtime
        time_module.sleep(0.01)
        new_time = 1000000100.0
        os.utime(ea_dir, (new_time, new_time))

        # Verify external-analysis is indeed newer
        assert ea_dir.stat().st_mtime > ui_index_path.stat().st_mtime

        # Second call - must return fresh execution state
        payload2, timings2 = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        payload2 = cast(dict[str, object], payload2)
        runs2 = _payload_runs(payload2)
        assert len(runs2) == 1

        # Verify fresh state after partial execution
        summary2 = _execution_summary(runs2[0])
        assert summary2 is not None
        assert summary2["executedCandidates"] == 3, (
            f"Expected 3 executed, got {summary2['executedCandidates']}"
        )
        assert summary2["pendingExecutableCandidates"] == 2, (
            f"Expected 2 pending, got {summary2['pendingExecutableCandidates']}"
        )
        assert summary2["batchExecutionState"] == "partially-executed", (
            f"Expected partially-executed, got {summary2['batchExecutionState']}"
        )
        assert runs2[0]["batchExecutable"] is True, (
            "batchExecutable should be True (2 remaining eligible)"
        )
        assert runs2[0]["batchEligibleCount"] == 2, (
            f"batchEligibleCount should be 2, got {runs2[0]['batchEligibleCount']}"
        )

        # Verify timing flags
        assert timings2.get("index_stale_execution_indices") is True, (
            "index_stale_execution_indices should be True"
        )
        assert timings2.get("index_execution_indices_recomputed") is True, (
            "index_execution_indices_recomputed should be True"
        )

    def test_stale_index_with_failed_executions(self, tmp_path: Path) -> None:
        """After 3 of 5 candidates fail, execution state must reflect failures.

        Setup:
        - ui-index with 5 executable candidates, no execution indices
        - stale row: batchExecutable=true, batchEligibleCount=5

        Action:
        - Write 3 execution artifacts with status="failed"
        - Force external-analysis mtime > ui-index mtime

        Expected:
        - executionSummary.executedCandidates == 3
        - executionSummary.failedCandidates == 3
        - executionSummary.pendingExecutableCandidates == 2
        - executionSummary.batchExecutionState == "partially-executed"
        - batchExecutable is True (2 remaining eligible)
        - batchEligibleCount == 2
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact with 5 executable candidates
        plan = _make_plan_artifact("test-run", 5)
        (ea_dir / "test-run-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create ui-index.json with stale execution state
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,
                "_plan_data": {"test-run": plan},
                "_execution_indices": {},  # Empty - stale state
            },
        }
        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set ui-index.json mtime to old
        old_time = 1000000000.0
        os.utime(ui_index_path, (old_time, old_time))

        # Write execution artifacts for 3 candidates with "failed" status
        time_module.sleep(0.01)
        for i in range(3):
            exec_artifact = _make_execution_artifact("test-run", i, "failed")
            (ea_dir / f"test-run-next-check-execution-{i}.json").write_text(
                json.dumps(exec_artifact), encoding="utf-8"
            )

        # Force external-analysis mtime > ui-index mtime
        time_module.sleep(0.01)
        new_time = 1000000100.0
        os.utime(ea_dir, (new_time, new_time))

        # Call - must return fresh execution state with failed count
        runs_dir = tmp_path
        payload, timings = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        payload = cast(dict[str, object], payload)
        runs = _payload_runs(payload)
        assert len(runs) == 1

        # Verify fresh state with failures
        summary = _execution_summary(runs[0])
        assert summary is not None
        assert summary["executedCandidates"] == 3, (
            f"Expected 3 executed, got {summary['executedCandidates']}"
        )
        assert summary["failedCandidates"] == 3, (
            f"Expected 3 failed, got {summary['failedCandidates']}"
        )
        assert summary["pendingExecutableCandidates"] == 2, (
            f"Expected 2 pending, got {summary['pendingExecutableCandidates']}"
        )
        assert summary["batchExecutionState"] == "partially-executed", (
            f"Expected partially-executed, got {summary['batchExecutionState']}"
        )
        assert runs[0]["batchExecutable"] is True, (
            "batchExecutable should be True (2 remaining eligible)"
        )
        assert runs[0]["batchEligibleCount"] == 2, (
            f"batchEligibleCount should be 2, got {runs[0]['batchEligibleCount']}"
        )

        # Verify timing flags
        assert timings.get("index_stale_execution_indices") is True
        assert timings.get("index_execution_indices_recomputed") is True