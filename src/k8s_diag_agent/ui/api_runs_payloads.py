"""Runs-list payload builders for the operator UI.

This module is the thin orchestrator that delegates to specialized modules:
- api_runs_payloads_index.py: index-backed fast paths
- api_runs_payloads_batch.py: batch eligibility computations
- api_runs_payloads_streaming.py: review file fallback
- api_runs_payloads_review.py: review metadata helpers
- api_runs_payloads_scan.py: Stage 2 scan and row assembly

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Literal, cast, overload

from .api_payloads import (
    RunsListPayload,
    RunsListTimings,
)
from .api_runs_payloads_batch import (
    _compute_batch_eligibility,  # noqa: F401 - re-exported for backward compatibility
)
from .api_runs_payloads_index import (
    _build_runs_list_from_index,
    _build_runs_list_with_batch_eligibility_index,
)
from .api_runs_payloads_review import _extract_review_metadata_streaming
from .api_runs_payloads_scan import build_runs_list_scan_stage
from .api_runs_payloads_streaming import _build_runs_list_review_streaming

logger = logging.getLogger("k8s_diag_agent.ui.api")


@overload
def _build_runs_list_super_fast(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    _timings: Literal[False] = False,
) -> RunsListPayload: ...


@overload
def _build_runs_list_super_fast(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    _timings: Literal[True] = True,
) -> tuple[RunsListPayload, RunsListTimings]: ...


def _build_runs_list_super_fast(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    _timings: bool = False,
) -> RunsListPayload | tuple[RunsListPayload, RunsListTimings]:
    """Super fast path for initial UI load.

    First tries to read runs from ui-index.json's recent_runs_summary.
    Falls back to review file scanning if index is unavailable or malformed.

    This is the key optimization to avoid scanning all review files on each request.
    Batch eligibility and execution count derivation are ALWAYS skipped here.
    """
    timings: RunsListTimings = {}
    start_time = time.perf_counter()
    run_health_dir = runs_dir / "health"

    ui_index_path = run_health_dir / "ui-index.json"
    if ui_index_path.is_file():
        try:
            raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
            recent_summary = raw_index.get("recent_runs_summary")
            if isinstance(recent_summary, dict):
                runs_from_index = recent_summary.get("runs")
                total_count = recent_summary.get("total_count")
                if isinstance(runs_from_index, list) and isinstance(total_count, int):
                    timings["path_strategy"] = "index_super_fast_path"
                    timings["reviews_parsed"] = 0
                    timings["reviews_files_found"] = 0
                    payload = _build_runs_list_from_index(
                        runs_dir, runs_from_index, recent_summary, limit, timings, start_time
                    )
                    if _timings:
                        return payload, timings
                    return payload
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    timings["path_strategy"] = "review_streaming_super_fast_path"
    payload = _build_runs_list_review_streaming(runs_dir, limit, timings, start_time)
    if _timings:
        return payload, timings
    return payload


@overload
def build_runs_list(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    include_status: bool = False,
    include_expensive: bool = False,
    include_batch_eligibility: bool = False,
    _timings: Literal[False] = False,
) -> RunsListPayload: ...


@overload
def build_runs_list(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    include_status: bool = False,
    include_expensive: bool = False,
    include_batch_eligibility: bool = False,
    _timings: Literal[True] = True,
) -> tuple[RunsListPayload, RunsListTimings]: ...


def build_runs_list(
    runs_dir: Path,
    *,
    limit: int | None = 100,
    include_status: bool = False,
    include_expensive: bool = False,
    include_batch_eligibility: bool = False,
    _timings: bool = False,
) -> RunsListPayload | tuple[RunsListPayload, RunsListTimings]:
    """Build a list of available runs with their review coverage status.

    A run's review status is derived from execution artifacts in the
    external-analysis/ directory. The status indicates:
    - "no-executions": run has no executed next checks
    - "unreviewed": has executions but none reviewed
    - "partially-reviewed": some executions reviewed, some not
    - "fully-reviewed": all executions reviewed

    Runs are discovered from review artifacts in the reviews/ directory.

    Performance optimization:
    - By default (limit=100), only computes batch eligibility for the returned window.
    - Set include_expensive=True to compute batch eligibility for all runs.
    - Set limit=None to return all runs without batch eligibility computation.
    - Set include_batch_eligibility=True to compute batch eligibility only (no status counts).
      This is the fastest path for initial UI load with actionable Execute buttons.

    Args:
        runs_dir: Path to the runs directory
        limit: Maximum number of runs to return (default 100). None for all runs.
        include_status: If True, compute status/review/execution projection for returned
            window. This is a bounded, cheaper operation than include_expensive.
        include_expensive: If True, compute batch eligibility for all runs (expensive).
            If False (default), only compute for returned window.
            Note: include_expensive=True implies include_status=True.
        include_batch_eligibility: If True, compute batch eligibility only for returned
            window (no execution counts). This is faster than include_status as it
            skips execution artifact scanning. Use this for initial UI load when
            Execute buttons are needed but full status isn't.
        _timings: If True, return tuple of (payload, timings) with detailed metrics

    Returns:
        RunsListPayload, or tuple of (RunsListPayload, RunsListTimings) if _timings=True
    """
    timings: RunsListTimings = {}

    # === SUPER FAST PATH: No expensive operations needed ===
    if not include_expensive and not include_status and not include_batch_eligibility:
        return _build_runs_list_super_fast(runs_dir, limit=limit, _timings=_timings)

    # === INDEX-BACKED BATCH ELIGIBILITY PATH ===
    if include_batch_eligibility and not include_status and not include_expensive:
        timings_index: RunsListTimings = {}
        start_time_index = time.perf_counter()
        run_health_dir_index = runs_dir / "health"

        ui_index_path = run_health_dir_index / "ui-index.json"
        if ui_index_path.is_file():
            try:
                raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
                recent_summary = raw_index.get("recent_runs_summary")
                if isinstance(recent_summary, dict):
                    runs_from_index = recent_summary.get("runs")
                    total_count = recent_summary.get("total_count")
                    index_version = recent_summary.get("version", 1)
                    if isinstance(runs_from_index, list) and isinstance(total_count, int) and index_version >= 2:
                        if runs_from_index and all(
                            "batchEligibility" in entry and "batchExecutable" in entry
                            for entry in runs_from_index[:1]
                        ):
                            timings_index["path_strategy"] = "index_recent_runs_with_batch_eligibility"
                            timings_index["reviews_parsed"] = 0
                            timings_index["reviews_files_found"] = 0
                            timings_index["batch_plan_glob_ms"] = 0.0
                            timings_index["batch_exec_glob_ms"] = 0.0
                            payload = _build_runs_list_with_batch_eligibility_index(
                                runs_dir, runs_from_index, recent_summary, limit, timings_index, start_time_index
                            )
                            if _timings:
                                return payload, timings_index
                            return payload
                        else:
                            timings_index["path_strategy"] = "index_batch_eligibility_fallback"
                            timings_index["fallback_reason"] = "missing_batch_fields"
                            timings_index["index_version"] = index_version
                            timings_index["entries_checked"] = len(runs_from_index)
                            timings_index["entries_with_fields"] = sum(
                                1 for e in runs_from_index[:5]
                                if "batchEligibility" in e and "batchExecutable" in e
                            )
                            timings_index["index_rejected_reason"] = "entries_missing_batch_fields"
                            logger.debug(
                                "Batch eligibility index path rejected: entries missing batch fields",
                                extra={
                                    "path_strategy": timings_index["path_strategy"],
                                    "fallback_reason": timings_index["fallback_reason"],
                                    "index_version": index_version,
                                    "entries_checked": timings_index["entries_checked"],
                                    "entries_with_fields": timings_index["entries_with_fields"],
                                    "index_rejected_reason": timings_index["index_rejected_reason"],
                                },
                            )
                    else:
                        timings_index["path_strategy"] = "index_batch_eligibility_fallback"
                        timings_index["fallback_reason"] = (
                            "version_lt_2" if index_version < 2 else "invalid_index_structure"
                        )
                        timings_index["has_runs_list"] = isinstance(runs_from_index, list)
                        timings_index["has_total_count"] = isinstance(total_count, int)
                        timings_index["index_rejected_reason"] = (
                            f"version={index_version}, "
                            f"runs_is_list={isinstance(runs_from_index, list)}, "
                            f"total_is_int={isinstance(total_count, int)}"
                        )
                        logger.debug(
                            "Batch eligibility index path rejected: version or structure issue",
                            extra={
                                "path_strategy": timings_index["path_strategy"],
                                "fallback_reason": timings_index["fallback_reason"],
                                "index_version": index_version,
                                "has_runs_list": timings_index["has_runs_list"],
                                "has_total_count": timings_index["has_total_count"],
                                "index_rejected_reason": timings_index["index_rejected_reason"],
                            },
                        )
                else:
                    timings_index["path_strategy"] = "index_batch_eligibility_fallback"
                    timings_index["fallback_reason"] = "missing_recent_runs_summary"
                    timings_index["index_rejected_reason"] = "recent_runs_summary_not_dict"
                    logger.debug(
                        "Batch eligibility index path rejected: missing recent_runs_summary",
                        extra={
                            "path_strategy": timings_index["path_strategy"],
                            "fallback_reason": timings_index["fallback_reason"],
                            "index_rejected_reason": timings_index["index_rejected_reason"],
                        },
                    )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                timings_index["path_strategy"] = "index_batch_eligibility_fallback"
                timings_index["fallback_reason"] = "invalid_json"
                logger.debug(
                    "Batch eligibility index path rejected: invalid JSON",
                    extra={
                        "path_strategy": timings_index["path_strategy"],
                        "fallback_reason": timings_index["fallback_reason"],
                        "error": str(exc),
                    },
                )
        else:
            timings_index["path_strategy"] = "index_batch_eligibility_fallback"
            timings_index["fallback_reason"] = "index_missing"
            timings_index["index_rejected_reason"] = "ui_index_file_not_found"
            logger.debug(
                "Batch eligibility index path rejected: index file missing",
                extra={
                    "path_strategy": timings_index["path_strategy"],
                    "fallback_reason": timings_index["fallback_reason"],
                    "index_rejected_reason": timings_index["index_rejected_reason"],
                },
            )

        if timings_index.get("fallback_reason"):
            timings["fallback_reason"] = timings_index["fallback_reason"]
            timings["path_strategy"] = timings_index["path_strategy"]
            timings["index_rejected_reason"] = timings_index.get("index_rejected_reason", "")

    # === STAGE 1: Collect runs from review artifacts ===
    reviews_scan_start = time.perf_counter()
    run_health_dir = runs_dir / "health"
    reviews_dir = run_health_dir / "reviews"

    run_entries: dict[str, dict[str, object]] = {}
    reviews_parsed = 0

    reviews_glob_only_start = time.perf_counter()
    review_files: list[Path] = []
    if reviews_dir.is_dir():
        review_files = list(reviews_dir.glob("*-review.json"))
    timings["reviews_glob_only_ms"] = (time.perf_counter() - reviews_glob_only_start) * 1000
    timings["reviews_files_found"] = len(review_files)

    reviews_parse_start = time.perf_counter()

    review_fast_path_attempted = 0
    review_fast_path_succeeded = 0
    review_fast_path_fallbacks = 0
    review_fast_path_failure_json = 0
    review_fast_path_failure_missing_field = 0

    for review_path in review_files:
        review_fast_path_attempted += 1
        extracted = _extract_review_metadata_streaming(review_path)

        if extracted is not None:
            raw = extracted
            review_fast_path_succeeded += 1
        else:
            review_fast_path_fallbacks += 1
            try:
                raw = json.loads(review_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                review_fast_path_failure_json += 1
                continue

            run_id = raw.get("run_id")
            timestamp = raw.get("timestamp")
            if not isinstance(run_id, str) or not isinstance(timestamp, str):
                review_fast_path_failure_missing_field += 1
                continue

        reviews_parsed += 1
        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        run_label = raw.get("run_label")
        cluster_count = raw.get("cluster_count", 0)

        if not isinstance(run_id, str):
            continue
        if not isinstance(timestamp, str):
            continue

        from ..datetime_utils import parse_iso_to_utc

        parsed_time = parse_iso_to_utc(timestamp)
        if parsed_time is None:
            from datetime import UTC, datetime

            parsed_time = datetime.now(UTC)

        run_entries[run_id] = {
            "run_id": run_id,
            "run_label": str(run_label) if run_label else run_id,
            "timestamp": timestamp,
            "cluster_count": cluster_count if isinstance(cluster_count, int) else 0,
            "parsed_time": parsed_time,
            "execution_count": 0,
            "reviewed_count": 0,
        }

    timings["review_fast_path_attempted"] = review_fast_path_attempted
    timings["review_fast_path_succeeded"] = review_fast_path_succeeded
    timings["review_fast_path_fallbacks"] = review_fast_path_fallbacks
    timings["review_fast_path_failure_json"] = review_fast_path_failure_json
    timings["review_fast_path_failure_missing_field"] = review_fast_path_failure_missing_field
    timings["review_fast_path_other"] = 0

    timings["reviews_parse_ms"] = (time.perf_counter() - reviews_parse_start) * 1000
    timings["reviews_glob_ms"] = (time.perf_counter() - reviews_scan_start) * 1000
    timings["reviews_parsed"] = reviews_parsed

    if include_expensive and not include_status:
        include_status = True

    if limit is not None:
        sorted_for_window = sorted(
            run_entries.values(),
            key=lambda e: cast("datetime", e["parsed_time"]),
            reverse=True,
        )
        window_ids = {cast(str, entry["run_id"]) for entry in sorted_for_window[:limit]}
    else:
        window_ids = set(run_entries.keys())

    if include_expensive:
        batch_eligibility_run_ids: set[str] = set(run_entries.keys())
    elif limit is not None:
        batch_eligibility_run_ids = window_ids
    else:
        batch_eligibility_run_ids = set()

    # === STAGE 2: Scan and row assembly ===
    (
        runs_list,
        total_discovered,
        returned_count,
        has_more,
        _,
        _,
    ) = build_runs_list_scan_stage(
        runs_dir,
        run_entries=run_entries,
        timings=timings,
        limit=limit,
        include_status=include_status,
        include_expensive=include_expensive,
        batch_eligibility_run_ids=batch_eligibility_run_ids,
    )

    timings["total_duration_ms"] = (time.perf_counter() - reviews_scan_start) * 1000

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=total_discovered,
        returnedCount=returned_count,
        hasMore=has_more,
        executionCountsComplete=include_expensive or include_status,
    )

    if _timings:
        return payload, timings
    return payload


# Re-export for backward compatibility
__all__ = [
    "_compute_batch_eligibility",
    "build_runs_list",
]