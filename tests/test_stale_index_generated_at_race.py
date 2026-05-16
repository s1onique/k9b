"""Regression test for stale index freshness race condition (T0 < T1 < T2).

This test verifies that when execution artifacts are written AFTER the index
snapshot was taken (generated_at), the API correctly detects stale execution
indices even when the ui-index.json file mtime is newer than the artifacts.

The race condition:
- T0: ui-index snapshot taken (generated_at), _execution_indices is empty
- T1: Execution artifacts written (execution artifacts are NEWER than generated_at)
- T2: ui-index.json file write completes (file mtime is NEWER than execution artifacts)

The bug was that the API compared external-analysis dir mtime against ui-index.json
file mtime. This fails when T0 < T1 < T2 because file mtime (T2) > execution mtime (T1),
falsely indicating the index is fresh.

The fix compares execution artifact mtimes against generated_at (T0):
- If any execution artifact mtime > generated_at, the index is stale

Regression test for: Recent Runs execution summary lags behind Work list
"""

from __future__ import annotations

import json
import os
import time as time_module
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import build_runs_list
from k8s_diag_agent.ui.api_payloads import RunsListPayload


def _payload_runs(payload: RunsListPayload) -> list[dict[str, object]]:
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


class TestStaleIndexGeneratedAtRace:
    """Regression tests for generated_at vs file mtime race condition.

    The exact race from the bug report:
    - ui-index.generated_at = T0 (index snapshot time, before executions)
    - execution artifacts = T1 (executions happened after T0)
    - ui-index.json file mtime = T2 (file written after T1)

    T0 < T1 < T2 means file mtime falsely indicates freshness.
    """

    def test_generated_at_stale_despite_newer_file_mtime(self, tmp_path: Path) -> None:
        """Regression: API must detect stale index even when ui-index.json mtime is newer.

        This is the exact scenario from the bug report:
        - generated_at = T0 (before executions)
        - execution artifacts mtime = T1 (after T0, but before file write completes)
        - ui-index.json file mtime = T2 (after T1)

        The API must use generated_at as the source of truth, NOT file mtime.

        Setup:
        - ui-index with generated_at = T0, _execution_indices = {}
        - 9 execution artifacts written at T1 (T1 > T0)
        - ui-index.json file mtime set to T2 (T2 > T1 > T0)

        Expected:
        - index_stale_by_generated_at = True
        - executionSummary.executedCandidates == 9
        - executionSummary.failedCandidates == 1
        - executionSummary.batchExecutionState == "fully-executed"
        - batchExecutable == False
        - batchEligibleCount == 0
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact with 9 executable candidates + 1 ineligible
        # Total 10 candidates, but 9 are executable
        plan = _make_plan_artifact("health-run-20260516T035713Z", 9)
        (ea_dir / "health-run-20260516T035713Z-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Set timestamps for the race condition:
        # T0 = 1000000000.0 (generated_at time - index snapshot)
        # Execution artifacts will be at T1 = 1000000100.0
        # ui-index.json file will be at T2 = 1000000200.0
        T0 = 1000000000.0  # generated_at (before executions)
        T1 = 1000000100.0  # execution artifacts (after T0)
        T2 = 1000000200.0  # ui-index.json file mtime (after T1)

        # Create ui-index.json with T0 as generated_at and EMPTY execution indices
        # This simulates the state where index was snapshotted BEFORE batch execution
        ui_index = {
            "run": {"run_id": "health-run-20260516T035713Z", "run_label": "Test Run"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "health-run-20260516T035713Z",
                        "run_label": "Test Run",
                        "timestamp": "2026-05-16T03:57:13Z",
                        "cluster_count": 3,
                        "batchEligibility": "computed",
                        "batchExecutable": True,  # Stale: shows executable
                        "batchEligibleCount": 9,  # Stale: shows 9 eligible
                    }
                ],
                "total_count": 1,
                "version": 3,
                "generated_at": datetime.fromtimestamp(T0, tz=UTC).isoformat(),
                "_plan_data": {"health-run-20260516T035713Z": plan},
                "_execution_indices": {},  # CRITICAL: Empty - simulates pre-execution state
            },
        }

        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set ui-index.json file mtime to T2 (NEWEST)
        # This is the key: file mtime is newer than execution artifacts
        os.utime(ui_index_path, (T2, T2))

        # Verify: file mtime (T2) > execution artifact mtime (T1) should NOT make it fresh
        # This is the BUG condition we're testing against
        assert ui_index_path.stat().st_mtime == T2, "ui-index.json mtime should be T2"

        # First, write execution artifacts for all 9 candidates at T1
        # This is AFTER T0 (generated_at) but BEFORE T2 (file mtime)
        statuses = ["success", "success", "success", "success", "failed", "success", "success", "success", "success"]

        for i, status in enumerate(statuses):
            exec_artifact = _make_execution_artifact("health-run-20260516T035713Z", i, status)
            exec_path = ea_dir / f"health-run-20260516T035713Z-next-check-execution-{i}.json"
            exec_path.write_text(json.dumps(exec_artifact), encoding="utf-8")
            # Set execution artifact mtime to T1
            os.utime(exec_path, (T1, T1))

        # Verify execution artifacts are at T1
        exec_files = list(ea_dir.glob("*-next-check-execution*.json"))
        assert len(exec_files) == 9
        newest_exec_mtime = max(f.stat().st_mtime for f in exec_files)
        assert newest_exec_mtime == T1, f"Execution artifacts mtime should be T1, got {newest_exec_mtime}"

        # Verify the race condition: T0 < T1 < T2
        assert T0 < T1 < T2, f"Race condition not set up correctly: {T0} < {T1} < {T2}"
        # Verify: generated_at (T0) < execution artifact mtime (T1)
        generated_at_ts = datetime.fromtimestamp(T0, tz=UTC).timestamp()
        assert newest_exec_mtime > generated_at_ts, (
            f"Execution artifacts ({newest_exec_mtime}) should be newer than generated_at ({generated_at_ts})"
        )
        # Verify: execution artifact mtime (T1) < file mtime (T2)
        assert ui_index_path.stat().st_mtime > newest_exec_mtime, (
            f"File mtime ({ui_index_path.stat().st_mtime}) should be newer than execution mtime ({newest_exec_mtime})"
        )

        # Call API - this should detect the staleness via generated_at comparison
        runs_dir = tmp_path
        payload, timings = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        runs = _payload_runs(payload)
        assert len(runs) == 1, f"Expected 1 run, got {len(runs)}"

        run = runs[0]

        # CRITICAL: Verify that the API correctly detected staleness via generated_at
        assert timings.get("index_stale_by_generated_at") is True, (
            f"Expected index_stale_by_generated_at=True, got {timings.get('index_stale_by_generated_at')}"
        )

        # Verify timing flags
        assert timings.get("index_stale_execution_indices") is True, (
            "index_stale_execution_indices should be True"
        )
        assert timings.get("index_execution_indices_recomputed") is True, (
            "index_execution_indices_recomputed should be True"
        )

        # Verify execution summary reflects the fresh execution state
        summary = _execution_summary(run)
        assert summary is not None, "executionSummary should not be None"

        # All 9 executable candidates were executed
        assert summary["executedCandidates"] == 9, (
            f"Expected 9 executed, got {summary['executedCandidates']}"
        )
        assert summary["pendingExecutableCandidates"] == 0, (
            f"Expected 0 pending, got {summary['pendingExecutableCandidates']}"
        )
        assert summary["failedCandidates"] == 1, (
            f"Expected 1 failed, got {summary['failedCandidates']}"
        )
        assert summary["batchExecutionState"] == "fully-executed", (
            f"Expected fully-executed, got {summary['batchExecutionState']}"
        )

        # Batch eligibility should be recomputed based on fresh data
        assert run["batchExecutable"] is False, (
            "batchExecutable should be False after all executed"
        )
        assert run["batchEligibleCount"] == 0, (
            f"batchEligibleCount should be 0, got {run['batchEligibleCount']}"
        )

    def test_fresh_when_no_executions_after_generated_at(self, tmp_path: Path) -> None:
        """When no execution artifacts exist after generated_at, index should be fresh.

        This is the normal case where the index is up-to-date.
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact with 5 candidates
        plan = _make_plan_artifact("test-run", 5)
        (ea_dir / "test-run-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create ui-index with generated_at = now, empty execution indices
        # (no executions have happened yet)
        now_ts = datetime.now(UTC).timestamp()
        generated_at = datetime.fromtimestamp(now_ts, tz=UTC).isoformat()

        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-05-16T03:57:13Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 3,
                "generated_at": generated_at,
                "_plan_data": {"test-run": plan},
                "_execution_indices": {},  # Empty - no executions yet
            },
        }

        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Call API
        runs_dir = tmp_path
        payload, timings = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        runs = _payload_runs(payload)
        assert len(runs) == 1

        # Since no execution artifacts exist after generated_at, index should be fresh
        assert timings.get("index_stale_by_generated_at") is not True, (
            "Index should be fresh when no executions after generated_at"
        )

        # Verify stale flags are NOT set
        assert timings.get("index_stale_execution_indices") is not True
        assert timings.get("index_execution_indices_recomputed") is not True

        run = runs[0]
        summary = _execution_summary(run)

        # No executions have happened
        assert summary["executedCandidates"] == 0, (
            f"Expected 0 executed, got {summary['executedCandidates']}"
        )
        assert summary["pendingExecutableCandidates"] == 5, (
            f"Expected 5 pending, got {summary['pendingExecutableCandidates']}"
        )
        assert summary["batchExecutionState"] == "not-started", (
            f"Expected not-started, got {summary['batchExecutionState']}"
        )

    def test_generated_at_missing_falls_back_to_dir_mtime(self, tmp_path: Path) -> None:
        """When generated_at is missing/invalid, fallback to directory mtime comparison.

        This tests the fallback heuristic for backward compatibility.
        """
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan artifact
        plan = _make_plan_artifact("test-run", 5)
        (ea_dir / "test-run-next-check-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )

        # Create ui-index WITHOUT generated_at (or with invalid value)
        ui_index = {
            "run": {"run_id": "test-run", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "test-run",
                        "run_label": "Test",
                        "timestamp": "2026-05-16T03:57:13Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 3,
                # No generated_at field - triggers fallback
                "_plan_data": {"test-run": plan},
                "_execution_indices": {},
            },
        }

        ui_index_path = health_dir / "ui-index.json"
        ui_index_path.write_text(json.dumps(ui_index), encoding="utf-8")

        # Set file mtime to old
        old_time = 1000000000.0
        os.utime(ui_index_path, (old_time, old_time))

        # Write execution artifacts
        time_module.sleep(0.01)
        for i in range(5):
            exec_artifact = _make_execution_artifact("test-run", i, "success")
            (ea_dir / f"test-run-next-check-execution-{i}.json").write_text(
                json.dumps(exec_artifact), encoding="utf-8"
            )

        # Set external-analysis dir mtime to newer
        time_module.sleep(0.01)
        new_time = 1000000100.0
        os.utime(ea_dir, (new_time, new_time))

        # Call API
        runs_dir = tmp_path
        payload, timings = build_runs_list(
            runs_dir,
            include_batch_eligibility=True,
            _timings=True,
        )
        runs = _payload_runs(payload)
        assert len(runs) == 1

        # When generated_at is missing, fallback to external-analysis mtime comparison
        # Since external_analysis mtime > ui_index mtime, it should be stale
        assert timings.get("index_stale_execution_indices") is True, (
            "Should use fallback heuristic when generated_at is missing"
        )
        assert timings.get("index_execution_indices_recomputed") is True, (
            "Execution indices should be recomputed"
        )

        # Verify execution summary is correct
        summary = _execution_summary(runs[0])
        assert summary["executedCandidates"] == 5
        assert summary["pendingExecutableCandidates"] == 0
        assert summary["batchExecutionState"] == "fully-executed"