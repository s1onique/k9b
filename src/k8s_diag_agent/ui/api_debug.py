"""Debug endpoints for diagnosing execution summary issues in preprod.

This module provides temporary diagnostic tools that are safe for local/admin/debug usage.
It should NOT be deployed publicly without authentication/authorization guards.

These endpoints help debug the "Recent Runs latest-row execution summary lags behind Work list" 
bug by exposing internal index state that cannot be observed from local developer machines.
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def _is_debug_enabled() -> bool:
    """Check if debug endpoints are enabled via environment variable.
    
    Debug endpoints are disabled by default and must be explicitly enabled
    via K9B_ENABLE_DEBUG_ENDPOINTS=true in the environment.
    """
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
    # CRITICAL: Normalize execution indices to handle JSON string keys
    # Without this, string keys like "0", "1" won't match integer candidate indices
    from .api import _normalize_execution_indices_from_index

    all_execution_indices = _normalize_execution_indices_from_index(recent_summary.get("_execution_indices", {}))

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


def get_recent_runs_debug_data(
    run_id: str,
    health_root: Path,
) -> dict[str, Any] | None:
    """Get recent runs debug data for a specific run.

    This is the debug equivalent of fetching the runs list with debug params.
    It collects the data needed for the bundle's recent-runs-debug.json.

    Args:
        run_id: The run ID to fetch debug data for
        health_root: Path to the health directory

    Returns:
        Debug dict with runs list and row data, or None if not enabled
    """
    if not _is_debug_enabled():
        return None

    ui_index_path = health_root / "ui-index.json"
    if not ui_index_path.exists():
        return {"error": "ui-index.json not found", "run_id": run_id}

    try:
        raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"error": "Failed to parse ui-index.json", "run_id": run_id}

    recent_summary = raw_index.get("recent_runs_summary", {})
    runs_list = recent_summary.get("runs", [])

    # Find the target run's row - check both run_id and runId for robustness
    # Recent Runs rows use runId (camelCase) in the serialized output
    target_row = None
    for entry in runs_list:
        if entry.get("run_id") == run_id or entry.get("runId") == run_id:
            target_row = dict(entry)
            break

    return {
        "run_id": run_id,
        "total_runs": len(runs_list),
        "runs_list": runs_list,
        "target_row": target_row,
        "generated_at": recent_summary.get("generated_at"),
        "version": recent_summary.get("version"),
    }


def get_runs_debug_block(
    run_id: str,
    health_root: Path,
) -> dict[str, Any] | None:
    """Get the debug execution summary block for a specific run.

    Args:
        run_id: The run ID to fetch debug block for
        health_root: Path to the health directory

    Returns:
        Debug block dict, or None if not enabled
    """
    if not _is_debug_enabled():
        return None

    diagnostic = build_execution_summary_diagnostics(run_id, health_root, debug_flag=True)
    return diagnostic


def get_worklist_payload(
    run_id: str,
    health_root: Path,
) -> dict[str, Any]:
    """Get worklist/run payload for a specific run.

    This fetches the run's detailed payload from the perspective of
    the Work list / selected run view.

    Args:
        run_id: The run ID to fetch worklist data for
        health_root: Path to the health directory

    Returns:
        Worklist payload dict (may contain error info on partial failure)
    """
    result: dict[str, Any] = {
        "run_id": run_id,
        "run_payload": None,
        "execution_summary": None,
        "errors": [],
    }

    # Load plan data
    external_analysis_dir = health_root / "external-analysis"
    if not external_analysis_dir.is_dir():
        result["errors"].append("external-analysis directory not found")
        return result

    plan_data: dict[str, object] | None = None
    execution_indices: dict[int, str] = {}

    # Find plan artifact
    from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

    try:
        validated_run_id = validate_run_id(run_id)
        plan_glob = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
        for plan_path in external_analysis_dir.glob(plan_glob):
            try:
                raw = json.loads(plan_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-planning":
                    plan_data = raw
                    break
            except (OSError, json.JSONDecodeError):
                continue
    except SecurityError:
        result["errors"].append("Invalid run_id for path validation")
        return result

    if plan_data:
        # Handle both top-level candidates and nested payload.candidates
        # Real next-check-plan artifacts may store candidates in payload.candidates
        # Fall back to top-level candidates if payload doesn't have them
        candidates: list[dict[str, object]] = []
        payload = plan_data.get("payload", {})
        if isinstance(payload, dict):
            # Check if candidates exists and is non-empty
            payload_candidates = payload.get("candidates")
            if isinstance(payload_candidates, list) and len(payload_candidates) > 0:
                candidates = payload_candidates
            else:
                # Fall back to top-level candidates
                top_candidates = plan_data.get("candidates")
                if isinstance(top_candidates, list) and len(top_candidates) > 0:
                    candidates = top_candidates
        else:
            # No payload, use top-level candidates
            top_candidates = plan_data.get("candidates")
            if isinstance(top_candidates, list) and len(top_candidates) > 0:
                candidates = top_candidates
        result["run_payload"] = {
            "purpose": plan_data.get("purpose"),
            "run_id": plan_data.get("run_id"),
            "timestamp": plan_data.get("timestamp"),
            "candidate_count": len(candidates),
        }
    else:
        result["errors"].append("No plan artifact found")

    # Find execution artifacts
    try:
        validated_run_id = validate_run_id(run_id)
        exec_glob = safe_run_artifact_glob(validated_run_id, "-next-check-execution*.json")
        for exec_path in external_analysis_dir.glob(exec_glob):
            try:
                raw = json.loads(exec_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-execution":
                    # Execution artifacts use root-level status, not payload.status
                    payload = raw.get("payload", {})
                    candidate_index = payload.get("candidateIndex")
                    # Read status from root-level with fallback to "unknown"
                    status = raw.get("status", "unknown")
                    if isinstance(candidate_index, int):
                        execution_indices[candidate_index] = str(status)
            except (OSError, json.JSONDecodeError):
                continue
    except SecurityError:
        result["errors"].append("Failed to glob execution artifacts")
        pass

    # Compute execution summary
    if plan_data:
        from .api import _compute_execution_summary_indexed

        exec_summary = _compute_execution_summary_indexed(plan_data, execution_indices)
        result["execution_summary"] = {
            "totalCandidates": exec_summary["totalCandidates"],
            "executableCandidates": exec_summary["executableCandidates"],
            "executedCandidates": exec_summary["executedCandidates"],
            "failedCandidates": exec_summary["failedCandidates"],
            "pendingExecutableCandidates": exec_summary["pendingExecutableCandidates"],
            "batchExecutionState": exec_summary["batchExecutionState"],
        }

    return result


def build_execution_state_bundle(
    run_id: str,
    health_root: Path,
) -> bytes | None:
    """Build a ZIP bundle containing execution state diagnostics.

    This creates a diagnostic bundle that can be downloaded from the UI
    to help debug execution summary issues.

    Bundle contents:
    - summary.md: Markdown summary with root-cause hints
    - recent-runs-debug.json: Recent runs debug data
    - recent-runs-row.json: Target run's row from Recent Runs
    - runs-debug-block.json: Debug execution summary block
    - execution-summary-diagnostics.json: Detailed diagnostic info
    - worklist-run-payload.json: Worklist/run payload

    Args:
        run_id: The run ID to bundle diagnostics for
        health_root: Path to the health directory

    Returns:
        ZIP bundle bytes, or None if debug endpoints are disabled
    """
    if not _is_debug_enabled():
        return None

    bundle_errors: list[str] = []

    # Collect all diagnostic data
    execution_summary_diagnostics = build_execution_summary_diagnostics(run_id, health_root, debug_flag=True)
    recent_runs_debug = get_recent_runs_debug_data(run_id, health_root)
    runs_debug_block = get_runs_debug_block(run_id, health_root)
    worklist_payload = get_worklist_payload(run_id, health_root)

    if execution_summary_diagnostics:
        bundle_errors.extend([
            f"execution_summary: {execution_summary_diagnostics.get('reason_execution_summary_missing', 'unknown')}"
        ])
    if not recent_runs_debug:
        bundle_errors.append("recent_runs_debug: not available")
    if not runs_debug_block:
        bundle_errors.append("runs_debug_block: not available")

    # Build summary.md content
    now_iso = datetime.now(UTC).isoformat()
    summary_lines = [
        "# k9b Execution State Diagnostics",
        "",
        f"**Run ID:** {run_id}",
        f"**Generated:** {now_iso}",
        "",
        "## Bundle Contents",
        "",
        "- `summary.md` - This file",
        "- `recent-runs-debug.json` - Recent runs debug data with runs list",
        "- `recent-runs-row.json` - Target run's row from Recent Runs table",
        "- `runs-debug-block.json` - Debug execution summary block",
        "- `execution-summary-diagnostics.json` - Detailed diagnostic analysis",
        "- `worklist-run-payload.json` - Worklist/run payload from plan artifacts",
        "",
        "## Quick Checks",
        "",
    ]

    # Add root-cause hints based on diagnostic data
    if execution_summary_diagnostics:
        reason = execution_summary_diagnostics.get("reason_execution_summary_missing")
        stale = execution_summary_diagnostics.get("stale_index_detected")
        plan_in_index = execution_summary_diagnostics.get("plan_data_in_index")
        exec_in_index = execution_summary_diagnostics.get("execution_indices_in_index")

        summary_lines.append("### Diagnostic Findings")
        summary_lines.append("")

        if reason:
            summary_lines.append(f"**Reason:** {reason}")
            summary_lines.append("")

        if stale:
            summary_lines.append("⚠️ **Stale Index Detected:** UI index may be out of date")
            summary_lines.append("")
            summary_lines.append("Fix: Rebuild the UI index:")
            summary_lines.append("```bash")
            summary_lines.append(".venv/bin/python scripts/update_ui_index.py --runs-dir runs/health")
            summary_lines.append("```")
            summary_lines.append("")

        if plan_in_index is False:
            summary_lines.append("⚠️ **Plan Data Missing:** Next-check plan not in UI index")
            summary_lines.append("")

        if exec_in_index is False:
            summary_lines.append("⚠️ **Execution Indices Missing:** Execution artifacts not indexed")
            summary_lines.append("")

        # Show execution summary if available
        computed = execution_summary_diagnostics.get("computed_execution_summary")
        if computed:
            summary_lines.append("### Computed Execution Summary")
            summary_lines.append("")
            summary_lines.append(f"- Total Candidates: {computed.get('totalCandidates', 'N/A')}")
            summary_lines.append(f"- Executable Candidates: {computed.get('executableCandidates', 'N/A')}")
            summary_lines.append(f"- Executed Candidates: {computed.get('executedCandidates', 'N/A')}")
            summary_lines.append(f"- Failed Candidates: {computed.get('failedCandidates', 'N/A')}")
            summary_lines.append(f"- Pending Executable: {computed.get('pendingExecutableCandidates', 'N/A')}")
            summary_lines.append(f"- Batch State: {computed.get('batchExecutionState', 'N/A')}")
            summary_lines.append("")

    # Add error summary if any
    if bundle_errors:
        summary_lines.append("### Bundle Collection Errors")
        summary_lines.append("")
        for err in bundle_errors:
            summary_lines.append(f"- {err}")
        summary_lines.append("")

    # Add timestamp info
    if execution_summary_diagnostics:
        ts = execution_summary_diagnostics.get("timestamp")
        if ts:
            summary_lines.append(f"**Run Timestamp:** {ts}")
            summary_lines.append("")

    summary_lines.append("---")
    summary_lines.append("*This bundle was generated by k9b debug diagnostics*")

    summary_content = "\n".join(summary_lines)

    # Build the ZIP bundle
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add summary.md
        zf.writestr("summary.md", summary_content)

        # Add recent-runs-debug.json
        if recent_runs_debug:
            zf.writestr("recent-runs-debug.json", json.dumps(recent_runs_debug, indent=2, ensure_ascii=False))
        else:
            zf.writestr("recent-runs-debug.json", json.dumps({"error": "not available", "run_id": run_id}))

        # Add recent-runs-row.json
        if recent_runs_debug and recent_runs_debug.get("target_row"):
            zf.writestr("recent-runs-row.json", json.dumps(recent_runs_debug["target_row"], indent=2, ensure_ascii=False))
        else:
            zf.writestr("recent-runs-row.json", json.dumps({"error": "run not found in recent runs", "run_id": run_id}))

        # Add runs-debug-block.json
        if runs_debug_block:
            zf.writestr("runs-debug-block.json", json.dumps(runs_debug_block, indent=2, ensure_ascii=False))
        else:
            zf.writestr("runs-debug-block.json", json.dumps({"error": "not available", "run_id": run_id}))

        # Add execution-summary-diagnostics.json
        if execution_summary_diagnostics:
            zf.writestr("execution-summary-diagnostics.json", json.dumps(execution_summary_diagnostics, indent=2, ensure_ascii=False))
        else:
            zf.writestr("execution-summary-diagnostics.json", json.dumps({"error": "not available", "run_id": run_id}))

        # Add worklist-run-payload.json
        zf.writestr("worklist-run-payload.json", json.dumps(worklist_payload, indent=2, ensure_ascii=False))

    buffer.seek(0)
    return buffer.read()


def is_debug_diagnostics_enabled() -> bool:
    """Check if debug diagnostics are enabled.

    This is used by the frontend to determine whether to show
    the download diagnostics button.

    Returns:
        True if debug diagnostics are enabled (K9B_ENABLE_DEBUG_ENDPOINTS=true)
    """
    return _is_debug_enabled()
