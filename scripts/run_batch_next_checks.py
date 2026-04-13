#!/usr/bin/env python3
"""Batch execution of eligible next-check candidates.

This script executes all currently eligible next-check candidates that are:
- safe (safeToAutomate=true)
- runnable (valid command family, has description, has context)
- not yet executed in this run

The flow:
1. Loads the next_check_plan from the latest health run
2. Collects already-executed candidate indices from existing execution artifacts
3. Filters candidates to find eligible ones
4. Executes each eligible candidate using the existing manual_next_check flow
5. Refreshes the diagnostic pack mirror

Usage:
    python scripts/run_batch_next_checks.py --run-id <run_id> [--runs-dir <path>]
    python scripts/run_batch_next_checks.py --latest [--runs-dir <path>]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from k8s_diag_agent.external_analysis.artifact import (  # noqa: E402
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    write_external_analysis_artifact,
)
from k8s_diag_agent.external_analysis.manual_next_check import (  # noqa: E402
    ManualNextCheckError,
    execute_manual_next_check,
)
from k8s_diag_agent.structured_logging import emit_structured_log

COMPONENT_NAME = "batch-next-check-runner"


class BatchExecutionResult:
    """Results from batch execution."""

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "eligible_candidates": self.eligible_candidates,
            "executed_count": self.executed_count,
            "skipped_already_executed": self.skipped_already_executed,
            "skipped_ineligible": self.skipped_ineligible,
            "failed_count": self.failed_count,
            "success_count": self.executed_count - self.failed_count,
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


def _load_ui_index(runs_dir: Path) -> dict[str, Any]:
    """Load the UI index for the latest run."""
    run_health_dir = runs_dir / "health"
    ui_index_path = run_health_dir / "ui-index.json"
    if not ui_index_path.exists():
        raise FileNotFoundError(f"UI index not found: {ui_index_path}")
    return cast(dict[str, Any], json.loads(ui_index_path.read_text(encoding="utf-8")))


def _find_next_check_plan(index_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract next_check_plan from UI index."""
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    plan = run_entry.get("next_check_plan")
    if isinstance(plan, dict):
        return plan
    return None


def _load_existing_execution_indices(run_health_dir: Path, run_id: str) -> set[int]:
    """Load indices of already-executed next-check candidates."""
    execution_indices: set[int] = set()
    external_dir = run_health_dir / "external-analysis"
    if not external_dir.exists():
        return execution_indices

    for artifact_path in external_dir.glob(f"{run_id}-next-check-execution-*.json"):
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


def _is_candidate_eligible(
    candidate: dict[str, Any],
    execution_indices: set[int],
    candidate_index: int,
) -> tuple[bool, str | None]:
    """Check if a candidate is eligible for batch execution.

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


def _collect_candidates(
    plan: dict[str, Any],
) -> list[tuple[int, dict[str, Any]]]:
    """Collect all candidates from the next_check_plan.

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


