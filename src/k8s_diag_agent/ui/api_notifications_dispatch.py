"""Notifications dispatch handler for GET /api/notifications.

This module provides the dispatch handler for the notifications endpoint,
which has special caching logic based on directory mtime.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


def handle_notifications_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch handler for GET /api/notifications.

    This handler uses directory mtime-based caching to avoid rescanning
    notification files on every request.

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

    # Query notifications (uses health_dir internally)
    result = query_notifications(
        health_dir,
        kind=kind,
        cluster_label=cluster_label,
        search=search,
        limit=limit_int,
        page=page_int,
    )

    # Cache the result
    with _notifications_cache_lock:
        _notifications_cache[cache_key] = (result, dir_mtime)

    handler._send_json(result)
