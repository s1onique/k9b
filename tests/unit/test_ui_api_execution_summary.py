"""Tests for index-backed execution summary computation.

These tests verify that _build_runs_list_with_batch_eligibility_index() correctly
computes executionSummary from pre-loaded plan/execution data stored in ui-index.json.

Root cause addressed: Without _plan_data and _execution_indices in the stored index,
the index-backed path returned executionSummary=None for all rows, causing Recent Runs
to fall back to batchExecutable and show Execute even after all work was executed.
"""

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.ui.api import (
    _build_runs_list_with_batch_eligibility_index,
    _compute_execution_summary_indexed,
    _normalize_execution_indices_from_index,
)


class IndexBackedExecutionSummaryTests(unittest.TestCase):
    """Tests for execution summary computation in index-backed runs-list path."""

    def test_normalize_execution_indices_handles_int_keys(self) -> None:
        """Test that _normalize_execution_indices_from_index converts string keys to int."""
        # Simulate JSON round-trip where int dict keys become strings
        raw_indices = {
            "run-1": {"0": "success", "1": "success", "2": "failed"},
            "run-2": {"0": "success"},
        }

        normalized = _normalize_execution_indices_from_index(raw_indices)

        # Keys should be integers
        self.assertIn("run-1", normalized)
        indices = normalized["run-1"]
        self.assertIsInstance(indices, dict)
        self.assertIn(0, indices)  # int key, not string
        self.assertIn(1, indices)
        self.assertIn(2, indices)
        self.assertEqual(indices[0], "success")
        self.assertEqual(indices[2], "failed")

    def test_normalize_execution_indices_preserves_int_keys(self) -> None:
        """Test that already-int keys are preserved."""
        raw_indices = {
            "run-1": {0: "success", 1: "success"},
        }

        normalized = _normalize_execution_indices_from_index(raw_indices)

        self.assertIn(0, normalized["run-1"])
        self.assertIn(1, normalized["run-1"])

    def test_compute_execution_summary_fully_executed(self) -> None:
        """Test that execution summary shows fully-executed when all candidates executed."""
        # Create plan data with 5 candidates (all batch-executable)
        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Check pod logs",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-get",
                        "description": "Get resource",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Describe node",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-get",
                        "description": "List events",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Check service",
                        "targetContext": "default",
                    },
                ]
            },
        }

        # Create execution indices for all 5 candidates (all success)
        execution_indices = {0: "success", 1: "success", 2: "success", 3: "success", 4: "success"}

        summary = _compute_execution_summary_indexed(plan_data, execution_indices)

        self.assertEqual(summary["totalCandidates"], 5)
        self.assertEqual(summary["executableCandidates"], 5)
        self.assertEqual(summary["executedCandidates"], 5)
        self.assertEqual(summary["pendingExecutableCandidates"], 0)
        self.assertEqual(summary["batchExecutionState"], "fully-executed")

    def test_compute_execution_summary_partially_executed(self) -> None:
        """Test that execution summary shows partially-executed when some candidates pending."""
        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Check pod logs",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-get",
                        "description": "Get resource",
                        "targetContext": "default",
                    },
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Describe node",
                        "targetContext": "default",
                    },
                ]
            },
        }

        # Only 1 of 3 candidates executed
        execution_indices = {0: "success"}

        summary = _compute_execution_summary_indexed(plan_data, execution_indices)

        self.assertEqual(summary["totalCandidates"], 3)
        self.assertEqual(summary["executableCandidates"], 3)
        self.assertEqual(summary["executedCandidates"], 1)
        self.assertEqual(summary["pendingExecutableCandidates"], 2)
        self.assertEqual(summary["batchExecutionState"], "partially-executed")

    def test_compute_execution_summary_not_started(self) -> None:
        """Test that execution summary shows not-started when no executions exist."""
        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": [
                    {
                        "safeToAutomate": True,
                        "suggestedCommandFamily": "kubectl-describe",
                        "description": "Check pod logs",
                        "targetContext": "default",
                    },
                ]
            },
        }

        # No executions
        execution_indices = {}

        summary = _compute_execution_summary_indexed(plan_data, execution_indices)

        self.assertEqual(summary["totalCandidates"], 1)
        self.assertEqual(summary["executedCandidates"], 0)
        self.assertEqual(summary["pendingExecutableCandidates"], 1)
        self.assertEqual(summary["batchExecutionState"], "not-started")

    def test_compute_execution_summary_no_candidates(self) -> None:
        """Test that execution summary shows no-candidates when plan has none."""
        plan_data = {
            "purpose": "next-check-planning",
            "payload": {
                "candidates": []
            },
        }

        execution_indices = {}

        summary = _compute_execution_summary_indexed(plan_data, execution_indices)

        self.assertEqual(summary["totalCandidates"], 0)
        self.assertEqual(summary["executableCandidates"], 0)
        self.assertEqual(summary["batchExecutionState"], "no-candidates")

    def test_build_runs_list_with_batch_eligibility_index_returns_execution_summary(
        self,
    ) -> None:
        """Test that _build_runs_list_with_batch_eligibility_index returns executionSummary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create a review artifact
            review_content = {
                "run_id": "run-exec-summary",
                "run_label": "Run with Execution",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 1,
            }
            review_path = reviews_dir / "run-exec-summary-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create plan artifact with 3 candidates
            plan_content = {
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl-describe",
                            "description": "Check pod",
                            "targetContext": "default",
                        },
                        {
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl-get",
                            "description": "Get pod",
                            "targetContext": "default",
                        },
                        {
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl-describe",
                            "description": "Describe pod",
                            "targetContext": "default",
                        },
                    ]
                },
            }
            plan_path = external_analysis_dir / "run-exec-summary-next-check-plan.json"
            plan_path.write_text(json.dumps(plan_content), encoding="utf-8")

            # Create execution artifacts for 2 candidates
            for idx in [0, 1]:
                exec_content = {
                    "purpose": "next-check-execution",
                    "status": "success",
                    "payload": {"candidateIndex": idx},
                }
                exec_path = external_analysis_dir / f"run-exec-summary-next-check-execution-{idx}.json"
                exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

            # Build recent_runs_summary with plan_data and execution_indices
            from src.k8s_diag_agent.health.ui import _build_recent_runs_summary

            recent_summary = _build_recent_runs_summary(
                reviews_dir, external_analysis_dir=external_analysis_dir
            )

            # Verify the summary has the required fields
            self.assertIn("_plan_data", recent_summary)
            self.assertIn("_execution_indices", recent_summary)

            plan_data = recent_summary["_plan_data"]
            exec_indices = _normalize_execution_indices_from_index(
                recent_summary["_execution_indices"]
            )

            # Verify we have data for our run
            self.assertIn("run-exec-summary", plan_data)
            self.assertIn("run-exec-summary", exec_indices)
            self.assertEqual(len(exec_indices["run-exec-summary"]), 2)

            # Build the runs list with batch eligibility
            runs_from_index = recent_summary.get("runs", [])
            # Add batch eligibility fields to the runs
            for run in runs_from_index:
                if run["run_id"] == "run-exec-summary":
                    run["batchEligibility"] = "computed"
                    run["batchExecutable"] = False
                    run["batchEligibleCount"] = 0
                    break

            timings: dict[str, object] = {}
            start_time = __import__("time").time()
            result = _build_runs_list_with_batch_eligibility_index(
                runs_dir,
                runs_from_index,
                recent_summary,
                limit=10,
                timings=timings,
                start_time=start_time,
            )

            # Find our run in the result
            found = False
            for run in result["runs"]:
                if run["runId"] == "run-exec-summary":
                    found = True
                    # Key assertion: executionSummary must be present
                    self.assertIsNotNone(run.get("executionSummary"))
                    exec_summary = run["executionSummary"]
                    self.assertIsNotNone(exec_summary)
                    # Verify execution state
                    self.assertEqual(exec_summary["executedCandidates"], 2)
                    self.assertEqual(exec_summary["pendingExecutableCandidates"], 1)
                    self.assertEqual(exec_summary["batchExecutionState"], "partially-executed")
                    break

            self.assertTrue(found, "run-exec-summary not found in result")

    def test_build_runs_list_shows_fully_executed_no_execute_button(self) -> None:
        """Test that runs with all candidates executed have no pending candidates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            runs_health_dir = runs_dir / "health"
            reviews_dir = runs_health_dir / "reviews"
            external_analysis_dir = runs_health_dir / "external-analysis"
            reviews_dir.mkdir(parents=True)
            external_analysis_dir.mkdir(parents=True)

            # Create a review artifact
            review_content = {
                "run_id": "run-fully-exec",
                "run_label": "Run Fully Executed",
                "timestamp": "2026-01-01T00:00:00Z",
                "cluster_count": 1,
            }
            review_path = reviews_dir / "run-fully-exec-review.json"
            review_path.write_text(json.dumps(review_content), encoding="utf-8")

            # Create plan artifact with 2 candidates
            plan_content = {
                "purpose": "next-check-planning",
                "payload": {
                    "candidates": [
                        {
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl-describe",
                            "description": "Check pod",
                            "targetContext": "default",
                        },
                        {
                            "safeToAutomate": True,
                            "suggestedCommandFamily": "kubectl-get",
                            "description": "Get pod",
                            "targetContext": "default",
                        },
                    ]
                },
            }
            plan_path = external_analysis_dir / "run-fully-exec-next-check-plan.json"
            plan_path.write_text(json.dumps(plan_content), encoding="utf-8")

            # Create execution artifacts for ALL candidates
            for idx in [0, 1]:
                exec_content = {
                    "purpose": "next-check-execution",
                    "status": "success",
                    "payload": {"candidateIndex": idx},
                }
                exec_path = external_analysis_dir / f"run-fully-exec-next-check-execution-{idx}.json"
                exec_path.write_text(json.dumps(exec_content), encoding="utf-8")

            # Build recent_runs_summary
            from src.k8s_diag_agent.health.ui import _build_recent_runs_summary

            recent_summary = _build_recent_runs_summary(
                reviews_dir, external_analysis_dir=external_analysis_dir
            )

            plan_data = recent_summary["_plan_data"]
            exec_indices = _normalize_execution_indices_from_index(
                recent_summary["_execution_indices"]
            )

            # Verify run-fully-exec has all executions
            self.assertIn("run-fully-exec", exec_indices)
            self.assertEqual(len(exec_indices["run-fully-exec"]), 2)

            # Compute execution summary for the run
            summary = _compute_execution_summary_indexed(
                plan_data["run-fully-exec"], exec_indices["run-fully-exec"]
            )

            # Key assertions: all candidates executed, no pending
            self.assertEqual(summary["executedCandidates"], 2)
            self.assertEqual(summary["pendingExecutableCandidates"], 0)
            self.assertEqual(summary["batchExecutionState"], "fully-executed")

            # This means batchExecutable should be False (no pending work to do)
            # The frontend should NOT show an Execute button for this run