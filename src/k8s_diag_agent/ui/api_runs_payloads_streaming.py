"""Review-file streaming fallback for runs-list when index is unavailable.

This module contains the fallback path for scanning review files directly
when ui-index.json is absent, malformed, or lacks recent_runs_summary.

Ownership reminder:
    - TypedDict payload classes live in api_payloads.py (the contract module).
    - Serializer functions (_serialize_*) and public builders live here.
    - Do not add new TypedDict definitions here; add them to api_payloads.py.
"""

from __future__ import annotations

import json

# Use the original logger name for compatibility
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ..datetime_utils import parse_iso_to_utc
from .api_payloads import (
    RunsListEntry,
    RunsListPayload,
    RunsListTimings,
)
from .api_runs_payloads_review import _derive_review_status, _extract_review_metadata_streaming

logger = logging.getLogger("k8s_diag_agent.ui.api")


def _build_runs_list_review_streaming(
    runs_dir: Path,
    limit: int | None,
    timings: RunsListTimings,
    start_time: float,
) -> RunsListPayload:
    """Fallback path that scans review files directly.

    Used when ui-index.json is absent, malformed, or lacks recent_runs_summary.

    Args:
        runs_dir: Path to the runs directory
        limit: Maximum number of runs to return
        timings: Timings dict (modified in place)
        start_time: Start time from perf_counter

    Returns:
        RunsListPayload (caller wraps with timings if needed)
    """
    run_health_dir = runs_dir / "health"
    reviews_dir = run_health_dir / "reviews"

    # Scan review files
    reviews_scan_start = time.perf_counter()
    run_entries: dict[str, dict[str, object]] = {}
    reviews_parsed = 0

    if reviews_dir.is_dir():
        review_files = list(reviews_dir.glob("*-review.json"))
    else:
        review_files = []

    timings["reviews_glob_ms"] = (time.perf_counter() - reviews_scan_start) * 1000
    timings["reviews_files_found"] = len(review_files)

    # Parse review files
    reviews_parse_start = time.perf_counter()
    for review_path in review_files:
        run_label: str | None = None
        cluster_count = 0

        # Try ijson streaming fast-path first
        extracted = _extract_review_metadata_streaming(review_path)
        if extracted is not None:
            run_id = cast(str, extracted.get("run_id"))
            timestamp = cast(str, extracted.get("timestamp"))
            run_label = cast(str | None, extracted.get("run_label"))
            cluster_count = cast(int, extracted.get("cluster_count", 0) or 0)
        else:
            # Fall back to full JSON parse
            try:
                raw = json.loads(review_path.read_text(encoding="utf-8"))
                run_id = raw.get("run_id")
                timestamp = raw.get("timestamp")
                run_label = raw.get("run_label")
                cluster_count = raw.get("cluster_count", 0) or 0
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Skipped malformed review artifact in streaming fallback: artifact=%s, error=%s",
                    review_path.name,
                    str(exc),
                    exc_info=True,
                )
                continue

        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue

        parsed_time = parse_iso_to_utc(timestamp)
        if parsed_time is None:
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
        reviews_parsed += 1

    timings["reviews_parse_ms"] = (time.perf_counter() - reviews_parse_start) * 1000
    timings["reviews_parsed"] = reviews_parsed

    # Sort all entries by timestamp descending
    sorted_entries = sorted(run_entries.values(), key=lambda e: cast(datetime, e["parsed_time"]), reverse=True)
    timings["sort_ms"] = (time.perf_counter() - start_time) * 1000
    timings["rows_considered"] = len(sorted_entries)

    # Window selection
    rows_to_return = min(limit, len(sorted_entries)) if limit is not None else len(sorted_entries)
    timings["rows_returned"] = rows_to_return

    # SUPER FAST PATH: Skip batch eligibility computation entirely
    timings["batch_plan_files_found"] = 0
    timings["batch_exec_files_found"] = 0
    timings["batch_eligibility_prescan_ms"] = 0.0
    timings["execution_files_parsed"] = 0
    timings["execution_files_skipped_outside_window"] = 0
    timings["per_run_glob_calls"] = 0
    timings["per_run_directory_list_calls"] = 0

    # Build runs list
    runs_list: list[RunsListEntry] = []
    entries_to_build = sorted_entries[:rows_to_return] if limit is not None else sorted_entries

    for entry in entries_to_build:
        execution_count = cast(int, entry.get("execution_count", 0))
        reviewed_count = cast(int, entry.get("reviewed_count", 0))
        review_status = _derive_review_status(execution_count, reviewed_count)
        triaged = execution_count > 0 and reviewed_count > 0

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
                reviewDownloadPath=None,
                batchEligibility="unknown",
                batchExecutable=False,
                batchEligibleCount=0,
                executionSummary=None,
            )
        )

    timings["row_assembly_ms"] = (time.perf_counter() - start_time) * 1000
    timings["rows_built"] = len(runs_list)

    # Build payload
    total_discovered = len(run_entries)
    returned_count = len(runs_list)
    has_more = total_discovered > returned_count

    payload = RunsListPayload(
        runs=runs_list,
        totalCount=total_discovered,
        returnedCount=returned_count,
        hasMore=has_more,
        executionCountsComplete=False,
    )

    timings["total_duration_ms"] = (time.perf_counter() - start_time) * 1000

    return payload