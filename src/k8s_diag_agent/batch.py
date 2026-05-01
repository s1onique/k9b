"""Batch execution of eligible next-check candidates.

This module provides the core batch execution logic that can be used by:
- The UI server API endpoint
- The command-line script

The module executes all currently eligible next-check candidates that are:
- safe (safeToAutomate=true)
- runnable (valid command family, has description, has context)
- not yet executed in this run

The flow:
1. Loads the next_check_plan from the specified run
2. Collects already-executed candidate indices from existing execution artifacts
3. Filters candidates to find eligible ones
4. Executes each eligible candidate using the existing manual_next_check flow
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .external_analysis.artifact import (
    ExternalAnalysisPurpose,
)
from .external_analysis.manual_next_check import (
    ManualNextCheckError,
    execute_manual_next_check,
)
from .security.path_validation import SecurityError, validate_run_id
from .structured_logging import emit_structured_log

COMPONENT_NAME = "batch-next-check-runner"


class BatchExecutionResult:
    """Results from batch execution.

    Attributes:
        total_candidates: Total number of candidates in the plan
        eligible_candidates: Number of candidates eligible for execution
        executed_count: Number of candidates actually executed
        skipped_already_executed: Number of candidates skipped because already executed
        skipped_ineligible: Number of candidates skipped due to ineligibility
        failed_count: Number of candidates that failed during execution
        success_count: Number of successful executions (executed_count - failed_count)
    """

    def __init__(
        self,
        total_candidates: int,
        eligible_candidates: int,
        executed_count: int,
        skipped_already_executed: int,
        skipped_ineligible: int,
        failed_count: int,
    ):
        self.total_candidates = total_candidates
        self.eligible_candidates = eligible_candidates
        self.executed_count = executed_count
        self.skipped_already_executed = skipped_already_executed
        self.skipped_ineligible = skipped_ineligible
        self.failed_count = failed_count

    @property
    def success_count(self) -> int:
        """Number of successful executions."""
        return self.executed_count - self.failed_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "eligible_candidates": self.eligible_candidates,
            "executed_count": self.executed_count,
            "skipped_already_executed": self.skipped_already_executed,
            "skipped_ineligible": self.skipped_ineligible,
            "failed_count": self.failed_count,
            "success_count": self.success_count,
        }


def _log_event(
    *,
    message: str,
    severity: str = "INFO",
    run_label: str,
    run_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a structured log event."""
    emit_structured_log(
        component=COMPONENT_NAME,
        message=message,
        severity=severity,
        run_label=run_label,
        run_id=run_id,
        metadata=metadata or {},
    )


def load_ui_index(runs_dir: Path) -> dict[str, Any]:
    """Load the UI index for a run.

    Args:
        runs_dir: Path to the runs directory

    Returns:
        The parsed UI index data

    Raises:
        FileNotFoundError: If the UI index doesn't exist
    """
    run_health_dir = runs_dir / "health"
    ui_index_path = run_health_dir / "ui-index.json"
    if not ui_index_path.exists():
        raise FileNotFoundError(f"UI index not found: {ui_index_path}")
    return cast(dict[str, Any], json.loads(ui_index_path.read_text(encoding="utf-8")))


