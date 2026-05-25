"""Approval freshness helpers for planner queue.

This module contains helpers for tracking approval staleness and matching
plan paths between planner artifacts and approval records.
"""

from __future__ import annotations

from ...structured_logging import emit_structured_log

__all__ = [
    "_log_next_check_approval_freshness",
    "_plan_paths_match",
]


def _plan_paths_match(plan_path: str | None, approval_path: str | None) -> bool:
    """Check if approval plan path matches the current plan path."""
    if not plan_path or not approval_path:
        return False
    return plan_path == approval_path


def _log_next_check_approval_freshness(
    run_label: str | None,
    run_id: str,
    candidate_id: str | None,
    candidate_index: int | None,
    plan_artifact_path: str | None,
    approval_plan_path: str | None,
    candidate_description: str | None,
    status: str,
) -> None:
    """Log when an approval's plan path doesn't match the current plan."""
    if status != "approval-stale":
        return
    emit_structured_log(
        "next_check_approval_stale",
        message="Next check approval is stale",
        run_id=run_id,
        run_label=run_label or "",
        candidate_id=candidate_id,
        candidate_index=candidate_index,
        plan_artifact_path=plan_artifact_path,
        approval_plan_path=approval_plan_path,
        candidate_description=candidate_description,
    )