def _get_target_cluster(candidate: dict[str, Any], run_label: str) -> str:
    """Extract target cluster from candidate."""
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
    """
    runs_dir = runs_dir.expanduser().resolve()
    run_health_dir = runs_dir / "health"

    # Load UI index
    index_data = _load_ui_index(runs_dir)
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    run_label = str(run_entry.get("run_label") or run_id)

    _log_event(
        message=f"Starting batch next-check execution for run {run_id}",
        run_label=run_label,
        run_id=run_id,
        metadata={"run_id": run_id, "run_label": run_label, "dry_run": dry_run},
    )

    # Find next_check_plan
    plan = _find_next_check_plan(index_data)
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
    execution_indices = _load_existing_execution_indices(run_health_dir, run_id)

    # Get all candidates
    all_candidates = _collect_candidates(plan)
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

    # Process each candidate
    for candidate_index, candidate in all_candidates:
        is_eligible, ineligibility_reason = _is_candidate_eligible(
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

        # Eligible - execute it
        description = str(candidate.get("description") or "")
        target_context = str(candidate.get("targetContext") or "")
        target_cluster = _get_target_cluster(candidate, run_label)

        _log_event(
            message=f"Executing candidate {candidate_index}: {description[:80]}",
            run_label=run_label,
            run_id=run_id,
            metadata={
                "candidate_index": candidate_index,
                "candidate_description": description,
                "target_context": target_context,
                "target_cluster": target_cluster,
            },
        )

        if dry_run:
            executed_count += 1
            continue

        try:
            artifact = execute_manual_next_check(
                runs_dir=runs_dir,
                run_id=run_id,
                run_label=run_label,
                plan_artifact_path=plan_artifact_path,
                candidate_index=candidate_index,
                candidate=candidate,
                target_context=target_context,
                target_cluster=target_cluster,
            )
            executed_count += 1
            _log_event(
                message=f"Executed candidate {candidate_index}: {artifact.status.value}",
                severity="INFO" if artifact.status.value == "success" else "WARNING",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "status": artifact.status.value,
                    "artifact_path": artifact.artifact_path,
                },
            )
        except ManualNextCheckError as exc:
            failed_count += 1
            _log_event(
                message=f"Failed to execute candidate {candidate_index}: {exc}",
                severity="ERROR",
                run_label=run_label,
                run_id=run_id,
                metadata={
                    "candidate_index": candidate_index,
                    "blocking_reason": exc.blocking_reason.value if exc.blocking_reason else None,
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
                    "error": str(exc),
                },
            )

    # Refresh diagnostic pack
    if executed_count > 0 and not dry_run:
        _refresh_diagnostic_pack(runs_dir, run_id, run_label)

    result = BatchExecutionResult(
        total_candidates=total_candidates,
        eligible_candidates=total_candidates - skipped_already_executed - skipped_ineligible,
        executed_count=executed_count,
        skipped_already_executed=skipped_already_executed,
        skipped_ineligible=skipped_ineligible,
        failed_count=failed_count,
    )

    _log_event(
        message=f"Batch execution complete: {executed_count - failed_count} succeeded, {failed_count} failed",
        severity="INFO" if failed_count == 0 else "WARNING",
        run_label=run_label,
        run_id=run_id,
        metadata=result.to_dict(),
    )

    return result


def _refresh_diagnostic_pack(runs_dir: Path, run_id: str, run_label: str) -> bool:
    """Refresh the diagnostic pack mirror."""
    try:
        # Import here to avoid circular imports
        from scripts.build_diagnostic_pack import create_diagnostic_pack  # noqa: E402

        _log_event(
            message="Refreshing diagnostic pack",
            run_label=run_label,
            run_id=run_id,
        )

        pack_path = create_diagnostic_pack(run_id, runs_dir)
        _log_event(
            message=f"Diagnostic pack refreshed: {pack_path}",
            run_label=run_label,
            run_id=run_id,
            metadata={"pack_path": str(pack_path)},
        )
        return True
    except Exception as exc:
        _log_event(
            message=f"Failed to refresh diagnostic pack: {exc}",
            severity="ERROR",
            run_label=run_label,
            run_id=run_id,
            metadata={"error": str(exc)},
        )
        return False


def _find_latest_run_id(runs_dir: Path) -> str:
    """Find the most recent run ID from the health directory."""
    run_health_dir = runs_dir / "health"
    ui_index_path = run_health_dir / "ui-index.json"
    if not ui_index_path.exists():
        raise FileNotFoundError(f"UI index not found: {ui_index_path}")
    index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    run_entry = cast(dict[str, Any], index_data.get("run") or {})
    run_id = run_entry.get("run_id")
    if not isinstance(run_id, str):
        raise ValueError(f"Could not find run_id in UI index")
    return run_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch execute eligible next-check candidates."
    )
    parser.add_argument(
        "--run-id",
        help="Specific run ID to operate on",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Use the latest run",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Path to runs directory (default: runs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be executed, don't actually run",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    runs_dir = Path(args.runs_dir)

    # Determine run_id
    if args.run_id:
        run_id = args.run_id
    elif args.latest:
        run_id = _find_latest_run_id(runs_dir)
        print(f"Using latest run: {run_id}")
    else:
        print("Error: Must specify either --run-id or --latest", file=sys.stderr)
        sys.exit(1)

    try:
        result = run_batch_next_checks(
            runs_dir=runs_dir,
            run_id=run_id,
            dry_run=args.dry_run,
        )

        print(f"\nBatch Execution Summary:")
        print(f"  Total candidates: {result.total_candidates}")
        print(f"  Eligible candidates: {result.eligible_candidates}")
        print(f"  Executed: {result.executed_count}")
        print(f"  Skipped (already executed): {result.skipped_already_executed}")
        print(f"  Skipped (ineligible): {result.skipped_ineligible}")
        print(f"  Failed: {result.failed_count}")
        print(f"  Succeeded: {result.executed_count - result.failed_count}")

        if result.failed_count > 0:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()