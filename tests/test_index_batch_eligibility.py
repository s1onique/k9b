"""Tests for index-backed batch eligibility in build_runs_list().

These tests verify the key contract:
- When ui-index.json has recent_runs_summary with version>=2 and batch eligibility fields,
  /api/runs?include_batch_eligibility=true must use the index without scanning files.
- The path_strategy should be "index_recent_runs_with_batch_eligibility"
- batch_plan_glob_ms and batch_exec_glob_ms should be 0
- Fallback to scan path when index is missing/incomplete/stale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import build_runs_list
from k8s_diag_agent.ui.api_payloads import RunsListPayload


def _summary_runs(summary: dict[str, object]) -> list[dict[str, object]]:
    runs = summary.get("runs")
    assert isinstance(runs, list)
    assert all(isinstance(run, dict) for run in runs)
    return cast(list[dict[str, object]], runs)


class TestIndexBatchEligibility:
    """Tests for index-backed batch eligibility path."""

    def test_index_path_with_batch_eligibility_uses_index(self, tmp_path: Path) -> None:
        """When index has batch eligibility (version>=2), should use index without scanning."""
        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create a review file
        (reviews_dir / "run-test-001-review.json").write_text(
            json.dumps(
                {
                    "run_id": "run-test-001",
                    "run_label": "Test Run 001",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create ui-index.json with batch eligibility (version 2)
        ui_index = {
            "run": {"run_id": "run-test-001", "run_label": "Test Run 001"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "run-test-001",
                        "run_label": "Test Run 001",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    }
                ],
                "total_count": 1,
                "version": 2,  # Version 2 includes batch eligibility
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Call build_runs_list with include_batch_eligibility=True
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Verify path strategy
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"

        # Verify no file scanning happened
        assert timings.get("batch_plan_glob_ms") == 0.0
        assert timings.get("batch_exec_glob_ms") == 0.0
        assert timings.get("reviews_parsed") == 0

        # Verify batch eligibility from index
        result = cast(RunsListPayload, result)
        assert len(result["runs"]) == 1
        run = result["runs"][0]
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        assert run["batchEligibleCount"] == 5

    def test_index_path_skips_plan_and_exec_glob(self, tmp_path: Path) -> None:
        """Index path should skip plan and exec glob entirely."""
        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create plan and exec files (should NOT be read)
        (ea_dir / "run-test-plan.json").write_text(json.dumps({"purpose": "next-check-planning", "candidates": []}), encoding="utf-8")
        (ea_dir / "run-test-exec.json").write_text(json.dumps({"purpose": "next-check-execution", "payload": {}}), encoding="utf-8")

        # Create ui-index.json with batch eligibility
        ui_index = {
            "run": {"run_id": "run-test", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "run-test",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 3,
                    }
                ],
                "total_count": 1,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Call build_runs_list with include_batch_eligibility=True
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Verify path strategy
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"

        # Verify no plan/exec scanning
        assert timings.get("batch_plan_files_found") == 0
        assert timings.get("batch_exec_files_found") == 0
        assert timings.get("batch_plan_glob_ms") == 0.0
        assert timings.get("batch_exec_glob_ms") == 0.0

    def test_fallback_when_index_version_1(self, tmp_path: Path) -> None:
        """Should fall back to scan path when index version is < 2."""
        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create a review file
        (reviews_dir / "run-test-review.json").write_text(
            json.dumps(
                {
                    "run_id": "run-test",
                    "run_label": "Test",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create ui-index.json WITHOUT batch eligibility (version 1)
        ui_index = {
            "run": {"run_id": "run-test", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "run-test",
                        "run_label": "Test",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        # No batchEligibility, batchExecutable, batchEligibleCount
                    }
                ],
                "total_count": 1,
                "version": 1,  # Version 1 lacks batch eligibility
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Call build_runs_list with include_batch_eligibility=True
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Should fall through to scan path (version 1 check failed)
        # The scan path will scan review files
        assert timings.get("reviews_parsed", 0) > 0 or timings.get("path_strategy") in (
            "index_super_fast_path",  # May still use index but for super fast path
            "review_streaming_super_fast_path",
        )

    def test_fallback_when_index_absent(self, tmp_path: Path) -> None:
        """Should fall back to scan path when ui-index.json is absent."""
        # Create health directory structure WITHOUT ui-index.json
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create a review file
        (reviews_dir / "run-test-review.json").write_text(
            json.dumps(
                {
                    "run_id": "run-test",
                    "run_label": "Test",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Call build_runs_list with include_batch_eligibility=True
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Should fall through to scan path
        assert timings.get("reviews_parsed", 0) > 0

    def test_batch_eligibility_runs_computed_timing(self, tmp_path: Path) -> None:
        """Index path should correctly report batch_eligibility_runs_computed."""
        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create multiple review files
        for i in range(3):
            (reviews_dir / f"run-test-{i:03d}-review.json").write_text(
                json.dumps(
                    {
                        "run_id": f"run-test-{i:03d}",
                        "run_label": f"Test Run {i}",
                        "timestamp": f"2026-04-30T{12 + i:02d}:00:00Z",
                        "cluster_count": 2,
                    }
                ),
                encoding="utf-8",
            )

        # Create ui-index.json with batch eligibility for all runs
        ui_index = {
            "run": {"run_id": "run-test-002", "run_label": "Test Run 002"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "run-test-002",
                        "run_label": "Test Run 002",
                        "timestamp": "2026-04-30T14:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 3,
                    },
                    {
                        "run_id": "run-test-001",
                        "run_label": "Test Run 001",
                        "timestamp": "2026-04-30T13:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": False,
                        "batchEligibleCount": 0,
                    },
                    {
                        "run_id": "run-test-000",
                        "run_label": "Test Run 000",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 7,
                    },
                ],
                "total_count": 3,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Call build_runs_list with include_batch_eligibility=True and limit=2
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, limit=2, _timings=True)

        # Verify path strategy
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"

        # Verify batch eligibility timing
        assert timings.get("batch_eligibility_runs_computed") == 2  # Limited to 2
        assert timings.get("batch_eligible_runs") == 1  # Only run-test-002 is executable

        # Verify result
        result = cast(RunsListPayload, result)
        assert len(result["runs"]) == 2
        assert result["runs"][0]["batchExecutable"] is True
        assert result["runs"][1]["batchExecutable"] is False

    def test_index_batch_eligibility_with_unknown_runs(self, tmp_path: Path) -> None:
        """Index path should handle runs with batchEligibility='unknown'."""
        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        # Create ui-index.json with mixed batch eligibility
        ui_index = {
            "run": {"run_id": "run-test", "run_label": "Test"},
            "recent_runs_summary": {
                "runs": [
                    {
                        "run_id": "run-test-known",
                        "run_label": "Known",
                        "timestamp": "2026-04-30T12:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "computed",
                        "batchExecutable": True,
                        "batchEligibleCount": 5,
                    },
                    {
                        "run_id": "run-test-unknown",
                        "run_label": "Unknown",
                        "timestamp": "2026-04-30T11:00:00Z",
                        "cluster_count": 2,
                        "batchEligibility": "unknown",  # No plan for this run
                        "batchExecutable": False,
                        "batchEligibleCount": 0,
                    },
                ],
                "total_count": 2,
                "version": 2,
            },
        }
        (health_dir / "ui-index.json").write_text(json.dumps(ui_index), encoding="utf-8")

        # Call build_runs_list with include_batch_eligibility=True
        result, timings = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)

        # Verify path strategy
        assert timings.get("path_strategy") == "index_recent_runs_with_batch_eligibility"

        # Verify mixed results
        result = cast(RunsListPayload, result)
        assert len(result["runs"]) == 2

        # First run has computed eligibility
        assert result["runs"][0]["runId"] == "run-test-known"
        assert result["runs"][0]["batchEligibility"] == "computed"
        assert result["runs"][0]["batchExecutable"] is True

        # Second run has unknown eligibility
        assert result["runs"][1]["runId"] == "run-test-unknown"
        assert result["runs"][1]["batchEligibility"] == "unknown"
        assert result["runs"][1]["batchExecutable"] is False


class TestBuildRecentRunsSummaryWithExternalAnalysis:
    """Tests for _build_recent_runs_summary with batch eligibility computation."""

    def test_build_recent_runs_summary_computes_batch_eligibility(self, tmp_path: Path) -> None:
        """_build_recent_runs_summary should compute batch eligibility when external-analysis exists."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        # Create a review file
        run_id = "health-run-20260430T120000Z"
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create a plan file with eligible candidates
        plan = {
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check pod status",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check node status",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Call _build_recent_runs_summary with external_analysis_dir
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify summary structure
        assert summary["version"] == 3
        assert "_execution_index_diagnostics" in summary
        diagnostics = cast(dict[str, object], summary["_execution_index_diagnostics"])
        assert diagnostics["_execution_index_collector_version"] == "shared-one-pass-v1"
        runs = _summary_runs(summary)
        assert len(runs) == 1

        # Verify batch eligibility was computed
        run = runs[0]
        assert run["run_id"] == run_id
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        assert run["batchEligibleCount"] == 2

    def test_build_recent_runs_summary_respects_execution_indices(self, tmp_path: Path) -> None:
        """_build_recent_runs_summary should subtract already-executed candidates."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260430T120000Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create a plan file with 3 candidates
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
                },
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 2",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 3",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create an execution artifact for candidate index 1
        execution = {
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 1},
        }
        (ea_dir / f"{run_id}-next-check-execution.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify batch eligibility was computed with execution subtracted
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        assert run["batchEligibleCount"] == 2  # 3 total - 1 executed = 2

    def test_build_recent_runs_summary_without_external_analysis(self, tmp_path: Path) -> None:
        """_build_recent_runs_summary should work without external-analysis directory."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure WITHOUT external-analysis
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)

        run_id = "health-run-20260430T120000Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Call _build_recent_runs_summary without external_analysis_dir
        summary = _build_recent_runs_summary(reviews_dir)

        # Verify summary structure - version 3 even without external-analysis (schema is consistent)
        assert summary["version"] == 3
        runs = _summary_runs(summary)
        assert len(runs) == 1

        # Verify batch eligibility is unknown (no plan to compute from)
        run = runs[0]
        assert run["run_id"] == run_id
        assert run["batchEligibility"] == "unknown"
        assert run["batchExecutable"] is False
        assert run["batchEligibleCount"] == 0