def find_next_check_plan(index_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract next_check_plan from UI index.

    Args:
        index_data: The parsed UI index data

    Returns:
        The next_check_plan dict or None if not found
    """
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    plan = run_entry.get("next_check_plan")
    if isinstance(plan, dict):
        return plan
    return None


def load_existing_execution_indices(run_health_dir: Path, run_id: str) -> set[int]:
    """Load indices of already-executed next-check candidates.

    Args:
        run_health_dir: Path to the run's health directory
        run_id: The run ID

    Returns:
        Set of candidate indices that have already been executed
    """
    # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return set()

    execution_indices: set[int] = set()
    external_dir = run_health_dir / "external-analysis"
    if not external_dir.exists():
        return execution_indices

    for artifact_path in external_dir.glob(f"{validated_run_id}-next-check-execution-*.json"):  # REVIEWED: safe
        try:
            artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
            # Check if this is a next-check-execution artifact
            purpose = artifact_data.get("purpose")
            if purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION.value:
                payload = cast(dict[str, Any], artifact_data.get("payload") or {})
                candidate_index = payload.get("candidateIndex")
                if isinstance(candidate_index, int):
                    execution_indices.add(candidate_index)
        except (json.JSONDecodeError, KeyError, TypeError):
            # Skip malformed artifacts
            continue

    return execution_indices


def is_candidate_eligible(
    candidate: dict[str, Any],
    execution_indices: set[int],
    candidate_index: int,
) -> tuple[bool, str | None]:
    """Check if a candidate is eligible for batch execution.

    Args:
        candidate: The candidate dictionary
        execution_indices: Set of already-executed candidate indices
        candidate_index: The candidate's index in the plan

    Returns:
        Tuple of (is_eligible, reason_if_ineligible)
    """
    # Already executed?
    if candidate_index in execution_indices:
        return False, "already_executed"

    # Must be safe to automate
    if not candidate.get("safeToAutomate"):
        return False, "not_safe_to_automate"

    # Must have a valid command family
    family = candidate.get("suggestedCommandFamily")
    if not family or not isinstance(family, str):
        return False, "missing_command_family"

    # Must have a description
    description = candidate.get("description")
    if not description or not isinstance(description, str):
        return False, "missing_description"

    # Must have target context info
    target_context = candidate.get("targetContext")
    if not target_context or not isinstance(target_context, str):
        return False, "missing_target_context"

    # Check approval requirement
    requires_approval = candidate.get("requiresOperatorApproval")
    if requires_approval:
        approval_status = str(candidate.get("approvalStatus") or "").lower()
        if approval_status != "approved":
            return False, "requires_approval"

    # Check for duplicates
    if candidate.get("duplicateOfExistingEvidence"):
        return False, "duplicate_of_existing_evidence"

    return True, None


def collect_candidates(
    plan: dict[str, Any],
) -> list[tuple[int, dict[str, Any]]]:
    """Collect all candidates from the next_check_plan.

    Args:
        plan: The next_check_plan dictionary

    Returns:
        List of (candidate_index, candidate_dict) tuples
    """
    candidates: list[tuple[int, dict[str, Any]]] = []

    # Plan may have candidates directly
    plan_candidates = plan.get("candidates")
    if isinstance(plan_candidates, list):
        for idx, candidate in enumerate(plan_candidates):
            if isinstance(candidate, dict):
                candidates.append((idx, candidate))

    # Also check payload.candidates
    payload = plan.get("payload") or {}
    payload_candidates = payload.get("candidates")
    if isinstance(payload_candidates, list):
        for idx, candidate in enumerate(payload_candidates):
            if isinstance(candidate, dict):
                # Use idx if not already in list, or merge
                if not any(c[0] == idx for c in candidates):
                    candidates.append((idx, candidate))

    return candidates


def get_target_cluster(candidate: dict[str, Any], run_label: str) -> str:
    """Extract target cluster from candidate.

    Args:
        candidate: The candidate dictionary
        run_label: Fallback run label

    Returns:
        The target cluster name
    """
    cluster = candidate.get("targetCluster")
    if isinstance(cluster, str) and cluster:
        return cluster
    return run_label


def run_batch_next_checks(
    runs_dir: Path,
    run_id: str,
    *,
    dry_run: bool = False,
) -> BatchExecutionResult:
    """Execute all eligible next-check candidates for a run.

    Args:
        runs_dir: Path to the runs directory
        run_id: The run ID to operate on
        dry_run: If True, only report what would be executed

    Returns:
        BatchExecutionResult with execution statistics

    Raises:
        FileNotFoundError: If the run's UI index doesn't exist
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Load UI index
    index_data = load_ui_index(runs_dir)
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    run_label = str(run_entry.get("run_label") or run_id)

    _log_event(
        message=f"Starting batch next-check execution for run {run_id}",
        run_label=run_label,
        run_id=run_id,
        metadata={"run_id": run_id, "run_label": run_label, "dry_run": dry_run},
    )

    # Find next_check_plan
    plan = find_next_check_plan(index_data)
    if not plan:
        _log_event(
            message=f"No next_check_plan found for run {run_id}",
            severity="WARNING",
            run_label=run_label,
            run_id=run_id,
        )
        return BatchExecutionResult(
            total_candidates=0,
            eligible_candidates=0,
            executed_count=0,
            skipped_already_executed=0,
            skipped_ineligible=0,
            failed_count=0,
        )

    # Get plan artifact path
    plan_artifact_path_str = plan.get("artifact_path")
    if isinstance(plan_artifact_path_str, str):
        plan_artifact_path = Path(plan_artifact_path_str)
    else:
        # Construct path
        plan_artifact_path = run_health_dir / "external-analysis" / f"{run_id}-next-check-plan.json"

    # Collect already-executed indices
    execution_indices = load_existing_execution_indices(run_health_dir, run_id)

    # Get all candidates
    all_candidates = collect_candidates(plan)
    total_candidates = len(all_candidates)

    _log_event(
        message=f"Found {total_candidates} total candidates, {len(execution_indices)} already executed",
        run_label=run_label,
        run_id=run_id,
        metadata={
            "total_candidates": total_candidates,
            "already_executed_count": len(execution_indices),
        },
    )

    # Track stats
    executed_count = 0
    skipped_already_executed = 0
    skipped_ineligible = 0
    failed_count = 0
    eligible_candidates = 0

    # Process each candidate
    for candidate_index, candidate in all_candidates:
        is_eligible, ineligibility_reason = is_candidate_eligible(
            candidate, execution_indices, candidate_index
        )

        if not is_eligible:
            if ineligibility_reason == "already_executed":
                skipped_already_executed += 1
            else:
                skipped_ineligible += 1
                _log_event(
                    message=f"Skipping candidate {candidate_index}: {ineligibility_reason}",
                    severity="INFO",
                    run_label=run_label,
                    run_id=run_id,
                    metadata={
                        "candidate_index": candidate_index,
                        "ineligibility_reason": ineligibility_reason,
                        "candidate_description": candidate.get("description"),
                    },
                )
            continue

        eligible_candidates += 1

        if dry_run:
            executed_count += 1
            _log_event(
                message=f"Would execute candidate {candidate_index}: {candidate.get('description')}",
                severity="INFO",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "candidate_description": candidate.get("description"),
                },
            )
            continue

        # Execute the candidate
        target_cluster = get_target_cluster(candidate, run_label)
        target_context = candidate.get("targetContext")

        try:
            execute_manual_next_check(
                health_root=run_health_dir,
                run_id=run_id,
                run_label=run_label,
                plan_artifact_path=plan_artifact_path,
                candidate_index=candidate_index,
                candidate=candidate,
                target_context=target_context or "",
                target_cluster=target_cluster,
            )
            executed_count += 1
            _log_event(
                message=f"Executed candidate {candidate_index}: {candidate.get('description')}",
                severity="INFO",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "candidate_description": candidate.get("description"),
                    "target_cluster": target_cluster,
                },
            )
        except ManualNextCheckError as exc:
            failed_count += 1
            _log_event(
                message=f"Failed to execute candidate {candidate_index}: {exc}",
                severity="WARNING",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "candidate_description": candidate.get("description"),
                    "target_cluster": target_cluster,
                    "error": str(exc),
                },
            )
        except Exception as exc:
            failed_count += 1
            _log_event(
                message=f"Unexpected error executing candidate {candidate_index}: {exc}",
                severity="ERROR",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "candidate_description": candidate.get("description"),
                    "target_cluster": target_cluster,
                    "error": str(exc),
                },
            )

    _log_event(
        message=f"Batch execution completed for run {run_id}: "
        f"executed={executed_count}, failed={failed_count}, "
        f"skipped_executed={skipped_already_executed}, "
        f"skipped_ineligible={skipped_ineligible}",
        run_label=run_label,
        run_id=run_id,
        metadata={
            "executed_count": executed_count,
            "failed_count": failed_count,
            "skipped_already_executed": skipped_already_executed,
            "skipped_ineligible": skipped_ineligible,
        },
    )

    return BatchExecutionResult(
        total_candidates=total_candidates,
        eligible_candidates=eligible_candidates,
        executed_count=executed_count,
        skipped_already_executed=skipped_already_executed,
        skipped_ineligible=skipped_ineligible,
        failed_count=failed_count,
    )