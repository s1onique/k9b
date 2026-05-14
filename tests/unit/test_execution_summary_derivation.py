"""Regression tests for execution summary derivation in Recent Runs Execute button eligibility.

Tests the new execution summary contract:
- batchExecutionState: "no-candidates" | "not-started" | "partially-executed" | "fully-executed"
- pendingExecutableCandidates: count of executable candidates without execution artifacts
- Button visibility derives from execution summary when present, batchExecutable as fallback
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.ui.api import _compute_execution_summary
from k8s_diag_agent.ui.api_payloads import BatchExecutionSummary


class TestExecutionSummaryDerivation:
    """Regression tests for execution summary computation."""

    def _make_plan_data(self, run_id: str, candidates: list[dict[str, Any]]) -> dict[str, dict[str, object]]:
        """Create plan data dict in the format expected by _compute_execution_summary."""
        return {run_id: {"payload": {"candidates": candidates}}}

    def _make_execution_indices(self, run_id: str, indices: set[int]) -> dict[str, set[int]]:
        """Create execution indices dict in the format expected by _compute_execution_summary."""
        return {run_id: indices}

    def _assert_summary(self, summary: BatchExecutionSummary, **expected: Any) -> None:
        """Assert summary fields using dict-style access on TypedDict.

        Convert TypedDict to dict for dynamic key access to satisfy mypy's
        literal-required constraint on TypedDict keys.
        """
        summary_dict: dict[str, Any] = dict(summary)
        for key, value in expected.items():
            assert summary_dict[key] == value, f"Expected summary[{key}]={value}, got {summary_dict[key]}"

    def test_not_started_state_with_executable_candidates(self) -> None:
        """Fresh run with executable candidates => not-started, pending > 0."""
        run_id = "run-001"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
            {
                "description": "Check pod status",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        self._assert_summary(summary, batchExecutionState="not-started", pendingExecutableCandidates=2, executedCandidates=0, executableCandidates=2)

    def test_fully_executed_state_all_success(self) -> None:
        """All candidates executed successfully => fully-executed, pending == 0."""
        run_id = "run-002"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {0})

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        self._assert_summary(summary, batchExecutionState="fully-executed", pendingExecutableCandidates=0, executedCandidates=1)

    def test_fully_executed_state_with_failures(self) -> None:
        """All candidates executed with failures => fully-executed, pending == 0."""
        run_id = "run-003"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {0})

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Failure artifacts still count as executed (no remaining work for that candidate)
        self._assert_summary(summary, batchExecutionState="fully-executed", pendingExecutableCandidates=0, executedCandidates=1)

    def test_partially_executed_state(self) -> None:
        """Subset executed => partially-executed, pending > 0."""
        run_id = "run-004"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
            {
                "description": "Check pod status",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
            {
                "description": "Check node status",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {0})

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        self._assert_summary(summary, batchExecutionState="partially-executed", pendingExecutableCandidates=2, executedCandidates=1, executableCandidates=3)

    def test_validation_failure_counts_as_executed(self) -> None:
        """Validation failure artifacts count as executed-failed for button eligibility."""
        run_id = "run-005"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, {0})

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Execution artifact exists - counts as executed even if failure
        self._assert_summary(summary, batchExecutionState="fully-executed", pendingExecutableCandidates=0, executedCandidates=1)

    def test_approval_blocked_not_executable(self) -> None:
        """Approval-blocked candidates are not currently executable."""
        run_id = "run-006"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "pending",  # Not yet approved
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Approval-blocked candidate is not executable
        self._assert_summary(summary, executableCandidates=0, batchExecutionState="no-candidates")

    def test_no_candidates_state(self) -> None:
        """Run with no candidates => no-candidates state."""
        run_id = "run-007"
        candidates: list[dict[str, Any]] = []
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        self._assert_summary(summary, batchExecutionState="no-candidates", totalCandidates=0, executableCandidates=0, pendingExecutableCandidates=0)

    def test_duplicate_candidates_not_executable(self) -> None:
        """Duplicate candidates are not counted as executable."""
        run_id = "run-008"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
            {
                "description": "Check kubelet again",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": True,  # Marked as duplicate
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Only non-duplicate is executable
        self._assert_summary(summary, executableCandidates=1, batchExecutionState="not-started", pendingExecutableCandidates=1)

    def test_approved_candidate_is_executable(self) -> None:
        """Approved candidates are executable even if requiresOperatorApproval is True."""
        run_id = "run-009"
        candidates = [
            {
                "description": "Check kubelet metrics",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": True,
                "requiresOperatorApproval": True,
                "approvalStatus": "approved",  # Approved - should be executable
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Approved candidate is executable
        self._assert_summary(summary, executableCandidates=1, batchExecutionState="not-started", pendingExecutableCandidates=1)

    def test_not_safe_to_automate_not_executable(self) -> None:
        """Candidates not safe to automate are not executable."""
        run_id = "run-010"
        candidates = [
            {
                "description": "Dangerous operation",
                "targetContext": "cluster-a",
                "suggestedCommandFamily": "kubectl",
                "safeToAutomate": False,  # Not safe to automate
                "requiresOperatorApproval": False,
                "duplicateOfExistingEvidence": False,
            },
        ]
        plan_data = self._make_plan_data(run_id, candidates)
        execution_indices = self._make_execution_indices(run_id, set())

        summary = _compute_execution_summary(run_id, all_plan_data=plan_data, all_execution_indices=execution_indices)

        # Not safe to automate = not executable
        self._assert_summary(summary, executableCandidates=0, batchExecutionState="no-candidates")