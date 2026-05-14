"""Shared execution-state derivation helpers for batch-eligible candidate assessment.

This module provides pure helpers for determining:
- Whether a candidate is batch-executable (eligible for batch execution)
- Detailed execution state and counts for a run's candidates

These helpers are used by:
- Recent Runs (ui/api.py) for execution summary computation
- QueuePanel uses NextCheckExecutionRecord-based paths from ui_next_check_execution.py

The batch eligibility logic is intentionally kept separate from the detailed
NextCheckExecutionRecord path to preserve their different use cases.

Key invariants:
- executed candidates are not batch-eligible (no re-execution)
- failed candidates are not batch-eligible (no re-execution)
- approval-blocked candidates are not batch-eligible
- duplicate candidates are not batch-eligible
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .api_payloads import BatchExecutionSummary

if TYPE_CHECKING:
    pass


def _is_candidate_batch_executable(
    candidate: dict[str, object],
) -> bool:
    """Check if a candidate meets batch execution eligibility criteria.

    A candidate is batch-executable when ALL of these are true:
    1. safeToAutomate is true
    2. Has a valid suggestedCommandFamily
    3. Has a description
    4. Has targetContext
    5. If requiresOperatorApproval is true, approvalStatus must be "approved"
    6. duplicateOfExistingEvidence is false

    NOTE: This function checks ELIGIBILITY criteria only. It does NOT check
    execution state. Use _is_candidate_executed() separately to determine if
    a candidate has already been executed.

    This logic is shared between:
    - _compute_batch_eligibility_from_cache() (Recent Runs)
    - _compute_execution_summary() (Recent Runs)
    - batch.py::is_candidate_eligible() (CLI batch execution)

    Args:
        candidate: The candidate dictionary from next-check-plan

    Returns:
        True if the candidate meets batch execution eligibility criteria, False otherwise
    """
    # Must be safe to automate
    if not candidate.get("safeToAutomate"):
        return False

    # Must have a valid command family
    family = candidate.get("suggestedCommandFamily")
    if not family or not isinstance(family, str):
        return False

    # Must have a description
    description = candidate.get("description")
    if not description or not isinstance(description, str):
        return False

    # Must have target context info
    target_context = candidate.get("targetContext")
    if not target_context or not isinstance(target_context, str):
        return False

    # Check approval requirement - must be approved if approval is required
    requires_approval = candidate.get("requiresOperatorApproval")
    if requires_approval:
        approval_status = str(candidate.get("approvalStatus") or "").lower()
        if approval_status != "approved":
            return False

    # Check for duplicates - duplicate candidates should not be batch-executed
    if candidate.get("duplicateOfExistingEvidence"):
        return False

    return True


def _is_candidate_executed(
    candidate_index: int,
    execution_indices: dict[int, str],
) -> bool:
    """Check if a candidate has already been executed.

    Args:
        candidate_index: The candidate's index in the plan
        execution_indices: Dict mapping candidate_index -> status string
            Candidates in this dict have execution artifacts

    Returns:
        True if the candidate has execution artifacts, False otherwise
    """
    return candidate_index in execution_indices


def _compute_execution_counts_from_candidates(
    candidates_data: list[dict[str, object]],
    execution_indices: dict[int, str],
) -> tuple[int, int, int, int]:
    """Compute executable, executed, failed, and pending-executable counts from candidates.

    This is the core counting logic shared by batch eligibility and execution
    summary computation.

    Args:
        candidates_data: List of candidate dictionaries from next-check-plan
        execution_indices: Dict mapping candidate_index -> status string
            (from execution artifacts)

    Returns:
        Tuple of (executable_count, executed_count, failed_count, pending_executable_count)
    """
    executable_count = 0
    executed_count = 0
    failed_count = 0
    pending_executable_count = 0

    for idx, candidate in enumerate(candidates_data):
        # Check if this candidate is executable (eligibility criteria only)
        is_executable = _is_candidate_batch_executable(candidate)

        # Check execution state for this candidate
        is_executed = _is_candidate_executed(idx, execution_indices)

        # executableCandidates = eligible candidates (regardless of execution status)
        # This counts ALL candidates that meet batch execution eligibility criteria
        if is_executable:
            executable_count += 1
            # pendingExecutableCandidates = eligible candidates WITHOUT execution artifacts
            # Only increment pending if NOT executed
            if not is_executed:
                pending_executable_count += 1

        if is_executed:
            executed_count += 1
            # Failed candidates have status == "failed"
            status = execution_indices[idx]
            if status == "failed":
                failed_count += 1

    return executable_count, executed_count, failed_count, pending_executable_count


def _derive_batch_execution_state(
    executable_count: int,
    executed_count: int,
    pending_executable_count: int,
) -> Literal["no-candidates", "not-started", "partially-executed", "fully-executed"]:
    """Derive the canonical batch execution state.

    Args:
        executable_count: Number of batch-executable candidates (eligible)
        executed_count: Number of candidates with execution artifacts
        pending_executable_count: Number of eligible candidates without execution artifacts

    Returns:
        Canonical batch execution state string

    Note:
        We derive state from explicit pending count rather than computing
        pending = executable - executed, because executed_count may include
        candidates that are currently ineligible/blocked but still have artifacts.
    """
    if executable_count == 0:
        return "no-candidates"
    if executed_count == 0 and pending_executable_count > 0:
        return "not-started"
    if pending_executable_count == 0 and executed_count > 0:
        return "fully-executed"
    if executed_count > 0 and pending_executable_count > 0:
        return "partially-executed"
    # Edge case: no executions yet and no pending means not-started
    return "not-started"


def compute_batch_execution_summary(
    plan_data: dict[str, object] | None,
    execution_indices: dict[int, str],
) -> BatchExecutionSummary:
    """Compute execution summary from plan data and execution indices.

    This is the indexed path helper for Recent Runs Execute button eligibility.
    It uses pre-scanned plan and execution data without filesystem access.

    Args:
        plan_data: The next-check-plan dict (may be None)
        execution_indices: Dict mapping candidate_index -> status string

    Returns:
        BatchExecutionSummary with all execution state fields
    """
    from typing import cast

    if not plan_data:
        return BatchExecutionSummary(
            totalCandidates=0,
            executableCandidates=0,
            executedCandidates=0,
            failedCandidates=0,
            pendingExecutableCandidates=0,
            batchExecutionState="no-candidates",
        )

    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    total_candidates = len(candidates_data)

    if total_candidates == 0:
        return BatchExecutionSummary(
            totalCandidates=0,
            executableCandidates=0,
            executedCandidates=0,
            failedCandidates=0,
            pendingExecutableCandidates=0,
            batchExecutionState="no-candidates",
        )

    # Compute counts using shared helper (returns 4 values)
    executable_count, executed_count, failed_count, pending_executable = _compute_execution_counts_from_candidates(
        candidates_data, execution_indices
    )

    # Derive batch execution state using explicit pending count
    batch_execution_state = _derive_batch_execution_state(executable_count, executed_count, pending_executable)

    return BatchExecutionSummary(
        totalCandidates=total_candidates,
        executableCandidates=executable_count,
        executedCandidates=executed_count,
        failedCandidates=failed_count,
        pendingExecutableCandidates=max(pending_executable, 0),
        batchExecutionState=batch_execution_state,
    )