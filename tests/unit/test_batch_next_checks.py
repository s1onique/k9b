"""Tests for batch next-check execution script."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.batch import (  # noqa: E402
    BatchExecutionResult,
    collect_candidates,
    is_candidate_eligible,
    load_existing_execution_indices,
    run_batch_next_checks,
)


class BatchNextCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.runs_dir = self.tmpdir
        # Create required directory structure
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.external_dir = self.health_dir / "external-analysis"
        self.external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_ui_index(self, run_id: str, run_label: str, plan_data: dict | None = None) -> None:
        """Create a minimal ui-index.json for testing."""
        index_data = {
            "run": {
                "run_id": run_id,
                "run_label": run_label,
                "next_check_plan": plan_data,
            }
        }
        (self.health_dir / "ui-index.json").write_text(
            json.dumps(index_data), encoding="utf-8"
        )

    def _create_plan_artifact(self, run_id: str, candidates: list[dict]) -> Path:
        """Create a next-check-plan artifact file."""
        plan_data = {
            "purpose": "next-check-planning",
            "run_id": run_id,
            "candidates": candidates,
        }
        plan_path = self.external_dir / f"{run_id}-next-check-plan.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
        return plan_path

    def _create_execution_artifact(self, run_id: str, candidate_index: int) -> None:
        """Create a mock execution artifact to simulate already-executed candidate."""
        artifact_data = {
            "purpose": "next-check-execution",
            "run_id": run_id,
            "status": "success",
            "payload": {
                "candidateIndex": candidate_index,
            },
        }
        artifact_path = self.external_dir / f"{run_id}-next-check-execution-{candidate_index}.json"
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

    def _base_candidate(self, index: int = 0) -> dict:
        return {
            "description": f"kubectl get pods -n default {index}",
            "targetCluster": "cluster-a",
            "targetContext": "prod",
            "suggestedCommandFamily": "kubectl-get",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
            "candidateId": f"candidate-{index}",
        }

    # Tests for eligibility checking

    def test_eligible_candidate_passes_all_checks(self) -> None:
        """Eligible candidate passes all eligibility checks."""
        candidate = self._base_candidate()
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertTrue(is_eligible)
        self.assertIsNone(reason)

    def test_already_executed_candidate_is_ineligible(self) -> None:
        """Candidate already executed is marked ineligible."""
        candidate = self._base_candidate()
        execution_indices = {0}
        is_eligible, reason = is_candidate_eligible(candidate, execution_indices, 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "already_executed")

    def test_not_safe_to_automate_is_ineligible(self) -> None:
        """Candidate not marked safe to automate is ineligible."""
        candidate = self._base_candidate()
        candidate["safeToAutomate"] = False
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "not_safe_to_automate")

    def test_missing_command_family_is_ineligible(self) -> None:
        """Candidate without command family is ineligible."""
        candidate = self._base_candidate()
        candidate["suggestedCommandFamily"] = ""
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "missing_command_family")

    def test_missing_description_is_ineligible(self) -> None:
        """Candidate without description is ineligible."""
        candidate = self._base_candidate()
        candidate["description"] = ""
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "missing_description")

    def test_missing_target_context_is_ineligible(self) -> None:
        """Candidate without target context is ineligible."""
        candidate = self._base_candidate()
        candidate["targetContext"] = ""
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "missing_target_context")

    def test_requires_approval_without_approval_is_ineligible(self) -> None:
        """Candidate requiring approval but not approved is ineligible."""
        candidate = self._base_candidate()
        candidate["requiresOperatorApproval"] = True
        candidate["approvalStatus"] = "pending"
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "requires_approval")

    def test_requires_approval_with_approval_is_eligible(self) -> None:
        """Candidate requiring approval but already approved is eligible."""
        candidate = self._base_candidate()
        candidate["requiresOperatorApproval"] = True
        candidate["approvalStatus"] = "approved"
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertTrue(is_eligible)
        self.assertIsNone(reason)

    def test_duplicate_of_existing_evidence_is_ineligible(self) -> None:
        """Candidate marked as duplicate is ineligible."""
        candidate = self._base_candidate()
        candidate["duplicateOfExistingEvidence"] = True
        is_eligible, reason = is_candidate_eligible(candidate, set(), 0)
        self.assertFalse(is_eligible)
        self.assertEqual(reason, "duplicate_of_existing_evidence")

    # Tests for candidate collection

    def test_collects_candidates_from_plan(self) -> None:
        """Correctly collects candidates from plan data."""
        plan = {
            "candidates": [
                self._base_candidate(0),
                self._base_candidate(1),
            ]
        }
        candidates = collect_candidates(plan)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0][0], 0)
        self.assertEqual(candidates[1][0], 1)

    def test_collects_candidates_from_payload(self) -> None:
        """Correctly collects candidates from plan payload."""
        plan = {
            "payload": {
                "candidates": [
                    self._base_candidate(0),
                    self._base_candidate(1),
                ]
            }
        }
        candidates = collect_candidates(plan)
        self.assertEqual(len(candidates), 2)

    def test_avoids_duplicates_when_candidates_in_both_places(self) -> None:
        """Avoids duplicating candidates when present in both plan and payload."""
        plan = {
            "candidates": [self._base_candidate(0)],
            "payload": {
                "candidates": [self._base_candidate(0)],
            }
        }
        candidates = collect_candidates(plan)
        self.assertEqual(len(candidates), 1)

    # Tests for execution index loading

    def test_loads_existing_execution_indices(self) -> None:
        """Correctly loads indices of already-executed candidates."""
        run_id = "test-run"
        # Create execution artifacts
        self._create_execution_artifact(run_id, 0)
        self._create_execution_artifact(run_id, 2)
        self._create_execution_artifact(run_id, 5)

        indices = load_existing_execution_indices(self.health_dir, run_id)
        self.assertEqual(indices, {0, 2, 5})

    def test_returns_empty_set_when_no_execution_artifacts(self) -> None:
        """Returns empty set when no execution artifacts exist."""
        indices = load_existing_execution_indices(self.health_dir, "nonexistent-run")
        self.assertEqual(indices, set())

    # Tests for batch execution flow

    def test_batch_execution_skips_already_executed(self) -> None:
        """Batch execution skips candidates that are already executed."""
        run_id = "test-run"
        run_label = "test-run"
        
        # Create UI index with plan
        plan_path = self._create_plan_artifact(run_id, [self._base_candidate(0)])
        plan_data = {
            "artifact_path": str(plan_path),
            "candidates": [self._base_candidate(0)],
        }
        self._create_ui_index(run_id, run_label, plan_data)
        
        # Mark candidate as already executed
        self._create_execution_artifact(run_id, 0)

        # Run batch execution
        result = run_batch_next_checks(
            runs_dir=self.runs_dir,
            run_id=run_id,
            dry_run=True,
        )

        self.assertEqual(result.total_candidates, 1)
        self.assertEqual(result.skipped_already_executed, 1)
        self.assertEqual(result.executed_count, 0)

    def test_batch_execution_filters_ineligible(self) -> None:
        """Batch execution filters out ineligible candidates."""
        run_id = "test-run"
        run_label = "test-run"
        
        candidates = [
            self._base_candidate(0),  # eligible
            {**self._base_candidate(1), "safeToAutomate": False},  # not safe
            self._base_candidate(2),  # eligible
        ]
        
        plan_path = self._create_plan_artifact(run_id, candidates)
        plan_data = {
            "artifact_path": str(plan_path),
            "candidates": candidates,
        }
        self._create_ui_index(run_id, run_label, plan_data)

        result = run_batch_next_checks(
            runs_dir=self.runs_dir,
            run_id=run_id,
            dry_run=True,
        )

        self.assertEqual(result.total_candidates, 3)
        self.assertEqual(result.eligible_candidates, 2)
        self.assertEqual(result.skipped_ineligible, 1)

    def test_batch_execution_writes_execution_artifacts(self) -> None:
        """Batch execution writes standard next-check-execution artifacts."""
        run_id = "test-run"
        run_label = "test-run"
        
        candidates = [self._base_candidate(0)]
        plan_path = self._create_plan_artifact(run_id, candidates)
        plan_data = {
            "artifact_path": str(plan_path),
            "candidates": candidates,
        }
        self._create_ui_index(run_id, run_label, plan_data)

        # Mock the command runner to avoid actual kubectl calls
        def mock_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        with patch("k8s_diag_agent.batch.execute_manual_next_check") as mock_exec:
            mock_exec.side_effect = lambda **kwargs: mock_runner(kwargs.get("command", []))

            run_batch_next_checks(
                runs_dir=self.runs_dir,
                run_id=run_id,
                dry_run=False,
            )

            # Verify execute_manual_next_check was called
            self.assertEqual(mock_exec.call_count, 1)

    def test_batch_execution_returns_correct_stats(self) -> None:
        """Batch execution returns correct statistics."""
        run_id = "test-run"
        run_label = "test-run"
        
        candidates = [
            self._base_candidate(0),
            self._base_candidate(1),
            {**self._base_candidate(2), "safeToAutomate": False},  # ineligible
        ]
        
        plan_path = self._create_plan_artifact(run_id, candidates)
        plan_data = {
            "artifact_path": str(plan_path),
            "candidates": candidates,
        }
        self._create_ui_index(run_id, run_label, plan_data)

        result = run_batch_next_checks(
            runs_dir=self.runs_dir,
            run_id=run_id,
            dry_run=True,
        )

        self.assertEqual(result.total_candidates, 3)
        self.assertEqual(result.eligible_candidates, 2)
        self.assertEqual(result.skipped_ineligible, 1)
        self.assertEqual(result.executed_count, 2)
        self.assertEqual(result.failed_count, 0)

    def test_batch_execution_handles_missing_plan(self) -> None:
        """Batch execution handles missing next_check_plan gracefully."""
        run_id = "test-run"
        run_label = "test-run"
        
        # Create UI index without plan
        self._create_ui_index(run_id, run_label, None)

        result = run_batch_next_checks(
            runs_dir=self.runs_dir,
            run_id=run_id,
            dry_run=True,
        )

        self.assertEqual(result.total_candidates, 0)
        self.assertEqual(result.eligible_candidates, 0)

    def test_batch_execution_handles_missing_ui_index(self) -> None:
        """Batch execution handles missing UI index gracefully."""
        # Don't create any UI index
        
        with self.assertRaises(FileNotFoundError):
            run_batch_next_checks(
                runs_dir=self.runs_dir,
                run_id="test-run",
                dry_run=True,
            )

    # Tests for BatchExecutionResult

    def test_batch_execution_result_to_dict(self) -> None:
        """BatchExecutionResult correctly serializes to dict."""
        result = BatchExecutionResult(
            total_candidates=10,
            eligible_candidates=8,
            executed_count=7,
            skipped_already_executed=1,
            skipped_ineligible=2,
            failed_count=1,
        )
        
        data = result.to_dict()
        self.assertEqual(data["total_candidates"], 10)
        self.assertEqual(data["eligible_candidates"], 8)
        self.assertEqual(data["executed_count"], 7)
        self.assertEqual(data["skipped_already_executed"], 1)
        self.assertEqual(data["skipped_ineligible"], 2)
        self.assertEqual(data["failed_count"], 1)
        self.assertEqual(data["success_count"], 6)  # executed - failed


if __name__ == "__main__":
    unittest.main()