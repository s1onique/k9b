"""Runs-list payload builder for the UI server.

This module contains the runs-list payload construction logic extracted from
server_reads.py. It handles runs-list response shaping including batch eligibility,
cache management, and structured logging.

Keep behavior exact: pagination, window behavior, batch eligibility, cache behavior,
HTTP status codes, error messages, and timing/debug metadata are preserved.

Extraction rationale: This module focuses on runs-list payload construction which is
a distinct concern from route handling (server_runs_list_reads.py) or artifact reads
(server_artifact_reads.py).
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

from ..security import sanitize_exception_message
from ..structured_logging import emit_structured_log
from .api import build_runs_list
from .server_artifact_reads import _has_batch_eligibility_index

logger = logging.getLogger(__name__)

__all__ = [
    "build_runs_list_payload",
]


def build_runs_list_payload(
    handler: HealthUIRequestHandler,
    *,
    limit: int | None = 100,
    include_status: bool = False,
    include_expensive: bool = False,
    include_batch_eligibility: bool = False,
) -> dict[str, object]:
    """Build the list of available runs with their triage state.

    A run is considered "triaged" if at least one next-check execution artifact
    has the usefulness_class field set.

    Performance optimization:
    - By default (limit=100), only computes batch eligibility for the returned window.
    - Set include_expensive=True to compute batch eligibility for all runs.
    - Set limit=None to return all runs without batch eligibility computation.
    - Set include_batch_eligibility=True to compute batch eligibility only (no status counts).
      This is the fastest path for initial UI load with actionable Execute buttons.

    Args:
        handler: The HealthUIRequestHandler instance
        limit: Maximum number of runs to return (default 100). None for all runs.
        include_status: If True, compute status/review/execution projection for returned
            window. This is a bounded, cheaper operation than include_expensive.
        include_expensive: If True, compute batch eligibility for all runs (expensive).
            Note: include_expensive=True implies include_status=True.
        include_batch_eligibility: If True, compute batch eligibility only for returned
            window (no execution counts). This is faster than include_status as it
            skips execution artifact scanning. Use this for initial UI load when
            Execute buttons are needed but full status isn't.

    Returns:
        The runs list payload dict
    """
    timings: dict[str, float | str] = {}
    total_start = time.perf_counter()

    health_root = handler.runs_dir / "health"
    cache_mtime = 0.0

    # Check if we can use the fast index path for batch eligibility (requires v2 index with batch fields)
    # When this path is used, we use ui-index.json mtime instead of external-analysis mtime
    # because batch eligibility is pre-computed in the index, not derived from external-analysis files.
    use_batch_eligibility_index = include_batch_eligibility and not include_status and not include_expensive

    if health_root.exists():
        try:
            ui_index_path = health_root / "ui-index.json"

            if use_batch_eligibility_index and ui_index_path.exists() and _has_batch_eligibility_index(ui_index_path):
                # FAST PATH: Use ui-index.json mtime for cache freshness.
                # Batch eligibility comes from the index, not from external-analysis files.
                # Only use this path if the index is v2+ with batch eligibility fields.
                # NOTE: We still include external-analysis mtime to ensure cache invalidation
                # after batch execution writes new execution artifacts.
                cache_mtime = ui_index_path.stat().st_mtime
                external_analysis_dir = health_root / "external-analysis"
                if external_analysis_dir.exists():
                    external_mtime = external_analysis_dir.stat().st_mtime
                    # CRITICAL: Use max(ui-index, external-analysis) mtime to ensure
                    # cache is invalidated when new execution artifacts are written,
                    # even if ui-index.json wasn't regenerated.
                    cache_mtime = max(cache_mtime, external_mtime)
                timings["cache_freshness_source"] = "ui_index_plus_external"
                timings["cache_freshness_path"] = "batch_eligibility_index"
            else:
                # STANDARD PATH: Use external-analysis mtime for cache correctness.
                # This is needed when batch eligibility is derived from plan/execution files.
                mtimes = []
                reviews_dir = health_root / "reviews"
                diagnostic_packs_dir = health_root / "diagnostic-packs"
                for d in [reviews_dir, diagnostic_packs_dir]:
                    if d.exists():
                        mtimes.append(d.stat().st_mtime)
                # external-analysis mtime is needed for batch eligibility derivation
                # (include_status and include_expensive both need it)
                if include_status or include_expensive or include_batch_eligibility:
                    external_analysis_dir = health_root / "external-analysis"
                    if external_analysis_dir.exists():
                        mtimes.append(external_analysis_dir.stat().st_mtime)
                if mtimes:
                    cache_mtime = max(mtimes)
                timings["cache_freshness_source"] = "directory_mtimes" if mtimes else "none"
                timings["cache_freshness_path"] = "standard"
        except OSError:
            pass
    timings["index_read_ms"] = (time.perf_counter() - total_start) * 1000

    # Include cache_mtime for filesystem freshness. Without it, a new run or execution
    # artifact would cause stale cache hits for the same parameter combination.
    cache_key = f"{handler.runs_dir}:{cache_mtime}:limit={limit}:status={include_status}:expensive={include_expensive}:batch_eligibility={include_batch_eligibility}"

    from .server import _runs_list_cache, _runs_list_cache_lock

    with _runs_list_cache_lock:
        cached = _runs_list_cache.get(cache_key)
        if cached is not None:
            cached_payload, cached_mtime = cached
            if cached_mtime == cache_mtime:
                total_duration = (time.perf_counter() - total_start) * 1000
                emit_structured_log(
                    component="ui-runs-list",
                    message="/api/runs payload served from cache",
                    run_id="",
                    run_label="",
                    severity="DEBUG",
                    metadata={
                        "path": "/api/runs",
                        "total_duration_ms": round(total_duration, 2),
                        "cache_hit": True,
                        "limit": limit,
                        "include_expensive": include_expensive,
                    },
                )
                return cached_payload

    reviews_scan_start = time.perf_counter()
    reviews_dir = health_root / "reviews"
    review_count = 0
    if reviews_dir.exists():
        review_count = len(list(reviews_dir.glob("*-review.json")))
    timings["reviews_scan_ms"] = (time.perf_counter() - reviews_scan_start) * 1000
    timings["review_files_count"] = review_count

    external_analysis_scan_start = time.perf_counter()
    external_analysis_dir = health_root / "external-analysis"
    execution_count = 0
    if external_analysis_dir.exists():
        execution_count = len(list(external_analysis_dir.glob("*-next-check-execution*.json")))
    timings["external_analysis_scan_ms"] = (time.perf_counter() - external_analysis_scan_start) * 1000
    timings["execution_files_scanned"] = execution_count

    payload_build_start = time.perf_counter()
    payload: dict[str, object]
    try:
        result = build_runs_list(
            handler.runs_dir,
            limit=limit,
            include_status=include_status,
            include_expensive=include_expensive,
            include_batch_eligibility=include_batch_eligibility,
            _timings=True,
        )
        if isinstance(result, tuple):
            raw_payload, inner_timings = result
            payload = cast(dict[str, object], raw_payload)
            for key, value in inner_timings.items():
                timings[key] = cast(float, value)
        else:
            payload = cast(dict[str, object], result)
    except Exception as exc:
        logger.warning(
            "Failed to build runs list payload",
            extra={"error": str(exc)},
        )
        emit_structured_log(
            component="ui-runs-list",
            message="/api/runs payload build failed",
            run_id="",
            run_label="",
            severity="ERROR",
            metadata={
                "path": "/api/runs",
                "error": str(exc),
                "limit": limit,
                "include_expensive": include_expensive,
            },
        )
        payload = {"runs": [], "error": sanitize_exception_message(exc)}
    timings["payload_build_ms"] = (time.perf_counter() - payload_build_start) * 1000

    serialize_start = time.perf_counter()
    _ = json.dumps(payload, ensure_ascii=False)
    timings["serialize_ms"] = (time.perf_counter() - serialize_start) * 1000

    with _runs_list_cache_lock:
        if len(_runs_list_cache) >= 10:
            oldest_key = next(iter(_runs_list_cache))
            del _runs_list_cache[oldest_key]
        _runs_list_cache[cache_key] = (cast(dict[str, Any], payload), cache_mtime)

    total_duration = (time.perf_counter() - total_start) * 1000
    timings["total_duration_ms"] = total_duration

    emit_structured_log(
        component="ui-runs-list",
        message="/api/runs payload built with timing",
        run_id="",
        run_label="",
        severity="INFO",
        metadata={
            "path": "/api/runs",
            "total_duration_ms": round(cast(float, timings.get("total_duration_ms", 0)), 2),
            "index_read_ms": round(cast(float, timings.get("index_read_ms", 0)), 2),
            "reviews_scan_ms": round(cast(float, timings.get("reviews_scan_ms", 0)), 2),
            "external_analysis_scan_ms": round(cast(float, timings.get("external_analysis_scan_ms", 0)), 2),
            "payload_build_ms": round(cast(float, timings.get("payload_build_ms", 0)), 2),
            "serialize_ms": round(cast(float, timings.get("serialize_ms", 0)), 2),
            "review_files_count": timings.get("review_files_count", 0),
            "execution_files_scanned": timings.get("execution_files_scanned", 0),
            "runs_count": len(cast(list, payload.get("runs", []))),
            "cache_hit": False,
            "limit": limit,
            "include_expensive": include_expensive,
            "reviews_glob_ms": round(cast(float, timings.get("reviews_glob_ms", 0)), 2),
            "reviews_parsed": timings.get("reviews_parsed", 0),
            "reviews_glob_only_ms": round(cast(float, timings.get("reviews_glob_only_ms", 0)), 2),
            "reviews_files_found": timings.get("reviews_files_found", 0),
            "reviews_parse_ms": round(cast(float, timings.get("reviews_parse_ms", 0)), 2),
            "execution_artifacts_glob_ms": round(cast(float, timings.get("execution_artifacts_glob_ms", 0)), 2),
            "execution_glob_only_ms": round(cast(float, timings.get("execution_glob_only_ms", 0)), 2),
            "execution_parse_ms": round(cast(float, timings.get("execution_parse_ms", 0)), 2),
            "execution_artifacts_scanned": timings.get("execution_artifacts_scanned", 0),
            "execution_count_derivation_ms": round(cast(float, timings.get("execution_count_derivation_ms", 0)), 2),
            "execution_count_derivation_matches": timings.get("execution_count_derivation_matches", 0),
            "execution_lookup_strategy": timings.get("execution_lookup_strategy", "unknown"),
            "execution_run_prefixes_queried": timings.get("execution_run_prefixes_queried", 0),
            "execution_files_found_total": timings.get("execution_files_found_total", 0),
            "execution_files_considered": timings.get("execution_files_considered", 0),
            "execution_files_parsed": timings.get("execution_files_parsed", 0),
            "execution_files_skipped_outside_window": timings.get("execution_files_skipped_outside_window", 0),
            "execution_lookup_ms": round(cast(float, timings.get("execution_lookup_ms", 0)), 2),
            "row_assembly_ms": round(cast(float, timings.get("row_assembly_ms", 0)), 2),
            "sort_ms": round(cast(float, timings.get("sort_ms", 0)), 2),
            "batch_eligible_runs": timings.get("batch_eligible_runs", 0),
            "review_artifact_prescan_ms": round(cast(float, timings.get("review_artifact_prescan_ms", 0)), 2),
            "batch_eligibility_prescan_ms": round(cast(float, timings.get("batch_eligibility_prescan_ms", 0)), 2),
            "batch_plan_glob_ms": round(cast(float, timings.get("batch_plan_glob_ms", 0)), 2),
            "batch_plan_files_found": timings.get("batch_plan_files_found", 0),
            "batch_plan_parse_ms": round(cast(float, timings.get("batch_plan_parse_ms", 0)), 2),
            "batch_exec_glob_ms": round(cast(float, timings.get("batch_exec_glob_ms", 0)), 2),
            "batch_exec_files_found": timings.get("batch_exec_files_found", 0),
            "batch_exec_parse_ms": round(cast(float, timings.get("batch_exec_parse_ms", 0)), 2),
            "batch_run_id_matching_ms": round(cast(float, timings.get("batch_run_id_matching_ms", 0)), 2),
            "batch_cache_construction_ms": round(cast(float, timings.get("batch_cache_construction_ms", 0)), 2),
            "review_status_row_ms": round(cast(float, timings.get("review_status_row_ms", 0)), 2),
            "review_download_path_row_ms": round(cast(float, timings.get("review_download_path_row_ms", 0)), 2),
            "batch_eligibility_row_ms": round(cast(float, timings.get("batch_eligibility_row_ms", 0)), 2),
            "artifact_lookup_row_ms": round(cast(float, timings.get("artifact_lookup_row_ms", 0)), 2),
            "timestamp_normalization_row_ms": round(cast(float, timings.get("timestamp_normalization_row_ms", 0)), 2),
            "label_normalization_row_ms": round(cast(float, timings.get("label_normalization_row_ms", 0)), 2),
            "per_row_fs_checks_ms": round(cast(float, timings.get("per_row_fs_checks_ms", 0)), 2),
            "rows_built": timings.get("rows_built", 0),
            "rows_considered": timings.get("rows_considered", 0),
            "rows_returned": timings.get("rows_returned", 0),
            "batch_eligibility_runs_computed": timings.get("batch_eligibility_runs_computed", 0),
            "path_exists_calls": timings.get("path_exists_calls", 0),
            "stat_calls": timings.get("stat_calls", 0),
            "diagnostic_pack_path_checks": timings.get("diagnostic_pack_path_checks", 0),
            "run_scoped_review_path_checks": timings.get("run_scoped_review_path_checks", 0),
            "per_run_glob_calls": timings.get("per_run_glob_calls", 0),
            "per_run_directory_list_calls": timings.get("per_run_directory_list_calls", 0),
        },
    )

    return payload
