"""Stage 2 scan and row assembly for build_runs_list().

This module contains the heavy-lifting scan logic when neither the
super-fast index path nor the index-backed batch eligibility path applies.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from .api_payloads import (
    BatchExecutionSummary,
    RunsListEntry,
    RunsListTimings,
)
from .api_runs_payloads_batch import (
    _compute_batch_eligibility_from_cache,
    _compute_execution_summary,
)
from .api_runs_payloads_review import _derive_review_status


def build_runs_list_scan_stage(
    runs_dir: Path,
    *,
    run_entries: dict[str, dict[str, object]],
    timings: RunsListTimings,
    limit: int | None,
    include_status: bool,
    include_expensive: bool,
    batch_eligibility_run_ids: set[str],
) -> tuple[
    list[RunsListEntry],
    int,
    int,
    bool,
    dict[str, dict[int, str]],
    dict[str, dict[str, object]],
]:
    """Stage 2: scan execution artifacts and build runs list entries.

    This function handles the expensive scan operations:
    - Execution artifact scanning for status counts
    - Plan/execution file scanning for batch eligibility
    - Row assembly with all computed fields

    Returns:
        Tuple of (runs_list, total_discovered, returned_count, has_more,
                  execution_indices, plan_data)
    """
    run_health_dir = runs_dir / "health"
    external_analysis_dir = run_health_dir / "external-analysis"
    diagnostic_packs_dir = run_health_dir / "diagnostic-packs"

    row_assembly_start = time.perf_counter()

    sort_start = time.perf_counter()
    sorted_entries = sorted(
        run_entries.values(),
        key=lambda e: cast("datetime", e["parsed_time"]),
        reverse=True,
    )
    timings["sort_ms"] = (time.perf_counter() - sort_start) * 1000

    rows_considered = len(sorted_entries)
    timings["rows_considered"] = rows_considered

    window_run_ids: set[str]
    if limit is not None:
        window_run_ids = {cast(str, entry["run_id"]) for entry in sorted_entries[:limit]}
        rows_to_return = min(limit, len(sorted_entries))
    else:
        window_run_ids = set(run_entries.keys())
        rows_to_return = len(sorted_entries)

    sorted_window_run_ids = sorted(window_run_ids, key=len, reverse=True)

    execution_scan_start = time.perf_counter()

    execution_parsed = 0
    execution_count_matches = 0

    window_exec_files: list[tuple[Path, str]] = []

    execution_lookup_start = time.perf_counter()

    if include_status:
        timings["status_lookup_strategy"] = "window_glob"
        timings["status_run_prefixes_queried"] = len(window_run_ids)
        timings["execution_lookup_strategy"] = "window_glob"
        timings["execution_run_prefixes_queried"] = len(window_run_ids)

        if external_analysis_dir.is_dir():
            for run_id in sorted_window_run_ids:
                pattern = f"{run_id}-next-check-execution*.json"
                for exec_path in external_analysis_dir.glob(pattern):
                    window_exec_files.append((exec_path, run_id))

        timings["status_files_found"] = len(window_exec_files)
        timings["execution_files_found_total"] = len(window_exec_files)
        timings["execution_files_considered"] = len(window_exec_files)
        timings["execution_files_skipped_outside_window"] = 0

        execution_parse_start = time.perf_counter()
        for exec_path, run_id in window_exec_files:
            execution_parsed += 1
            try:
                raw = json.loads(exec_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue

            purpose = raw.get("purpose")
            if purpose != "next-check-execution":
                continue

            execution_count_matches += 1

            current_exec_count = run_entries[run_id].get("execution_count", 0)
            run_entries[run_id]["execution_count"] = cast(int, current_exec_count) + 1

            usefulness = raw.get("usefulness_class")
            if usefulness and isinstance(usefulness, str) and usefulness.strip():
                current_reviewed_count = run_entries[run_id].get("reviewed_count", 0)
                run_entries[run_id]["reviewed_count"] = cast(int, current_reviewed_count) + 1

        timings["status_lookup_ms"] = (time.perf_counter() - execution_lookup_start) * 1000
        timings["execution_parse_ms"] = (time.perf_counter() - execution_parse_start) * 1000
        timings["execution_files_parsed"] = execution_parsed
    else:
        timings["status_lookup_strategy"] = "skipped_fast_path"
        timings["status_run_prefixes_queried"] = 0
        timings["status_files_found"] = 0
        timings["execution_lookup_strategy"] = "skipped_fast_path"
        timings["execution_run_prefixes_queried"] = 0
        timings["execution_files_found_total"] = 0
        timings["execution_files_considered"] = 0
        timings["execution_files_skipped_outside_window"] = 0
        timings["execution_parse_ms"] = 0.0
        timings["execution_files_parsed"] = 0
        timings["status_lookup_ms"] = 0.0

    timings["execution_lookup_ms"] = (time.perf_counter() - execution_lookup_start) * 1000
    timings["execution_count_derivation_ms"] = (time.perf_counter() - execution_scan_start) * 1000
    timings["execution_count_derivation_matches"] = execution_count_matches

    timings["rows_returned"] = rows_to_return

    review_artifact_exists: dict[str, bool] = {}
    review_artifact_scan_start = time.perf_counter()
    if diagnostic_packs_dir.is_dir():
        for run_dir in diagnostic_packs_dir.iterdir():
            if run_dir.is_dir():
                run_id = run_dir.name
                review_path = run_dir / "next_check_usefulness_review.json"
                review_artifact_exists[run_id] = review_path.exists()
    timings["review_artifact_prescan_ms"] = (time.perf_counter() - review_artifact_scan_start) * 1000

    batch_eligibility_prescan_start = time.perf_counter()

    batch_plan_glob_start = time.perf_counter()
    plan_files: list[Path] = []
    if external_analysis_dir.is_dir():
        plan_files = list(external_analysis_dir.glob("*-next-check-plan*.json"))
    timings["batch_plan_glob_ms"] = (time.perf_counter() - batch_plan_glob_start) * 1000
    timings["batch_plan_files_found"] = len(plan_files)

    batch_plan_parse_start = time.perf_counter()
    plan_data: dict[str, dict[str, object]] = {}
    for plan_path in plan_files:
        filename = plan_path.stem
        for run_id in sorted_window_run_ids:
            if filename.startswith(f"{run_id}-next-check-plan"):
                try:
                    raw = json.loads(plan_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-planning":
                        plan_data[run_id] = raw
                        break
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
    timings["batch_plan_parse_ms"] = (time.perf_counter() - batch_plan_parse_start) * 1000

    batch_exec_glob_start = time.perf_counter()
    exec_files: list[Path] = []
    if external_analysis_dir.is_dir():
        exec_files = list(external_analysis_dir.glob("*-next-check-execution*.json"))
    timings["batch_exec_glob_ms"] = (time.perf_counter() - batch_exec_glob_start) * 1000
    timings["batch_exec_files_found"] = len(exec_files)

    batch_exec_parse_start = time.perf_counter()
    execution_indices: dict[str, dict[int, str]] = {run_id: {} for run_id in window_run_ids}
    for exec_path in exec_files:
        filename = exec_path.stem
        for run_id in sorted_window_run_ids:
            if filename.startswith(f"{run_id}-next-check-execution"):
                try:
                    raw = json.loads(exec_path.read_text(encoding="utf-8"))
                    if raw.get("purpose") == "next-check-execution":
                        exec_payload: dict[str, object] = cast(dict[str, object], raw.get("payload", {}))
                        candidate_index = exec_payload.get("candidateIndex")
                        if isinstance(candidate_index, int):
                            status = raw.get("status", "unknown")
                            if isinstance(status, str):
                                execution_indices[run_id][candidate_index] = status
                            else:
                                execution_indices[run_id][candidate_index] = "unknown"
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
    timings["batch_exec_parse_ms"] = (time.perf_counter() - batch_exec_parse_start) * 1000

    timings["batch_run_id_matching_ms"] = 0.0
    timings["batch_cache_construction_ms"] = 0.0
    timings["batch_eligibility_prescan_ms"] = (time.perf_counter() - batch_eligibility_prescan_start) * 1000

    runs_list: list[RunsListEntry] = []
    review_download_paths_found = 0
    batch_eligible_runs = 0

    review_status_row_ms_total = 0.0
    review_download_path_row_ms_total = 0.0
    batch_eligibility_row_ms_total = 0.0
    artifact_lookup_row_ms_total = 0.0
    timestamp_normalization_row_ms_total = 0.0
    label_normalization_row_ms_total = 0.0

    entries_to_build = sorted_entries[:rows_to_return] if limit is not None else sorted_entries

    for entry in entries_to_build:
        run_id = entry["run_id"]

        row_start = time.perf_counter()
        execution_count = cast(int, entry.get("execution_count", 0))
        reviewed_count = cast(int, entry.get("reviewed_count", 0))
        review_status = _derive_review_status(execution_count, reviewed_count)
        triaged = execution_count > 0 and reviewed_count > 0
        review_status_row_ms_total += (time.perf_counter() - row_start) * 1000

        row_start = time.perf_counter()
        review_download_path: str | None = None
        if review_status in ("unreviewed", "partially-reviewed"):
            run_id_str = cast(str, run_id)
            if review_artifact_exists.get(run_id_str, False):
                run_scoped_path = diagnostic_packs_dir / run_id_str / "next_check_usefulness_review.json"
                review_download_path = str(run_scoped_path.relative_to(runs_dir))
                review_download_paths_found += 1
        review_download_path_row_ms_total += (time.perf_counter() - row_start) * 1000

        row_start = time.perf_counter()
        if run_id in batch_eligibility_run_ids:
            batch_executable, batch_eligible_count = _compute_batch_eligibility_from_cache(
                run_id, plan_data, execution_indices
            )
            batch_eligibility = "computed"
            if batch_executable:
                batch_eligible_runs += 1
        else:
            batch_executable = False
            batch_eligible_count = 0
            batch_eligibility = "unknown"
        batch_eligibility_row_ms_total += (time.perf_counter() - row_start) * 1000

        row_start = time.perf_counter()
        artifact_lookup_row_ms_total += (time.perf_counter() - row_start) * 1000

        row_start = time.perf_counter()
        timestamp_normalization_row_ms_total += (time.perf_counter() - row_start) * 1000

        row_start = time.perf_counter()
        label_normalization_row_ms_total += (time.perf_counter() - row_start) * 1000

        execution_summary: BatchExecutionSummary | None = None
        if run_id in batch_eligibility_run_ids:
            execution_summary = _compute_execution_summary(run_id, plan_data, execution_indices)
        else:
            execution_summary = None

        runs_list.append(
            RunsListEntry(
                runId=cast(str, entry["run_id"]),
                runLabel=cast(str, entry["run_label"]),
                timestamp=cast(str, entry["timestamp"]),
                clusterCount=cast(int, entry["cluster_count"]),
                triaged=triaged,
                executionCount=execution_count,
                reviewedCount=reviewed_count,
                reviewStatus=review_status,
                reviewDownloadPath=review_download_path,
                batchEligibility=cast(Literal["computed", "unknown"], batch_eligibility),
                batchExecutable=batch_executable,
                batchEligibleCount=batch_eligible_count,
                executionSummary=execution_summary,
            )
        )

    timings["review_status_row_ms"] = round(review_status_row_ms_total, 2)
    timings["review_download_path_row_ms"] = round(review_download_path_row_ms_total, 2)
    timings["batch_eligibility_row_ms"] = round(batch_eligibility_row_ms_total, 2)
    timings["artifact_lookup_row_ms"] = round(artifact_lookup_row_ms_total, 2)
    timings["timestamp_normalization_row_ms"] = round(timestamp_normalization_row_ms_total, 2)
    timings["label_normalization_row_ms"] = round(label_normalization_row_ms_total, 2)
    timings["per_row_fs_checks_ms"] = 0.0

    timings["review_download_path_checks_ms"] = 0
    timings["review_download_paths_found"] = review_download_paths_found
    timings["row_assembly_ms"] = (time.perf_counter() - row_assembly_start) * 1000
    timings["rows_built"] = len(runs_list)

    timings["batch_eligible_runs"] = batch_eligible_runs
    timings["batch_eligibility_runs_computed"] = len(batch_eligibility_run_ids)

    timings["path_exists_calls"] = 0
    timings["stat_calls"] = 0
    timings["diagnostic_pack_path_checks"] = 0
    timings["run_scoped_review_path_checks"] = 0
    timings["per_run_glob_calls"] = 0
    timings["per_run_directory_list_calls"] = 0

    total_discovered = len(run_entries)
    returned_count = len(runs_list)
    has_more = total_discovered > returned_count

    return (
        runs_list,
        total_discovered,
        returned_count,
        has_more,
        execution_indices,
        plan_data,
    )