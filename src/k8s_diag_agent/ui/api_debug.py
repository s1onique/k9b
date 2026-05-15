"""Debug endpoints for diagnosing execution summary issues in preprod.

This module provides temporary diagnostic tools that are safe for local/admin/debug usage.
It should NOT be deployed publicly without authentication/authorization guards.

These endpoints help debug the "Recent Runs latest-row execution summary lags behind Work list" 
bug by exposing internal index state that cannot be observed from local developer machines.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def _is_debug_enabled() -> bool:
    """Check if debug endpoints are enabled via environment variable.
    
    Debug endpoints are disabled by default and must be explicitly enabled
    via K9B_ENABLE_DEBUG_ENDPOINTS=true in the environment.
    """
    import os
    return os.environ.get("K9B_ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true"


def build_execution_summary_diagnostics(
    run_id: str,
    health_root: Path,
    *,
    debug_flag: bool = False,
) -> dict[str, Any] | None:
    """Build diagnostic output for execution summary computation.

    This function diagnoses why a specific run's execution summary might be missing
    or stale in the Recent Runs API. It examines the index state and execution artifacts
    to identify the root cause.

    Args:
        run_id: The run ID to diagnose
        health_root: Path to the health directory
        debug_flag: Must be True AND K9B_ENABLE_DEBUG_ENDPOINTS=true to enable

    Returns:
        Diagnostic dict with detailed state, or None if disabled
    """
    if not debug_flag or not _is_debug_enabled():
        return None

    diagnostic: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": None,
        "selected_source": None,
        "ui_index_generated_at": None,
        "ui_index_mtime": None,
        "newest_plan_artifact_mtime": None,
        "newest_execution_artifact_mtime": None,
        "plan_candidate_count": 0,
        "parsed_execution_indices_count": 0,
        "execution_statuses_by_candidate_index": {},
        "computed_execution_summary": None,
        "batchExecutable": False,
        "batchEligibleCount": 0,
        "stale_index_detected": False,
        "reason_execution_summary_missing": None,
        "plan_data_in_index": False,
        "execution_indices_in_index": False,
        "index_path": None,
    }

    ui_index_path = health_root / "ui-index.json"
    diagnostic["index_path"] = str(ui_index_path)

    # Load ui-index.json to check internal state
    if not ui_index_path.exists():
        diagnostic["reason_execution_summary_missing"] = "ui_index_missing"
        return diagnostic

    try:
        index_mtime = ui_index_path.stat().st_mtime
        diagnostic["ui_index_mtime"] = index_mtime
    except OSError:
        pass

    try:
        raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        diagnostic["reason_execution_summary_missing"] = f"index_parse_error:{exc}"
        return diagnostic

    recent_summary = raw_index.get("recent_runs_summary")
    if not isinstance(recent_summary, dict):
        diagnostic["reason_execution_summary_missing"] = "missing_recent_runs_summary"
        return diagnostic

    diagnostic["ui_index_generated_at"] = recent_summary.get("generated_at")

    # Check internal data in index
    all_plan_data = recent_summary.get("_plan_data", {})
    all_execution_indices = recent_summary.get("_execution_indices", {})

    diagnostic["plan_data_in_index"] = run_id in all_plan_data
    diagnostic["execution_indices_in_index"] = run_id in all_execution_indices

    # Find the run in the runs list
    runs_list = recent_summary.get("runs", [])
    run_entry = None
    for entry in runs_list:
        if entry.get("run_id") == run_id:
            run_entry = entry
            break

    if not run_entry:
        diagnostic["reason_execution_summary_missing"] = "run_not_in_index_runs_list"
        return diagnostic

    diagnostic["timestamp"] = run_entry.get("timestamp")
    diagnostic["batchExecutable"] = run_entry.get("batchExecutable", False)
    diagnostic["batchEligibleCount"] = run_entry.get("batchEligibleCount", 0)

    # Determine selected source
    if run_id in all_plan_data:
        diagnostic["selected_source"] = "index-backed"
    else:
        diagnostic["selected_source"] = "fresh_fallback"

    # Get plan data for candidate count
    plan_data = all_plan_data.get(run_id)
    if plan_data:
        candidates_data: list[dict[str, object]] = []
        if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
            candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
        elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
            payload = cast(dict[str, object], plan_data["payload"])
            if "candidates" in payload and isinstance(payload["candidates"], list):
                candidates_data = cast(list[dict[str, object]], payload["candidates"])
        diagnostic["plan_candidate_count"] = len(candidates_data)

    # Get execution indices for status counts
    exec_indices = all_execution_indices.get(run_id, {})
    diagnostic["parsed_execution_indices_count"] = len(exec_indices)
    diagnostic["execution_statuses_by_candidate_index"] = dict(exec_indices)

    # Check for newest plan artifact mtime
    external_analysis_dir = health_root / "external-analysis"
    if external_analysis_dir.is_dir():
        # SECURITY: Use safe_run_artifact_glob for path validation
        from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

        try:
            validated_run_id = validate_run_id(run_id)
            plan_glob = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
            plan_files = list(external_analysis_dir.glob(plan_glob))
            if plan_files:
                newest_plan_mtime = max(f.stat().st_mtime for f in plan_files if f.exists())
                diagnostic["newest_plan_artifact_mtime"] = newest_plan_mtime
        except SecurityError:
            pass

        try:
            exec_glob = safe_run_artifact_glob(validated_run_id, "-next-check-execution*.json")
            exec_files = list(external_analysis_dir.glob(exec_glob))
            if exec_files:
                newest_exec_mtime = max(f.stat().st_mtime for f in exec_files if f.exists())
                diagnostic["newest_execution_artifact_mtime"] = newest_exec_mtime
        except SecurityError:
            pass

    # Compute execution summary if we have plan data
    if run_id in all_plan_data and plan_data:
        from .api import _compute_execution_summary_indexed

        execution_summary = _compute_execution_summary_indexed(plan_data, exec_indices)
        diagnostic["computed_execution_summary"] = {
            "totalCandidates": execution_summary["totalCandidates"],
            "executableCandidates": execution_summary["executableCandidates"],
            "executedCandidates": execution_summary["executedCandidates"],
            "failedCandidates": execution_summary["failedCandidates"],
            "pendingExecutableCandidates": execution_summary["pendingExecutableCandidates"],
            "batchExecutionState": execution_summary["batchExecutionState"],
        }

        # Check for stale index: execution artifacts newer than ui-index
        if diagnostic["newest_execution_artifact_mtime"] and diagnostic["ui_index_mtime"]:
            if diagnostic["newest_execution_artifact_mtime"] > diagnostic["ui_index_mtime"]:
                diagnostic["stale_index_detected"] = True

        # If execution summary shows pending but batchExecutable is True, that's a mismatch
        if diagnostic["computed_execution_summary"]["pendingExecutableCandidates"] == 0 and diagnostic["batchExecutable"]:
            diagnostic["reason_execution_summary_missing"] = "batchExecutable_but_no_pending"
    else:
        diagnostic["reason_execution_summary_missing"] = "run_id_not_in_all_plan_data"

    return diagnostic