class TestExtractRunIdsFromFilename:
    """Tests for _extract_run_ids_from_filename with numbered artifacts."""

    def test_extract_run_ids_handles_numbered_artifact(self, tmp_path: Path) -> None:
        """Should correctly extract run_id from numbered plan artifacts like health-run-20260430T120000Z-next-check-plan-001.json."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260430T120000Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create a NUMBERED plan file (the bug scenario: plan-001 instead of just plan)
        plan = {
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check pod status",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
            ],
        }
        # This is the key test: numbered plan artifact like health-run-20260430T120000Z-next-check-plan-001.json
        (ea_dir / f"{run_id}-next-check-plan-001.json").write_text(json.dumps(plan), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify batch eligibility was computed despite numbered artifact
        assert summary["version"] == 3
        runs = _summary_runs(summary)
        assert len(runs) == 1
        run = runs[0]
        assert run["run_id"] == run_id
        # Should detect the plan despite the -001 suffix
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        assert run["batchEligibleCount"] == 1


class TestNonContiguousCandidateIndex:
    """Tests for _compute_batch_eligibility_indexed with non-contiguous candidateIndex."""

    def test_compute_eligibility_uses_candidate_index_not_enumerate(self, tmp_path: Path) -> None:
        """Should use candidateIndex from plan artifact, not enumerate index."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260430T120000Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create plan with non-contiguous candidateIndex values
        # Candidates are enumerated 0, 1, 2 but have explicit candidateIndex 10, 20, 30
        plan = {
            "purpose": "next-check-planning",
            "candidates": [
                {
                    "candidateIndex": 10,  # Non-contiguous index
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 1",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
                {
                    "candidateIndex": 20,  # Non-contiguous index
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 2",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
                {
                    "candidateIndex": 30,  # Non-contiguous index
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 3",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create execution artifact for candidateIndex=20 (the SECOND candidate by enumerate, but index 20)
        execution = {
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 20},
        }
        (ea_dir / f"{run_id}-next-check-execution.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify batch eligibility was computed with execution subtracted
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        # Only 2 eligible (candidates at indices 10 and 30 remain, 20 was executed)
        assert run["batchEligibleCount"] == 2

    def test_compute_eligibility_falls_back_to_enumerate_when_no_candidate_index(self, tmp_path: Path) -> None:
        """Should fall back to enumerate index when candidateIndex is absent."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260430T120000Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-04-30T12:00:00Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create plan WITHOUT candidateIndex (backward compatibility case)
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
                },
                {
                    "suggestedCommandFamily": "kubectl",
                    "description": "Check 2",
                    "targetContext": "default/cluster-a",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "duplicateOfExistingEvidence": False,
                },
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create execution artifact for index 0 (first candidate by enumerate)
        execution = {
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 0},
        }
        (ea_dir / f"{run_id}-next-check-execution.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify batch eligibility was computed with execution subtracted
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        # Only 1 eligible (first candidate was executed by enumerate index 0)
        assert run["batchEligibleCount"] == 1


class TestExecutionArtifactRunIdExtraction:
    """Tests for correct execution artifact run_id extraction.

    This addresses the bug where execution artifacts like
    health-run-20260515T200439Z-next-check-execution-0.json were incorrectly
    parsed because the marker "-next-check-execution" matched INSIDE the run_id
    rather than as the artifact suffix delimiter.
    """

    def test_execution_artifact_with_numbered_suffix(self, tmp_path: Path) -> None:
        """Should correctly extract run_id from numbered execution artifacts.

        The bug: filename "health-run-20260515T200439Z-next-check-execution-0.json"
        contains "-next-check-" INSIDE the run_id, so using marker "-next-check-execution"
        would match the marker at position 27 (inside run_id) rather than position 35.

        The fix: Use marker "-next-check-execution-" (with trailing dash) or extract
        run_id from the artifact's run_id field.
        """
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "health-run-20260515T200439Z"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-05-15T20:04:39Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create plan with 11 candidates
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
                for i in range(11)
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create 8 execution artifacts with numbered suffixes (indices 0-7)
        # 2 failed, 6 success
        execution_statuses = {
            0: "success",
            1: "success",
            2: "failed",
            3: "success",
            4: "failed",
            5: "success",
            6: "success",
            7: "success",
        }
        for idx, status in execution_statuses.items():
            execution = {
                "purpose": "next-check-execution",
                "run_id": run_id,  # Artifact has run_id field
                "status": status,
                "payload": {"candidateIndex": idx},
            }
            # Filename pattern: health-run-20260515T200439Z-next-check-execution-{idx}.json
            (ea_dir / f"{run_id}-next-check-execution-{idx}.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify execution indices were correctly stored
        execution_indices_obj = summary.get("_execution_indices", {})
        assert isinstance(execution_indices_obj, dict)
        execution_indices = cast(dict[str, dict[int, str]], execution_indices_obj)
        assert run_id in execution_indices, f"run_id {run_id} should be in execution_indices"

        # Verify we got 8 parsed execution indices
        run_exec_indices = execution_indices[run_id]
        assert len(run_exec_indices) == 8, f"Expected 8 execution indices, got {len(run_exec_indices)}"

        # Verify status extraction
        assert run_exec_indices.get(0) == "success", f"Index 0 should be success, got {run_exec_indices.get(0)}"
        assert run_exec_indices.get(2) == "failed", f"Index 2 should be failed, got {run_exec_indices.get(2)}"
        assert run_exec_indices.get(4) == "failed", f"Index 4 should be failed, got {run_exec_indices.get(4)}"

        # Verify batch eligibility was computed correctly
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibility"] == "computed"
        assert run["batchExecutable"] is True
        # 11 total - 8 executed = 3 pending
        assert run["batchEligibleCount"] == 3, f"Expected 3 eligible, got {run['batchEligibleCount']}"

    def test_execution_artifact_run_id_from_artifact_field(self, tmp_path: Path) -> None:
        """Should prefer run_id from artifact's run_id field over filename parsing."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        run_id = "test-run-with-hyphens"

        # Create a review file
        (reviews_dir / f"{run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-05-15T20:04:39Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create plan with 3 candidates
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
                for i in range(3)
            ],
        }
        (ea_dir / f"{run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create execution artifact with DIFFERENT run_id in filename vs artifact field
        # The filename has run_id but artifact field says something else
        execution = {
            "purpose": "next-check-execution",
            "run_id": run_id,  # Primary: from artifact field
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        # Filename contains run_id with the marker inside
        (ea_dir / f"{run_id}-next-check-execution-0.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify execution indices were correctly stored
        execution_indices_obj = summary.get("_execution_indices", {})
        assert isinstance(execution_indices_obj, dict)
        execution_indices = cast(dict[str, dict[int, str]], execution_indices_obj)
        assert run_id in execution_indices, f"run_id {run_id} should be in execution_indices"

        # Verify we got 1 parsed execution index
        run_exec_indices = execution_indices[run_id]
        assert len(run_exec_indices) == 1, f"Expected 1 execution index, got {len(run_exec_indices)}"
        assert run_exec_indices.get(0) == "success"

        # Verify batch eligibility: 3 - 1 = 2 remaining
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibleCount"] == 2

    def test_execution_artifact_filename_vs_run_id_field_priority(self, tmp_path: Path) -> None:
        """Should use artifact run_id field as primary, filename as fallback."""
        from k8s_diag_agent.health.ui import _build_recent_runs_summary

        # Create health directory structure
        health_dir = tmp_path / "health"
        health_dir.mkdir(parents=True)
        reviews_dir = health_dir / "reviews"
        reviews_dir.mkdir(parents=True)
        ea_dir = health_dir / "external-analysis"
        ea_dir.mkdir(parents=True)

        artifact_run_id = "actual-run-id-in-artifact"
        filename_run_id = "health-run-timestamp"

        # Create review for the actual run_id from artifact
        (reviews_dir / f"{artifact_run_id}-review.json").write_text(
            json.dumps(
                {
                    "run_id": artifact_run_id,
                    "run_label": "Test Run",
                    "timestamp": "2026-05-15T20:04:39Z",
                    "cluster_count": 2,
                }
            ),
            encoding="utf-8",
        )

        # Create plan for the actual run_id
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
                },
            ],
        }
        (ea_dir / f"{artifact_run_id}-next-check-plan.json").write_text(json.dumps(plan), encoding="utf-8")

        # Create execution artifact with run_id in both filename and artifact field
        # Artifact field takes priority
        execution = {
            "purpose": "next-check-execution",
            "run_id": artifact_run_id,  # This should be used
            "status": "success",
            "payload": {"candidateIndex": 0},
        }
        # Filename has a different run_id than the artifact field
        (ea_dir / f"{filename_run_id}-next-check-execution-0.json").write_text(json.dumps(execution), encoding="utf-8")

        # Call _build_recent_runs_summary
        summary = _build_recent_runs_summary(
            reviews_dir,
            external_analysis_dir=ea_dir,
        )

        # Verify execution indices were stored under the actual run_id from artifact
        execution_indices_obj = summary.get("_execution_indices", {})
        assert isinstance(execution_indices_obj, dict)
        execution_indices = cast(dict[str, dict[int, str]], execution_indices_obj)

        # Should be stored under artifact_run_id, NOT filename_run_id
        assert artifact_run_id in execution_indices, f"artifact_run_id {artifact_run_id} should be in execution_indices"
        assert filename_run_id not in execution_indices, f"filename_run_id {filename_run_id} should NOT be in execution_indices"

        # Verify batch eligibility: 1 - 1 = 0 remaining
        runs = _summary_runs(summary)
        run = runs[0]
        assert run["batchEligibleCount"] == 0
