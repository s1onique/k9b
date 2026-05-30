"""Batch eligibility and execution summary computations for runs-list.

This module contains the batch eligibility and execution summary computation
logic used by the runs-list API endpoints.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

import json

# Use the original logger name for compatibility
import logging
from pathlib import Path
from typing import Literal, cast

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id
from ._batch_execution_state import (
    _is_candidate_batch_executable,
    _is_candidate_executed,
)
from .api_payloads import BatchExecutionSummary

logger = logging.getLogger("k8s_diag_agent.ui.api")


def _compute_batch_eligibility(
    run_id: str,
    run_health_dir: Path,
) -> tuple[bool, int]:
    """Compute batch executable status for a run.

    Uses the same eligibility logic as run_batch_next_checks.py to determine
    if there are any eligible candidates that can be batch-executed.

    Returns:
        Tuple of (batchExecutable: bool, batchEligibleCount: int)
    """
    # SECURITY: Validate run_id before using in glob patterns
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return safe fallback
        return False, 0

    external_analysis_dir = run_health_dir / "external-analysis"

    # Load next_check_plan for this run
    plan_data: dict[str, object] | None = None

    if external_analysis_dir.is_dir():
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
        for plan_path in external_analysis_dir.glob(glob_pattern):
            try:
                raw = json.loads(plan_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-planning":
                    plan_data = cast(dict[str, object], raw)
                    break
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    if not plan_data:
        return False, 0

    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    if not candidates_data:
        return False, 0

    # Load already-executed indices
    execution_indices: set[int] = set()
    if external_analysis_dir.is_dir():
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-execution*.json")
        for exec_path in external_analysis_dir.glob(glob_pattern):
            try:
                raw = json.loads(exec_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-execution":
                    payload = raw.get("payload", {})
                    candidate_index = payload.get("candidateIndex")
                    if isinstance(candidate_index, int):
                        execution_indices.add(candidate_index)
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    # Count eligible candidates using the same logic as run_batch_next_checks.py
    eligible_count = 0
    for idx, candidate in enumerate(candidates_data):
        # Already executed?
        if idx in execution_indices:
            continue

        # Must be safe to automate
        if not candidate.get("safeToAutomate"):
            continue

        # Must have a valid command family
        family = candidate.get("suggestedCommandFamily")
        if not family or not isinstance(family, str):
            continue

        # Must have a description
        description = candidate.get("description")
        if not description or not isinstance(description, str):
            continue

        # Must have target context info
        target_context = candidate.get("targetContext")
        if not target_context or not isinstance(target_context, str):
            continue

        # Check approval requirement
        requires_approval = candidate.get("requiresOperatorApproval")
        if requires_approval:
            approval_status = str(candidate.get("approvalStatus") or "").lower()
            if approval_status != "approved":
                continue

        # Check for duplicates
        if candidate.get("duplicateOfExistingEvidence"):
            continue

        eligible_count += 1

    return eligible_count > 0, eligible_count


def _compute_batch_eligibility_from_cache(
    run_id: str,
    all_plan_data: dict[str, dict[str, object]],
    all_execution_indices: dict[str, dict[int, str]],
) -> tuple[bool, int]:
    """Compute batch eligibility using pre-scanned data (no filesystem access).

    This is the optimized version that uses data pre-loaded in Stage 3b
    to eliminate per-row filesystem operations.

    Returns:
        Tuple of (batchExecutable: bool, batchEligibleCount: int)
    """
    # SECURITY: Validate run_id for consistency
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - return safe fallback
        return False, 0

    plan_data = all_plan_data.get(validated_run_id)
    if not plan_data:
        return False, 0

    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    if not candidates_data:
        return False, 0

    # Get pre-loaded execution indices (use validated_run_id for dict lookup)
    execution_indices = all_execution_indices.get(validated_run_id, {})

    # Count eligible candidates using the shared helper for consistency
    eligible_count = 0
    for idx, candidate in enumerate(candidates_data):
        if _is_candidate_batch_executable(candidate) and not _is_candidate_executed(idx, execution_indices):
            eligible_count += 1

    return eligible_count > 0, eligible_count


def _compute_execution_summary(
    run_id: str,
    all_plan_data: dict[str, dict[str, object]],
    all_execution_indices: dict[str, dict[int, str]],
) -> BatchExecutionSummary:
    """Compute execution summary for a run's batch execution state.

    Derives the execution summary from next-check plan candidates and execution
    artifacts. This provides sufficient information for Recent Runs Execute
    button eligibility without requiring full execution artifact scanning.

    Contract:
    - totalCandidates: total number of next-check plan candidates
    - executableCandidates: candidates eligible for batch execution (safe, approved, etc.)
    - executedCandidates: candidates with execution artifacts (success, failed, or validation-failure)
    - failedCandidates: executed candidates with failure status (status == "failed")
    - pendingExecutableCandidates: executable candidates without execution artifacts
    - batchExecutionState: canonical state for UI eligibility derivation

    Args:
        run_id: The run ID to compute summary for
        all_plan_data: Pre-scanned plan data dict (run_id -> plan dict)
        all_execution_indices: Pre-scanned execution indices dict with status

    Returns:
        BatchExecutionSummary with all execution state fields
    """
    # SECURITY: Validate run_id for consistency
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        return BatchExecutionSummary(
            totalCandidates=0,
            executableCandidates=0,
            executedCandidates=0,
            failedCandidates=0,
            pendingExecutableCandidates=0,
            batchExecutionState="no-candidates",
        )

    plan_data = all_plan_data.get(validated_run_id)
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

    # Get pre-loaded execution indices with status
    execution_indices = all_execution_indices.get(validated_run_id, {})

    # Count executable and executed candidates using the shared helper
    executable_count = 0
    executed_count = 0
    failed_count = 0
    pending_executable = 0

    for idx, candidate in enumerate(candidates_data):
        is_executable = _is_candidate_batch_executable(candidate)
        is_executed = _is_candidate_executed(idx, execution_indices)

        if is_executable:
            executable_count += 1
            if not is_executed:
                pending_executable += 1

        if is_executed:
            executed_count += 1
            status = execution_indices[idx]
            if status == "failed" or status.endswith("/failed") or "failed" in status.lower():
                failed_count += 1

    # Derive batch execution state
    if total_candidates == 0:
        batch_execution_state: Literal["no-candidates", "not-started", "partially-executed", "fully-executed"] = "no-candidates"
    elif executable_count == 0:
        if executed_count > 0:
            batch_execution_state = "fully-executed"
        else:
            batch_execution_state = "no-candidates"
    elif executed_count == 0:
        batch_execution_state = "not-started"
    elif pending_executable == 0:
        batch_execution_state = "fully-executed"
    else:
        batch_execution_state = "partially-executed"

    return BatchExecutionSummary(
        totalCandidates=total_candidates,
        executableCandidates=executable_count,
        executedCandidates=executed_count,
        failedCandidates=failed_count,
        pendingExecutableCandidates=pending_executable,
        batchExecutionState=batch_execution_state,
    )