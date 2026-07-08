"""Notifications dispatch handler for GET /api/notifications.

This module provides the dispatch handler for the notifications endpoint,
which has special caching logic based on directory mtime.
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


# Re-export for backwards compatibility
from .notifications_loaders import (
    _load_notification_records_optimized as _load_notification_records_optimized,
)
from .notifications_loaders import (
    _matches_search as _matches_search,
)
from .notifications_loaders import (
    _normalize_filter_value,
)
from .notifications_payloads import (
    _build_notification_entry,
)
from .notifications_payloads import (
    _notification_sort_key as _notification_sort_key,
)

DEFAULT_NOTIFICATION_LIMIT = 50


def _load_notifications_from_index(
    health_dir: Path,
    kind_filter: str | None,
    cluster_filter: str | None,
    search_term: str,
    limit_int: int | None,
    page_int: int,
) -> dict[str, object]:
    """Load notifications from ui-index.json (fast path).
    
    Returns dict with path_strategy="index_notifications_path" when successful.
    """
    ui_index_path = health_dir / "ui-index.json"
    
    if not ui_index_path.exists():
        return {"fallback_reason": "missing_index"}
    
    try:
        ui_index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"fallback_reason": "malformed_index"}
    
    notification_history = ui_index_data.get("notification_history", [])
    if not isinstance(notification_history, list):
        return {"fallback_reason": "malformed_index"}
    
    # Load notification index for fast lookups
    notification_index = ui_index_data.get("notification_index", {})
    notification_entries = notification_index.get("notifications", []) if isinstance(notification_index, dict) else []
    
    # Filter notifications based on query parameters
    filtered = []
    for entry in notification_entries:
        # Normalize entry to dict if it's a NotificationArtifact
        if hasattr(entry, "__dict__"):
            entry = entry.__dict__
        elif not isinstance(entry, dict):
            continue
        
        # Apply filters
        if kind_filter and entry.get("kind") != kind_filter:
            continue
        if cluster_filter and entry.get("cluster_label") != cluster_filter:
            continue
        if search_term:
            summary = entry.get("summary", "").lower()
            if search_term not in summary:
                continue
        
        filtered.append(entry)
    
    # Sort by timestamp (newest first) - use dict-based sort key
    def _dict_sort_key(entry: dict[str, object]) -> datetime:
        timestamp_str = entry.get("timestamp")
        if timestamp_str:
            # Try to parse the timestamp
            from ..datetime_utils import parse_iso_to_utc
            parsed = parse_iso_to_utc(timestamp_str)
            if parsed:
                return parsed
        return datetime.min.replace(tzinfo=UTC)
    
    filtered.sort(key=_dict_sort_key, reverse=True)
    
    # Calculate pagination
    limit_value = limit_int if isinstance(limit_int, int) and limit_int > 0 else DEFAULT_NOTIFICATION_LIMIT
    offset = (page_int - 1) * limit_value
    total = len(filtered)
    total_pages = max(1, math.ceil(total / limit_value)) if total else 1
    
    # Apply pagination
    sliced = filtered[offset : offset + limit_value]
    
    # Build entries with full details
    entries = []
    for entry in sliced:
        if hasattr(entry, "__dict__"):
            # Already a NotificationArtifact or similar - convert to dict
            entry = entry.__dict__
        
        # Get the artifact path for _build_notification_entry
        artifact_path_str = entry.get("artifact_path") or entry.get("path", "")
        artifact_path = Path(artifact_path_str) if artifact_path_str else None
        
        if artifact_path:
            entry = _build_notification_entry(health_dir, entry, artifact_path)
        entries.append(entry)
    
    # Emit structured log with path strategy for observability
    from ..structured_logging import emit_structured_log
    emit_structured_log(
        component="ui-notifications",
        message="/api/notifications query completed with timing",
        run_id="",
        run_label="",
        severity="DEBUG",
        metadata={
            "path": "/api/notifications",
            "path_strategy": "index_notifications_path",
            "notification_files_considered": 0,
            "notification_files_fully_parsed": 0,
            "notification_records_matched": len(filtered),
            "notification_records_returned": len(entries),
            "index_notification_count": len(notification_entries),
            "notification_files_rejected_by_metadata": 0,
            "sort_applied": 0,
            "early_termination": 0,
            "kind_filter": kind_filter or "",
            "cluster_filter": cluster_filter or "",
            "search_term": search_term[:50] if search_term else "",
            "limit": limit_value,
            "page": page_int,
        },
    )
    
    return {
        "notifications": entries,
        "total": total,
        "limit": limit_value,
        "page": page_int,
        "total_pages": total_pages,
        "notification_files_considered": 0,
        "notification_files_fully_parsed": 0,
        "notification_records_matched": len(filtered),
        "notification_records_returned": len(entries),
        "path_strategy": "index_notifications_path",
        "path_strategy_reason": None,
        "fallback_reason": None,
        "index_notification_count": len(notification_entries),
        "rows_returned": len(entries),
    }


def handle_notifications_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch handler for GET /api/notifications.

    This handler uses ui-index.json when available (fast path),
    and falls back to file scanning when the index is missing or
    when filtered requests require accurate results.

    Args:
        handler: The HTTP request handler instance
        query: Query string
        path_params: Path parameters (unused for this route)
    """
    from .notifications import query_notifications
    from .server_singleflight import _notifications_cache, _notifications_cache_lock

    # Parse query parameters
    params = parse_qs(query)

    kind = params.get("kind", [None])[0]
    cluster_label = params.get("cluster_label", [None])[0]
    search = params.get("search", [None])[0]
    limit = params.get("limit", [None])[0]
    page = params.get("page", [None])[0]

    # Parse limit and page to int if provided
    try:
        limit_int = int(limit) if limit is not None else None
    except ValueError:
        limit_int = None

    try:
        page_int = int(page) if page is not None else None
    except ValueError:
        page_int = None
    
    # Normalize page to int
    if not isinstance(page_int, int) or page_int < 1:
        page_int = 1

    # Get the runs directory
    runs_dir = getattr(handler, "runs_dir", None)
    if runs_dir is None:
        handler._send_json({"notifications": [], "total": 0, "error": "runs_dir not available"})
        return

    # Use health subdirectory (consistent with original implementation)
    health_dir = runs_dir / "health"
    notifications_dir = health_dir / "notifications"

    # Get directory mtime for cache invalidation
    try:
        dir_mtime = os.path.getmtime(notifications_dir) if notifications_dir.exists() else 0
    except OSError:
        dir_mtime = 0

    cache_key_parts = [
        f"mtime={dir_mtime}",
        f"kind={kind or ''}",
        f"cluster={cluster_label or ''}",
        f"search={search or ''}",
        f"limit={limit_int}",
        f"page={page_int}",
    ]
    cache_key = "|".join(cache_key_parts)

    # Check cache
    with _notifications_cache_lock:
        if cache_key in _notifications_cache:
            cached_payload, cached_mtime = _notifications_cache[cache_key]
            # Verify mtime hasn't changed
            if cached_mtime == dir_mtime:
                handler._send_json(cached_payload)
                return

    # Normalize filters
    kind_filter = _normalize_filter_value(kind)
    cluster_filter = _normalize_filter_value(cluster_label)
    search_term = (search or "").strip().lower()

    # Check if we should use index path:
    # - No kind filter
    # - No cluster filter
    # - No search term
    # - Page 1 (simpler pagination)
    use_index = (
        not kind_filter
        and not cluster_filter
        and not search_term
    )
    
    if use_index:
        index_result = _load_notifications_from_index(
            health_dir=health_dir,
            kind_filter=kind_filter,
            cluster_filter=cluster_filter,
            search_term=search_term,
            limit_int=limit_int,
            page_int=page_int,
        )
        
        # Check if index was successfully used (fallback_reason is None, not a string)
        if index_result.get("fallback_reason") is None and index_result.get("path_strategy") == "index_notifications_path":
            # Index was successfully used
            with _notifications_cache_lock:
                _notifications_cache[cache_key] = (index_result, dir_mtime)
            handler._send_json(index_result)
            return
        
        # Index was missing or malformed - fall through to file scanning
        # Set fallback_reason on the result we'll use from file scanning
        index_fallback_reason = index_result.get("fallback_reason")
    else:
        index_fallback_reason = None

    # Fallback: Query notifications from files
    result = query_notifications(
        health_dir,
        kind=kind,
        cluster_label=cluster_label,
        search=search,
        limit=limit_int,
        page=page_int,
    )
    
    # Add path strategy for fallback path
    result["path_strategy"] = "notification_file_fallback_path"
    
    # Set fallback_reason based on why we fell back
    if index_fallback_reason:
        result["fallback_reason"] = index_fallback_reason
    elif use_index:
        result["fallback_reason"] = None  # Index was valid, just no entries
    else:
        # We explicitly chose fallback due to filtering
        # Build descriptive reason including which filters triggered it
        filter_parts = []
        if kind_filter:
            filter_parts.append(f"kind={kind_filter}")
        if cluster_filter:
            filter_parts.append(f"cluster={cluster_filter}")
        if search_term:
            filter_parts.append("search")
        result["fallback_reason"] = "filtered_request:" + ",".join(filter_parts) if filter_parts else "filtered_request"

    # Cache the result
    with _notifications_cache_lock:
        _notifications_cache[cache_key] = (result, dir_mtime)

    handler._send_json(result)
