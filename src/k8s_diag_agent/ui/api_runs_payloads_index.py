"""Index-backed runs-list fast paths for the operator UI.

This module contains the index-backed fast paths for runs-list payload construction.
It handles reading from pre-computed ui-index.json without filesystem scanning.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

# Use the original logger name for compatibility
import logging
import time
from pathlib import Path
from typing import Literal, cast

from ..datetime_utils import parse_iso_to_utc
from ._batch_execution_state import (
    _is_candidate_batch_executable,
)
from .api_payloads import (
    BatchExecutionSummary,
    RunsListEntry,
    RunsListPayload,
    RunsListTimings,
)

logger = logging.getLogger("k8s_diag_agent.ui.api")


def _normalize_execution_indices_from_index(
    raw: object,
) -> dict[str, dict[int, str]]:
    """Normalize execution indices loaded from JSON index.

    When execution indices are stored in JSON, integer keys become strings.
    This function converts them back to integers for consistent lookup.

    Args:
        raw: The raw _execution_indices value from recent_summary (may be untyped dict)

    Returns:
        Normalized dict with int keys: run_id -> {candidate_index: status_string}
        String keys that cannot be parsed as int are ignored.
        Non-string status values are converted to "unknown".
    """
    if not isinstance(raw, dict):
        return {}

    result: dict[str, dict[int, str]] = {}
    for run_id, indices in raw.items():
        if not isinstance(run_id, str) or not isinstance(indices, dict):
            continue

        normalized: dict[int, str] = {}
        for key, value in indices.items():
            # Convert string key to int
            if isinstance(key, int):
                candidate_idx = key
            elif isinstance(key, str):
                try:
                    candidate_idx = int(key)
                except (ValueError, TypeError):
                    # Non-integer string key - skip this entry
                    continue
            else:
                # Non-string, non-int key - skip
                continue

            # Normalize status to string
            if isinstance(value, str):
                status = value
            elif value is None:
                status = "unknown"
            else:
                status = str(value) if value else "unknown"

            normalized[candidate_idx] = status

        result[run_id] = normalized

    return result


def _compute_execution_summary_indexed(
    plan_data: dict[str, object],
    execution_indices: dict[int, str],
) -> BatchExecutionSummary:
    """Compute execution summary from pre-loaded plan and execution data.

    This is the index-backed version that uses pre-scanned data without
    filesystem access. It derives the same summary as _compute_execution_summary()
    but uses index-computed execution indices (status strings) for failedCandidates.

    Args:
        plan_data: The next-check-plan artifact data
        execution_indices: Dict of {candidate_index: status_string} from execution artifacts

    Returns:
        BatchExecutionSummary with all execution state fields
    """
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

    # Count executable and executed candidates
    executable_count = 0
    executed_count = 0
    failed_count = 0
    pending_executable = 0

    for idx, candidate in enumerate(candidates_data):
        is_executable = _is_candidate_batch_executable(candidate)
        is_executed = idx in execution_indices

        if is_executable:
            executable_count += 1
            if not is_executed:
                pending_executable += 1

        if is_executed:
            executed_count += 1
            status = execution_indices.get(idx, "unknown")
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


def _build_runs_list_from_index(
    runs_dir: Path,
    runs_from_index: list[dict[str, object]],
    recent_summary: dict[str, object],
    limit: int | None,
    timings: RunsListTimings,
    start_time: float,
) -> RunsListPayload:
    """Build runs list from ui-index.json's recent_runs_summary.

    This is the fastest path - no filesystem scanning needed as data
    is pre-compiled during index generation.
    """
    total_count = cast(int, recent_summary.get("total_count", len(runs_from_index)))

    runs_to_return = runs_from_index
    if limit is not None:
        runs_to_return = runs_from_index[:limit]

    runs_list: list[RunsListEntry] = []
    for entry in runs_to_return:
        run_id = cast(str, entry.get("run_id", ""))
        run_label = cast(str, entry.get("run_label", run_id))
        timestamp = cast(str, entry.get("timestamp", ""))
        cluster_count = cast(int, entry.get("cluster_count", 0))

        runs_list.append(
            RunsListEntry(
                runId=run_id,
                runLabel=run_label,
                timestamp=timestamp,
                clusterCount=cluster_count,
                triaged=False,
                executionCount=0,
                reviewedCount=0,
                reviewStatus="unknown",
                reviewDownloadPath=None,
                batchEligibility="unknown",
                batchExecutable=False,
                batchEligibleCount=0,
                executionSummary=None,
            )
        )

    timings["batch_plan_files_found"] = 0
    timings["batch_exec_files_found"] = 0
    timings["batch_eligibility_prescan_ms"] = 0.0

    timings["row_assembly_ms"] = (time.perf_counter() - start_time) * 1000
    timings["rows_built"] = len(runs_list)
    timings["rows_considered"] = len(runs_from_index)
    timings["rows_returned"] = len(runs_list)

    returned_count = len(runs_list)
    has_more = total_count > returned_count

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=total_count,
        returnedCount=returned_count,
        hasMore=has_more,
        executionCountsComplete=False,
    )

    timings["total_duration_ms"] = (time.perf_counter() - start_time) * 1000

    return payload


def _build_runs_list_with_batch_eligibility_index(
    runs_dir: Path,
    runs_from_index: list[dict[str, object]],
    recent_summary: dict[str, object],
    limit: int | None,
    timings: RunsListTimings,
    start_time: float,
) -> RunsListPayload:
    """Build runs list from ui-index.json's recent_runs_summary with batch eligibility.

    This is the index-backed path for include_batch_eligibility=true.
    It reads batch eligibility AND execution summary from the pre-computed index.
    """
    total_count = cast(int, recent_summary.get("total_count", len(runs_from_index)))

    runs_to_return = runs_from_index
    if limit is not None:
        runs_to_return = runs_from_index[:limit]

    all_plan_data = cast(dict[str, dict[str, object]], recent_summary.get("_plan_data", {}))
    all_execution_indices = _normalize_execution_indices_from_index(recent_summary.get("_execution_indices", {}))

    run_health_dir = runs_dir / "health"
    ui_index_path = run_health_dir / "ui-index.json"
    external_analysis_dir = run_health_dir / "external-analysis"
    execution_indices_are_stale = False

    generated_at_str = recent_summary.get("generated_at")
    generated_at_ts: float | None = None
    if isinstance(generated_at_str, str):
        parsed_dt = parse_iso_to_utc(generated_at_str)
        if parsed_dt is not None:
            generated_at_ts = parsed_dt.timestamp()

    if generated_at_ts is not None and external_analysis_dir.exists():
        try:
            exec_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))
            if exec_files:
                newest_execution_artifact_mtime = max(f.stat().st_mtime for f in exec_files if f.exists())
                if newest_execution_artifact_mtime > generated_at_ts:
                    execution_indices_are_stale = True
                    timings["index_stale_by_generated_at"] = True
        except (OSError, ValueError):
            pass

    external_analysis_is_fresher = False
    if not execution_indices_are_stale and ui_index_path.exists():
        try:
            ui_index_mtime = ui_index_path.stat().st_mtime
            if external_analysis_dir.exists():
                external_mtime = external_analysis_dir.stat().st_mtime
                if external_mtime > ui_index_mtime:
                    external_analysis_is_fresher = True
                    timings["index_stale_execution_indices"] = True
        except OSError:
            pass

    if execution_indices_are_stale or external_analysis_is_fresher:
        timings["index_stale_execution_indices"] = True

    if execution_indices_are_stale or external_analysis_is_fresher:
        from .execution_index_utils import collect_execution_indices_for_all_runs

        if external_analysis_dir.exists():
            fresh_indices, _ = collect_execution_indices_for_all_runs(external_analysis_dir)
            for run_id, indices in fresh_indices.items():
                all_execution_indices[run_id] = indices
            timings["index_execution_indices_recomputed"] = True

    runs_list: list[RunsListEntry] = []
    for entry in runs_to_return:
        run_id = cast(str, entry.get("run_id", ""))
        run_label = cast(str, entry.get("run_label", run_id))
        timestamp = cast(str, entry.get("timestamp", ""))
        cluster_count = cast(int, entry.get("cluster_count", 0))

        batch_eligibility = cast(Literal["computed", "unknown"], entry.get("batchEligibility", "unknown"))
        batch_executable = cast(bool, entry.get("batchExecutable", False))
        batch_eligible_count = cast(int, entry.get("batchEligibleCount", 0))

        execution_summary: BatchExecutionSummary | None = None
        if batch_eligibility == "computed" and run_id in all_plan_data:
            exec_indices = all_execution_indices.get(run_id, {})
            execution_summary = _compute_execution_summary_indexed(all_plan_data[run_id], exec_indices)

            if execution_indices_are_stale or external_analysis_is_fresher:
                from .api_runs_payloads_batch import _compute_batch_eligibility_from_cache

                batch_executable, batch_eligible_count = _compute_batch_eligibility_from_cache(
                    run_id, all_plan_data, all_execution_indices
                )

        runs_list.append(
            RunsListEntry(
                runId=run_id,
                runLabel=run_label,
                timestamp=timestamp,
                clusterCount=cluster_count,
                triaged=False,
                executionCount=0,
                reviewedCount=0,
                reviewStatus="unknown",
                reviewDownloadPath=None,
                batchEligibility=batch_eligibility,
                batchExecutable=batch_executable,
                batchEligibleCount=batch_eligible_count,
                executionSummary=execution_summary,
            )
        )

    timings["batch_plan_files_found"] = 0
    timings["batch_exec_files_found"] = 0
    timings["batch_eligibility_prescan_ms"] = 0.0
    timings["batch_plan_glob_ms"] = 0.0
    timings["batch_exec_glob_ms"] = 0.0
    timings["batch_eligibility_row_ms"] = 0.0

    timings["row_assembly_ms"] = (time.perf_counter() - start_time) * 1000
    timings["rows_built"] = len(runs_list)
    timings["rows_considered"] = len(runs_from_index)
    timings["rows_returned"] = len(runs_list)
    timings["batch_eligibility_runs_computed"] = len(runs_list)
    timings["batch_eligible_runs"] = sum(1 for entry in runs_to_return if entry.get("batchExecutable", False))

    returned_count = len(runs_list)
    has_more = total_count > returned_count

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=total_count,
        returnedCount=returned_count,
        hasMore=has_more,
        executionCountsComplete=False,
    )

    timings["total_duration_ms"] = (time.perf_counter() - start_time) * 1000

    return payload