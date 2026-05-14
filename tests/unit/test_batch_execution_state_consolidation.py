"""Regression tests proving batch eligibility and execution summary agreement.

These tests verify that _compute_batch_eligibility_from_cache() and
_compute_execution_summary() agree on candidate eligibility:
- Candidates excluded from executable count are also excluded from pending executable count
- Executed candidates are not batch-eligible
- Failed executed candidates are not batch-eligible
- Approval-blocked candidates are not batch-eligible and do not count as pending executable
- Duplicate candidates are not batch-eligible and do not count as pending executable
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.ui.api import (
    _compute_batch_eligibility_from_cache,
    _compute_execution_summary,
)
from k8s_diag_agent.ui.api_payloads import BatchExecutionSummary


class TestBatchEligibilityAndExecutionSummaryAgreement:
    """Regression tests proving batch eligibility and execution summary agree."""

    def _make_plan_data(self, run_id: str, candidates: list[dict[str, Any]]) -> dict[str, dict[str, object]]:
        """Create plan data dict in the format expected by the functions."""
        return {run_id: {"payload": {"candidates": candidates}}}

    def _make_execution_indices(
        self, run_id: str, status_by_index: dict[int, str]
    ) -> dict[str, dict[int, str]]:
        """Create execution indices dict with explicit status mapping."""
        return {run_id: status_by_index}

    def _base_executable_candidate(self, index: int = 0) -> dict[str, Any]:
        """Create a base executable candidate."""
        return {
            "description": f"Check resource usage {index}",
            "targetContext": "cluster-a",
            "suggestedCommandFamily": "kubectl",
            "safeToAutomate": True,
            "requiresOperatorApproval": False,
            "duplicateOfExistingEvidence": False,
        }

    def _assert_eligibility_and_summary_agree(
        self,
        run_id: str,
        plan_data: dict[str, dict[str, object]],
        execution_indices: dict[str, dict[int, str]],
        expected_executable: int,
        expected_batch_executable: bool,
        expected_pending: int | None = None,
    ) -> BatchExecutionSummary:
        """Assert that batch eligibility and execution summary agree on executable counts.

        Args:
            run_id: Run ID for the test
            plan_data: Plan data dict
            execution_indices: Execution indices dict
            expected_executable: Expected executableCandidates (total eligible)
            expected_batch_executable: Expected batchExecutable bool
            expected_pending: Expected pendingExecutableCandidates (eligible AND not executed)
                              If None, inferred as executable - executed where applicable
        """
        # Get batch eligibility (returns eligible AND NOT executed)
        batch_executable, batch_eligible_count = _compute_batch_eligibility_from_cache(
            run_id, plan_data, execution_indices
        )

        # Get execution summary
        summary = _compute_execution_summary(
            run_id, plan_data, execution_indices
        )

        # executableCandidates = total eligible (regardless of execution status)
        assert summary["executableCandidates"] == expected_executable, (
            f"summary['executableCandidates'] ({summary['executableCandidates']}) != expected_executable ({expected_executable})"
        )

        # pendingExecutableCandidates = eligible AND NOT executed
        if expected_pending is not None:
            assert summary["pendingExecutableCandidates"] == expected_pending, (
                f"summary['pendingExecutableCandidates'] ({summary['pendingExecutableCandidates']}) != expected_pending ({expected_pending})"
            )

        # Batch eligibility count should match pending (eligible AND not executed)
        # This is the semantic for batch execution: how many can we execute?
        assert batch_eligible_count == summary["pendingExecutableCandidates"], (
            f"batch_eligible_count ({batch_eligible_count}) != summary['pendingExecutableCandidates'] ({summary['pendingExecutableCandidates']})"
        )

        # Batch executable bool should match expected
        assert batch_executable == expected_batch_executable, (
            f"batch_executable ({batch_executable}) != expected_batch_executable ({expected_batch_executable})"
        )

        return summary

    # === Basic agreement tests ===

    def test_agreement_all_candidates_executable_no_execution(self) -> None:
        """Both agree when all candidates are executable and none executed."""
        run_id = "run-agreement-001"
        candidates = [
            self._base_executable_candidate(0),
            self._base_executable_candidate(1),
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=2, expected_batch_executable=True
        )

        # Summary should show not-started state
        assert summary["batchExecutionState"] == "not-started"
        assert summary["executedCandidates"] == 0
        assert summary["pendingExecutableCandidates"] == 2

    def test_agreement_executed_candidates_not_batch_eligible(self) -> None:
        """Executed candidates are not batch-eligible - both agree."""
        run_id = "run-agreement-002"
        candidates = [
            self._base_executable_candidate(0),
            self._base_executable_candidate(1),
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Candidate 0 is executed (status doesn't matter for eligibility)
        execution_indices = self._make_execution_indices(run_id, {0: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=2, expected_batch_executable=True  # Both 0,1 are eligible; 0 executed, 1 pending
        )

        # Summary should show partially-executed state
        assert summary["batchExecutionState"] == "partially-executed"
        assert summary["executedCandidates"] == 1
        assert summary["pendingExecutableCandidates"] == 1  # candidate 1 is pending (eligible, not executed)

    def test_agreement_failed_executed_candidates_not_batch_eligible(self) -> None:
        """Failed executed candidates are not batch-eligible - both agree."""
        run_id = "run-agreement-003"
        candidates = [
            self._base_executable_candidate(0),
            self._base_executable_candidate(1),
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Candidate 0 failed execution - still not batch-eligible
        execution_indices = self._make_execution_indices(run_id, {0: "failed"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=2, expected_batch_executable=True
        )

        # Summary should show partially-executed with 1 failure
        assert summary["batchExecutionState"] == "partially-executed"
        assert summary["executedCandidates"] == 1
        assert summary["failedCandidates"] == 1
        assert summary["pendingExecutableCandidates"] == 1  # candidate 1 is pending (eligible, not executed)

    def test_agreement_all_executed_fully_executed_state(self) -> None:
        """Both agree when all executable candidates are executed."""
        run_id = "run-agreement-004"
        candidates = [
            self._base_executable_candidate(0),
            self._base_executable_candidate(1),
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Both executed
        execution_indices = self._make_execution_indices(run_id, {0: "success", 1: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=2, expected_batch_executable=False  # Both eligible, both executed
        )

        # Summary should show fully-executed state
        assert summary["batchExecutionState"] == "fully-executed"
        assert summary["executedCandidates"] == 2
        assert summary["pendingExecutableCandidates"] == 0  # All eligible candidates executed

    # === Approval-blocked tests ===

    def test_agreement_approval_blocked_not_executable(self) -> None:
        """Approval-blocked candidates are not batch-eligible - both agree."""
        run_id = "run-agreement-005"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Approval blocked check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "pending",  # Not approved
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        # Summary should show not-started with only 1 executable
        assert summary["batchExecutionState"] == "not-started"
        assert summary["pendingExecutableCandidates"] == 1  # 1 executable - 0 executed = 1 pending

    def test_agreement_approval_blocked_with_execution(self) -> None:
        """Approval-blocked candidate that was executed doesn't count as pending."""
        run_id = "run-agreement-006"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Approval blocked check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "pending",
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Executed candidate 0, but candidate 1 is blocked
        execution_indices = self._make_execution_indices(run_id, {0: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=False,  # Candidate 0 eligible, 1 blocked
            expected_pending=0  # 0 pending (executed)
        )

        # Only candidate 0 is executable, and it's executed
        assert summary["batchExecutionState"] == "fully-executed"
        assert summary["pendingExecutableCandidates"] == 0

    def test_agreement_approved_candidate_is_executable(self) -> None:
        """Approved candidates are executable - both agree."""
        run_id = "run-agreement-007"
        candidates = [
            {
                "description": "Approved check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "approved",  # Explicitly approved
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["batchExecutionState"] == "not-started"
        assert summary["pendingExecutableCandidates"] == 1

    # === Duplicate tests ===

    def test_agreement_duplicate_not_executable(self) -> None:
        """Duplicate candidates are not batch-eligible - both agree."""
        run_id = "run-agreement-008"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Duplicate check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": True,  # Marked as duplicate
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["batchExecutionState"] == "not-started"
        assert summary["pendingExecutableCandidates"] == 1

    def test_agreement_duplicate_with_execution(self) -> None:
        """Duplicate candidate that was executed doesn't count as pending."""
        run_id = "run-agreement-009"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Duplicate check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": True,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Executed candidate 0, candidate 1 is duplicate
        execution_indices = self._make_execution_indices(run_id, {0: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=False,  # 0 eligible, 1 is duplicate
            expected_pending=0  # 0 pending (executed)
        )

        assert summary["batchExecutionState"] == "fully-executed"
        assert summary["pendingExecutableCandidates"] == 0

    # === Not safe to automate tests ===

    def test_agreement_not_safe_to_automate_not_executable(self) -> None:
        """Candidates not safe to automate are not batch-eligible - both agree."""
        run_id = "run-agreement-010"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Dangerous check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": False,  # Not safe
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["batchExecutionState"] == "not-started"
        assert summary["pendingExecutableCandidates"] == 1

    # === Missing fields tests ===

    def test_agreement_missing_command_family_not_executable(self) -> None:
        """Candidates missing command family are not batch-eligible - both agree."""
        run_id = "run-agreement-011"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Check without command",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": None,  # Missing
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["pendingExecutableCandidates"] == 1

    def test_agreement_missing_description_not_executable(self) -> None:
        """Candidates missing description are not batch-eligible - both agree."""
        run_id = "run-agreement-012"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": None,  # Missing
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["pendingExecutableCandidates"] == 1

    def test_agreement_missing_target_context_not_executable(self) -> None:
        """Candidates missing target context are not batch-eligible - both agree."""
        run_id = "run-agreement-013"
        candidates = [
            self._base_executable_candidate(0),
            {
                "description": "Check without context",
                "targetContext": None,  # Missing
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=True
        )

        assert summary["pendingExecutableCandidates"] == 1

    # === No candidates tests ===

    def test_agreement_no_candidates(self) -> None:
        """Both agree when there are no candidates."""
        run_id = "run-agreement-014"
        candidates: list[dict[str, Any]] = []
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=0, expected_batch_executable=False
        )

        assert summary["batchExecutionState"] == "no-candidates"
        assert summary["totalCandidates"] == 0

    # === Mixed state tests ===

    def test_agreement_mixed_partial_run(self) -> None:
        """Both agree on a mixed partial run with various states."""
        run_id = "run-agreement-015"
        candidates = [
            self._base_executable_candidate(0),  # Executable
            self._base_executable_candidate(1),  # Executable
            {
                "description": "Approval blocked",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "pending",
                "duplicateOfExistingEvidence": False,
            },  # Not executable
            self._base_executable_candidate(3),  # Executable
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Only candidate 0 is executed (as success)
        execution_indices = self._make_execution_indices(run_id, {0: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=3, expected_batch_executable=True  # candidates 0,1,3 are eligible; 0 executed, 1,3 pending
        )

        assert summary["batchExecutionState"] == "partially-executed"
        assert summary["executedCandidates"] == 1
        assert summary["pendingExecutableCandidates"] == 2  # candidates 1,3 are pending (eligible, not executed)

    def test_agreement_unknown_status_not_failed(self) -> None:
        """Unknown status counts as executed but not failed - both agree."""
        run_id = "run-agreement-016"
        candidates = [
            self._base_executable_candidate(0),
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Unknown status - executed but not failed
        execution_indices = self._make_execution_indices(run_id, {0: "unknown"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1, expected_batch_executable=False,  # 0 eligible (executed=unknown)
            expected_pending=0  # 0 pending (executed)
        )

        assert summary["batchExecutionState"] == "fully-executed"
        assert summary["executedCandidates"] == 1
        assert summary["failedCandidates"] == 0  # unknown is not failed
        assert summary["pendingExecutableCandidates"] == 0



    def test_agreement_ineligible_candidate_with_execution_artifact(self) -> None:
        """Ineligible candidate with execution artifact should not cause negative pending.

        This test verifies the edge case where:
        - One eligible candidate is executed (has artifact)
        - One ineligible candidate ALSO has an execution artifact
        - pendingExecutableCandidates should be 0
        - batchExecutionState should be "fully-executed"
        - No negative or derived pending behavior occurs
        """
        run_id = "run-agreement-edge-case"
        candidates = [
            self._base_executable_candidate(0),  # Eligible
            {
                "description": "Approval blocked check",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "pending",  # Blocked - not eligible
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # Both candidates have execution artifacts
        # - Index 0: eligible, executed
        # - Index 1: blocked, but also has execution artifact (stale from when it was eligible)
        execution_indices = self._make_execution_indices(run_id, {0: "success", 1: "success"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=1,  # Only index 0 is eligible
            expected_batch_executable=False,  # No pending (index 0 is executed)
            expected_pending=0  # 0 pending (executed)
        )

        # State should be fully-executed despite index 1 having an artifact
        # because index 1 is not eligible and index 0 is executed
        assert summary["batchExecutionState"] == "fully-executed"
        assert summary["executedCandidates"] == 2  # Both have artifacts
        assert summary["failedCandidates"] == 0  # No failures
        # Critical: pending should NOT be negative even though executed (2) > executable (1)
        assert summary["pendingExecutableCandidates"] == 0


    # === Shared helper tests ===

    def test_agreement_pending_executable_equals_executable_minus_executed(self) -> None:
        """pendingExecutableCandidates = executableCandidates - executedCandidates."""
        run_id = "run-agreement-017"
        candidates = [
            self._base_executable_candidate(0),  # Executable
            self._base_executable_candidate(1),  # Executable
            self._base_executable_candidate(2),  # Executable
            self._base_executable_candidate(3),  # Executable
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        # 2 executed
        execution_indices = self._make_execution_indices(run_id, {0: "success", 1: "failed"})

        summary = self._assert_eligibility_and_summary_agree(
            run_id, plan_data, execution_indices,
            expected_executable=4, expected_batch_executable=True,  # All 4 eligible
            expected_pending=2  # 2 pending (indices 2,3)
        )

        assert summary["executedCandidates"] == 2
        assert summary["failedCandidates"] == 1  # Only 1 failed
