"""Notification history helpers for the UI server."""

from __future__ import annotations

import math
import time as time_module
from pathlib import Path
from typing import Any

from ..structured_logging import emit_structured_log

# Re-export loaders for backward compatibility
from .notifications_loaders import (  # noqa: F401 - re-exported for backward compatibility
    _count_matching_records,
    _detail_entries,
    _load_notification_records,
    _load_notification_records_optimized,
    _matches_search,
    _normalize_filter_value,
    _stringify_value,
)

# Re-export payload helpers for backward compatibility
from .notifications_payloads import (  # noqa: F401 - re-exported for backward compatibility
    _build_notification_entry,
    _notification_sort_key,
    _parse_timestamp,
    _relative_path,
)

DEFAULT_NOTIFICATION_LIMIT = 50

# Logging component identifier
_COMPONENT = "ui-notifications"


def query_notifications(
    root_dir: Path,
    *,
    kind: str | None = None,
    cluster_label: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    """Return a newest-first slice of retained notifications with filtering."""
    total_start = time_module.perf_counter()
    
    # Counters for observability
    counters: dict[str, int] = {
        "notification_files_considered": 0,
        "notification_files_rejected_by_metadata": 0,
        "notification_files_fully_parsed": 0,
        "notification_records_matched": 0,
        "notification_records_returned": 0,
        "early_termination": 0,
    }

    notifications_dir = root_dir / "notifications"
    
    # Pre-normalize filters
    kind_filter = _normalize_filter_value(kind)
    cluster_filter = _normalize_filter_value(cluster_label)
    search_term = (search or "").strip().lower()
    
    # Compute limit and page
    limit_value = limit if isinstance(limit, int) and limit > 0 else DEFAULT_NOTIFICATION_LIMIT
    page_value = page if isinstance(page, int) and page > 0 else 1
    offset = (page_value - 1) * limit_value
    
    # Determine if we can use early termination optimization
    # Safe when: no cluster filter, no search term, page 1
    # For other cases, we need full scan for accurate total
    use_early_termination = (
        page_value == 1 
        and not cluster_filter 
        and not search_term
    )
    needed_for_page1 = offset + limit_value if use_early_termination else None
    
    # Timing: load phase - optimized with early termination for common case
    load_start = time_module.perf_counter()
    records, preliminary_count = _load_notification_records_optimized(
        notifications_dir,
        kind_filter=kind_filter,
        cluster_filter=cluster_filter,
        search_term=search_term,
        counters=counters,
        max_records=needed_for_page1,
    )
    load_duration_ms = (time_module.perf_counter() - load_start) * 1000
    
    # If early termination was used but we need accurate total, do count pass
    # This happens when early_termination was triggered but caller needs exact total
    if counters.get("early_termination") and not use_early_termination:
        # This case shouldn't happen as use_early_termination controls max_records
        pass
    elif counters.get("early_termination"):
        # Early termination was used - need count pass for accurate total
        count_start = time_module.perf_counter()
        total_count = _count_matching_records(
            notifications_dir,
            kind_filter=kind_filter,
            cluster_filter=cluster_filter,
            search_term=search_term,
        )
        count_duration_ms = (time_module.perf_counter() - count_start) * 1000
        # Add count timing to load for reporting
        load_duration_ms = load_duration_ms + count_duration_ms
        counters["count_pass_duration_ms"] = int(round(count_duration_ms, 2))
    else:
        # No early termination - preliminary count is accurate
        total_count = preliminary_count
    
    # Timing: filter phase (now lightweight - records already filtered during load)
    filter_start = time_module.perf_counter()
    # Records already filtered during load - just count them
    filtered = records
    filter_duration_ms = (time_module.perf_counter() - filter_start) * 1000
    counters["notification_records_matched"] = len(filtered)
    
    # Timing: sort phase - skip if already sorted by filename (newest first)
    sort_start = time_module.perf_counter()
    # Files are already processed in reverse chronological order (newest first)
    # Only need to sort if we have search term or complex filters that might have
    # disrupted order
    needs_sort = bool(search_term or cluster_filter)
    if needs_sort:
        filtered.sort(key=_notification_sort_key, reverse=True)
    sort_duration_ms = (time_module.perf_counter() - sort_start) * 1000
    counters["sort_applied"] = 1 if needs_sort else 0
    
    # Timing: pagination phase
    paginate_start = time_module.perf_counter()
    # Use total_count if we did count pass (accurate), otherwise len(filtered)
    total = total_count if counters.get("early_termination") else len(filtered)
    sliced = filtered[offset : offset + limit_value]
    
    # Timing: payload build phase
    payload_build_start = time_module.perf_counter()
    entries = [
        _build_notification_entry(root_dir, artifact, path)
        for artifact, path in sliced
    ]
    payload_build_duration_ms = (time_module.perf_counter() - payload_build_start) * 1000
    counters["notification_records_returned"] = len(entries)
    paginate_duration_ms = (time_module.perf_counter() - paginate_start) * 1000
    
    total_pages = max(1, math.ceil(total / limit_value)) if total else 1
    total_duration_ms = (time_module.perf_counter() - total_start) * 1000
    
    # Determine path strategy for observability
    # early_termination=1 means index was used (records loaded from index, then count pass done)
    # early_termination=0 means full scan/fallback was used (had to scan files for accurate results)
    path_strategy = "index_notifications_path" if counters.get("early_termination") else "notification_file_fallback_path"
    path_strategy_reason = None if path_strategy == "index_notifications_path" else "full_scan_required"

    result = {
        "notifications": entries,
        "total": total,
        "limit": limit_value,
        "page": page_value,
        "total_pages": total_pages,
        # Include counters for route-level telemetry
        "notification_files_considered": counters["notification_files_considered"],
        "notification_files_fully_parsed": counters["notification_files_fully_parsed"],
        "notification_records_matched": counters["notification_records_matched"],
        "notification_records_returned": counters["notification_records_returned"],
        # Path strategy for distinguishing index vs fallback behavior
        "path_strategy": path_strategy,
        "path_strategy_reason": path_strategy_reason,
    }
    
    # Emit structured log with timing breakdown
    emit_structured_log(
        component=_COMPONENT,
        message="/api/notifications query completed with timing",
        run_id="",
        run_label="",
        severity="DEBUG",
        metadata={
            "path": "/api/notifications",
            "total_duration_ms": round(total_duration_ms, 2),
            "load_duration_ms": round(load_duration_ms, 2),
            "filter_duration_ms": round(filter_duration_ms, 2),
            "sort_duration_ms": round(sort_duration_ms, 2),
            "paginate_duration_ms": round(paginate_duration_ms, 2),
            "payload_build_duration_ms": round(payload_build_duration_ms, 2),
            # Counters
            "notification_files_considered": counters["notification_files_considered"],
            "notification_files_rejected_by_metadata": counters["notification_files_rejected_by_metadata"],
            "notification_files_fully_parsed": counters["notification_files_fully_parsed"],
            "notification_records_matched": counters["notification_records_matched"],
            "notification_records_returned": counters["notification_records_returned"],
            # Additional telemetry
            "sort_applied": counters.get("sort_applied", 0),
            "early_termination": counters.get("early_termination", 0),
            # Query params for correlation
            "kind_filter": kind_filter,
            "cluster_filter": cluster_filter,
            "search_term": search_term[:50] if search_term else "",
            "limit": limit_value,
            "page": page_value,
        },
    )
    
    return result
