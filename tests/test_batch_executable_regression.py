"""Regression test: /api/runs must return batchExecutable=true for runs with eligible candidates.

This test verifies that the Recent Runs Execute button works correctly by ensuring
the backend computes batchExecutable=true when:
1. A next-check plan exists with eligible candidates (safeToAutomate=true, etc.)
2. include_batch_eligibility=true is passed to /api/runs

This was previously broken because:
- Frontend fetchRunsList() called /api/runs WITHOUT include_batch_eligibility=true
- Backend only computes batch eligibility when include_status=True or include_expensive=True
- Without this flag, batchExecutable was always False

Fix: fetchRunsList() now passes include_batch_eligibility=true so the backend computes
batch eligibility for runs in the visible window WITHOUT triggering execution count derivation.
This is the optimized path that avoids the slow execution count derivation observed on large artifact directories.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from k8s_diag_agent.ui.api import build_runs_list


class TestBatchExecutableRegression:
    """Regression test for batchExecutable computation in /api/runs."""

    def test_batch_executable_true_for_run_with_eligible_candidates(self, tmp_path: Path) -> None:
        """Verify runs with eligible external-analysis plan candidates get batchExecutable=true."""
        # Arrange: Create health/external-analysis directory with a plan containing eligible candidates
        # NOTE: build_runs_list() expects runs_dir/health/external-analysis/, NOT runs_dir/external-analysis/
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        # Create a plan artifact with 3 eligible candidates (safeToAutomate=true, etc.)
        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "kubectl logs -n ns1 pod-abc --previous",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    },
                    {
                        "candidateId": "c2",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "kubectl describe pod name-x -n ns2",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 1,
                    },
                    {
                        "candidateId": "c3",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-get",
                        "description": "kubectl get pods -n ns3",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 2,
                    },
                ]
            }
        }
        plan_path = ea_dir / "run-eligible-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create a review artifact (required for runs list discovery)
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-eligible-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "eligible-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-eligible-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act: Call build_runs_list with include_batch_eligibility=True (optimized path)
        # NOTE: The frontend now uses include_batch_eligibility=true which computes
        # batchExecutable without triggering the slow execution count derivation.
        # We test include_status=True here to verify batch eligibility still works.
        result = build_runs_list(tmp_path, include_batch_eligibility=True)
        result = cast(dict[str, object], result)

        # Assert: Find the run and verify batchExecutable is true
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_eligible = next((r for r in runs if r["runId"] == "run-eligible-001"), None)

        assert run_eligible is not None, "run-eligible-001 should be in runs list"
        assert run_eligible["batchExecutable"] is True, \
            f"batchExecutable should be True, got {run_eligible.get('batchExecutable')}"
        assert run_eligible["batchEligibleCount"] == 3, \
            f"batchEligibleCount should be 3, got {run_eligible.get('batchEligibleCount')}"
        assert run_eligible["batchEligibility"] == "computed", \
            f"batchEligibility should be 'computed', got {run_eligible.get('batchEligibility')}"

    def test_batch_executable_false_when_no_plan_exists(self, tmp_path: Path) -> None:
        """Verify runs without a next-check plan get batchExecutable=false."""
        # Arrange: Create only a review artifact (no plan)
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-no-plan-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "no-plan-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-no-plan-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act
        result = build_runs_list(tmp_path, include_status=True)
        result = cast(dict[str, object], result)

        # Assert
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_no_plan = next((r for r in runs if r["runId"] == "run-no-plan-001"), None)

        assert run_no_plan is not None, "run-no-plan-001 should be in runs list"
        assert run_no_plan["batchExecutable"] is False, \
            f"batchExecutable should be False when no plan exists, got {run_no_plan.get('batchExecutable')}"
        assert run_no_plan["batchEligibleCount"] == 0, \
            f"batchEligibleCount should be 0, got {run_no_plan.get('batchEligibleCount')}"

    def test_batch_executable_false_for_run_with_only_non_eligible_candidates(
        self, tmp_path: Path
    ) -> None:
        """Verify runs with candidates that don't meet eligibility criteria get batchExecutable=false."""
        # Arrange: Create plan with candidates that are NOT eligible
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": False,  # NOT eligible - unsafe
                        "suggestedCommandFamily": "kubectl-delete",
                        "description": "kubectl delete resource",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": True,  # Also needs approval
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    },
                    {
                        "candidateId": "c2",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "",  # NOT eligible - empty description
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 1,
                    },
                ]
            }
        }
        plan_path = ea_dir / "run-not-eligible-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create review
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-not-eligible-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "not-eligible-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-not-eligible-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act
        result = build_runs_list(tmp_path, include_status=True)
        result = cast(dict[str, object], result)

        # Assert
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_not_eligible = next((r for r in runs if r["runId"] == "run-not-eligible-001"), None)

        assert run_not_eligible is not None, "run-not-eligible-001 should be in runs list"
        assert run_not_eligible["batchExecutable"] is False, \
            f"batchExecutable should be False when no candidates eligible, got {run_not_eligible.get('batchExecutable')}"
        assert run_not_eligible["batchEligibleCount"] == 0

    def test_batch_executable_respects_already_executed_candidates(self, tmp_path: Path) -> None:
        """Verify already-executed candidates are not counted as eligible."""
        # Arrange: Create plan with 3 candidates, then execution artifact for candidate index 1
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "Candidate 1",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    },
                    {
                        "candidateId": "c2",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "Candidate 2",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 1,
                    },
                    {
                        "candidateId": "c3",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "Candidate 3",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 2,
                    },
                ]
            }
        }
        plan_path = ea_dir / "run-partially-executed-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create execution artifact for candidate index 1 (already executed)
        exec_data = {
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 1}
        }
        exec_path = ea_dir / "run-partially-executed-001-next-check-execution-001.json"
        exec_path.write_text(json.dumps(exec_data), encoding="utf-8")

        # Create review
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-partially-executed-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "partially-executed-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-partially-executed-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act
        result = build_runs_list(tmp_path, include_status=True)
        result = cast(dict[str, object], result)

        # Assert: 2 eligible candidates (c0 and c2 not executed, c1 is executed)
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_pe = next((r for r in runs if r["runId"] == "run-partially-executed-001"), None)

        assert run_pe is not None, "run-partially-executed-001 should be in runs list"
        assert run_pe["batchExecutable"] is True, \
            "batchExecutable should be True (2 candidates still eligible)"
        assert run_pe["batchEligibleCount"] == 2, \
            f"batchEligibleCount should be 2 (c0, c2), got {run_pe.get('batchEligibleCount')}"

    def test_batch_executable_false_without_include_status(self, tmp_path: Path) -> None:
        """Verify batchExecutable is False when include_status is not passed (super fast path)."""
        # This test documents the previous broken behavior that was fixed.
        # Without include_status=True, batch eligibility is NOT computed (deferred).

        # Arrange: Create plan with eligible candidates
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "Test candidate",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    }
                ]
            }
        }
        plan_path = ea_dir / "run-super-fast-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create review
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-super-fast-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "super-fast-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-super-fast-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act: Call WITHOUT include_status (super fast path - same as old fetchRunsList)
        result = build_runs_list(tmp_path, include_status=False)
        result = cast(dict[str, object], result)

        # Assert: batchEligibility should be "unknown" (deferred), batchExecutable should be False
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_sf = next((r for r in runs if r["runId"] == "run-super-fast-001"), None)

        assert run_sf is not None, "run-super-fast-001 should be in runs list"
        assert run_sf["batchEligibility"] == "unknown", \
            f"batchEligibility should be 'unknown' (deferred) without include_status, got {run_sf.get('batchEligibility')}"
        assert run_sf["batchExecutable"] is False, \
            "batchExecutable is False when eligibility is deferred"

    def test_include_batch_eligibility_flag_computes_eligibility_only(self, tmp_path: Path) -> None:
        """Verify include_batch_eligibility=True computes batch eligibility without full status.

        This is the new optimized path for initial UI load:
        - include_batch_eligibility=True: computes batchExecutable only (fast)
        - include_status=True: computes full execution/review counts (slower)

        The include_batch_eligibility flag should:
        - Compute batchExecutable for visible runs
        - NOT compute full execution/review counts
        - Return batchEligibility="computed" for runs with eligible candidates
        """
        # Arrange: Create plan with eligible candidates
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "kubectl logs test",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    }
                ]
            }
        }
        plan_path = ea_dir / "run-batch-eligible-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create review
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-batch-eligible-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "batch-eligible-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-batch-eligible-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Act: Call with include_batch_eligibility=True (NEW optimized path)
        result = build_runs_list(tmp_path, include_batch_eligibility=True)
        result = cast(dict[str, object], result)

        # Assert: batchEligibility should be "computed", batchExecutable should be True
        runs = cast(list[dict[str, object]], result.get("runs", []))
        run_be = next((r for r in runs if r["runId"] == "run-batch-eligible-001"), None)

        assert run_be is not None, "run-batch-eligible-001 should be in runs list"
        assert run_be["batchEligibility"] == "computed", \
            f"batchEligibility should be 'computed' with include_batch_eligibility=True, got {run_be.get('batchEligibility')}"
        assert run_be["batchExecutable"] is True, \
            f"batchExecutable should be True with include_batch_eligibility=True, got {run_be.get('batchExecutable')}"
        assert run_be["batchEligibleCount"] == 1, \
            f"batchEligibleCount should be 1, got {run_be.get('batchEligibleCount')}"

        # Verify execution counts are NOT computed (executionCountsComplete should be False)
        assert result.get("executionCountsComplete") is False, \
            "executionCountsComplete should be False when using include_batch_eligibility (not include_status)"

    def test_include_batch_eligibility_vs_include_status_timing(self, tmp_path: Path) -> None:
        """Verify include_batch_eligibility skips execution count derivation that include_status does.

        Both should compute batchEligibility, but include_batch_eligibility should be faster
        because it skips the execution artifact scanning for counts.
        """
        # Arrange: Create plan with eligible candidates and execution artifact
        ea_dir = tmp_path / "health" / "external-analysis"
        ea_dir.mkdir(parents=True, exist_ok=True)

        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "candidateId": "c1",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-logs",
                        "description": "kubectl logs test",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 0,
                    },
                    {
                        "candidateId": "c2",
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-get",
                        "description": "kubectl get test",
                        "targetContext": "admin@cluster-a",
                        "requiresOperatorApproval": False,
                        "duplicateOfExistingEvidence": False,
                        "candidateIndex": 1,
                    }
                ]
            }
        }
        plan_path = ea_dir / "run-timing-001-next-check-plan-001.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        # Create execution artifact for candidate index 0
        exec_data = {
            "purpose": "next-check-execution",
            "payload": {"candidateIndex": 0}
        }
        exec_path = ea_dir / "run-timing-001-next-check-execution-001.json"
        exec_path.write_text(json.dumps(exec_data), encoding="utf-8")

        # Create review
        reviews_dir = tmp_path / "health" / "reviews"
        reviews_dir.mkdir(parents=True, exist_ok=True)
        review_data = {
            "run_id": "run-timing-001",
            "timestamp": "2026-05-07T21:00:00Z",
            "run_label": "timing-test-run",
            "cluster_count": 1,
        }
        review_path = reviews_dir / "run-timing-001-review.json"
        review_path.write_text(json.dumps(review_data), encoding="utf-8")

        # Test 1: include_batch_eligibility only
        result_batch = build_runs_list(tmp_path, include_batch_eligibility=True, _timings=True)
        if isinstance(result_batch, tuple):
            payload_batch, timings_batch = result_batch
        else:
            payload_batch = result_batch

        runs_batch = cast(list[dict[str, object]], payload_batch.get("runs", []))
        run_timing_batch = next((r for r in runs_batch if r["runId"] == "run-timing-001"), None)

        # batchEligibility should be computed
        assert run_timing_batch["batchExecutable"] is True, \
            "batchExecutable should be True with include_batch_eligibility"
        # execution counts should NOT be computed
        assert run_timing_batch["executionCount"] == 0, \
            f"executionCount should be 0 (not computed) with include_batch_eligibility, got {run_timing_batch.get('executionCount')}"

        # Test 2: include_status computes full counts
        result_status = build_runs_list(tmp_path, include_status=True, _timings=True)
        if isinstance(result_status, tuple):
            payload_status, timings_status = result_status
        else:
            payload_status = result_status

        runs_status = cast(list[dict[str, object]], payload_status.get("runs", []))
        run_timing_status = next((r for r in runs_status if r["runId"] == "run-timing-001"), None)

        # execution counts should BE computed
        assert run_timing_status["executionCount"] == 1, \
            f"executionCount should be 1 (computed) with include_status, got {run_timing_status.get('executionCount')}"
        # batchEligibility should also be computed
        assert run_timing_status["batchExecutable"] is True, \
            "batchExecutable should be True with include_status"
