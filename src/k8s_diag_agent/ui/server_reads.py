"""Read-only API handlers for the UI server.

This module contains the read-side logic extracted from server.py. Functions
here accept the request handler instance as the argument and perform no mutation.

Keep GET endpoints consistent: no endpoint URL changes, no response JSON shape
changes, no HTTP status code changes.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.

Extraction: Run-context loading moved to server_run_reads.py. Debug/batch handlers
moved to server_artifact_reads.py. /api/runs route moved to server_runs_list_reads.py.
Runs-list payload moved to server_runs_list_payload.py. Selected-run detail handler
moved to server_run_detail_reads.py. Re-exported here for backward compatibility
with existing callers.
"""

from __future__ import annotations

import logging
import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

# Re-export from extraction modules for backward compatibility
from .server_artifact_reads import (
    _handle_debug_routes,
    _has_batch_eligibility_index,
)
from .server_run_reads import _get_llm_activity_from_index, _load_ui_index_file, load_context_for_run
from .server_runs_list_payload import build_runs_list_payload
from .server_runs_list_reads import handle_runs_list_route

logger = logging.getLogger(__name__)

__all__ = [
    "_get_llm_activity_from_index",
    "_has_batch_eligibility_index",
    "_load_ui_index_file",
    "build_runs_list_payload",
    "handle_api",
    "handle_runs_list_route",
    "load_context_for_run",
]


def handle_runtime_status_route(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/runtime-status route.

    Args:
        handler: The HTTP request handler instance
    """
    from .api_runtime_status import handle_runtime_status_route as _handle

    _handle(handler)


def handle_api(handler: HealthUIRequestHandler, route: str, query: str) -> None:
    """Handle API GET requests (read-only endpoints).

    This is the top-level GET dispatcher extracted from server.py's _handle_api.
    All cache/single-flight logic is preserved inline here since it needs access
    to handler state.

    Args:
        handler: The HealthUIRequestHandler instance
        route: The request path without query string
        query: The query string
    """
    # Import here to avoid circular import at module level
    from ..structured_logging import emit_structured_log
    from .api import build_cluster_detail_payload, build_fleet_payload, build_proposals_payload
    from .notifications import query_notifications
    from .server import (
        _single_flight_acquire,
        _single_flight_release,
        _single_flight_wait,
    )
    from .server_incident_reads import handle_incident_routes
    from .server_singleflight import (
        _notifications_cache,
        _notifications_cache_lock,
    )

    if route == "/api/runs":
        # Delegate to extraction module for artifact-read isolation
        handle_runs_list_route(handler, query)
        return

    if route == "/api/runtime-status":
        # Runtime status does not need run context - handles its own route
        handle_runtime_status_route(handler)
        return

    if route == "/api/notifications":
        from urllib.parse import parse_qs

        params = parse_qs(query)
        notifications_dir = handler.runs_dir / "health" / "notifications"

        kind_filter = params.get("kind", [None])[0] or ""
        cluster_filter = params.get("cluster_label", [None])[0] or ""
        search_filter = params.get("search", [None])[0] or ""
        limit_value = handler._parse_limit(params.get("limit", [None])[0])
        page_value = handler._parse_page(params.get("page", [None])[0])

        # Normalize limit/page for cache key
        limit_str = str(limit_value if limit_value is not None else 50)
        page_str = str(page_value if page_value is not None else 1)

        cache_mtime = 0.0
        index_mtime = 0.0
        if notifications_dir.exists():
            try:
                cache_mtime = notifications_dir.stat().st_mtime
            except OSError:
                pass
        ui_index_path = handler.runs_dir / "health" / "ui-index.json"
        if ui_index_path.exists():
            try:
                index_mtime = ui_index_path.stat().st_mtime
            except OSError:
                pass

        notifications_cache_key = f"{cache_mtime}:{index_mtime}:{kind_filter}:{cluster_filter}:{search_filter}:{limit_str}:{page_str}"
        sf_key = f"/api/notifications:{notifications_cache_key}"
        should_build, sf_result, sf_wait_start = _single_flight_acquire(sf_key)

        if not should_build and sf_result is not None:
            result, wait_ms = _single_flight_wait(sf_result, sf_wait_start)
            if result is not None:
                emit_structured_log(
                    component="ui-notifications",
                    message="/api/notifications payload served from single-flight waiter",
                    run_id="",
                    run_label="",
                    severity="DEBUG",
                    metadata={
                        "path": "/api/notifications",
                        "cache_hit": True,
                        "single_flight_acquire": "waiter",
                        "single_flight_result": "waited",
                        "single_flight_key": sf_key[:100],
                        "single_flight_wait_ms": round(wait_ms, 2),
                        "cache_key": notifications_cache_key[:50],
                    },
                )
                handler._send_json(result)
                return

        with _notifications_cache_lock:
            notifications_cached = _notifications_cache.get(notifications_cache_key)
            if notifications_cached is not None:
                notifications_payload, notifications_mtime = notifications_cached
                if notifications_mtime == cache_mtime:
                    if should_build:
                        _single_flight_release(sf_key, notifications_payload, success=True, result_type="cached")
                    emit_structured_log(
                        component="ui-notifications",
                        message="/api/notifications payload served from cache",
                        run_id="",
                        run_label="",
                        severity="DEBUG",
                        metadata={
                            "path": "/api/notifications",
                            "request_outcome": "cache_hit",
                            "single_flight_acquire": "builder",
                            "single_flight_result": "cache_hit",
                            "cache_key": notifications_cache_key[:50],
                        },
                    )
                    handler._send_json(notifications_payload)
                    return

        # Try index path first for default request shape
        # Default shape: no filters, page=1, limit=50
        is_default_request = not kind_filter and not cluster_filter and not search_filter
        effective_limit = limit_value if limit_value is not None else 50
        effective_page = page_value if page_value is not None else 1
        effective_offset = (effective_page - 1) * effective_limit

        path_strategy = "unknown"
        fallback_reason: str | None = None
        notification_files_considered = 0
        notification_files_fully_parsed = 0
        index_notification_count = 0
        rows_returned = 0
        total_duration_ms = 0.0

        payload_start = time.perf_counter()

        # Check if we can use the index path
        if is_default_request:
            ui_index_path = handler.runs_dir / "health" / "ui-index.json"
            if ui_index_path.exists():
                try:
                    index = _load_ui_index_file(handler.runs_dir / "health")
                    notif_index = index.get("notification_index")
                    if notif_index is not None:
                        # Use index path - no file parsing needed
                        path_strategy = "index_notifications_path"
                        index_notifications = notif_index.get("notifications", [])
                        index_total_count = notif_index.get("total_count", len(index_notifications))
                        index_notification_count = len(index_notifications)

                        # Apply pagination
                        sliced = index_notifications[effective_offset : effective_offset + effective_limit]
                        rows_returned = len(sliced)

                        total_pages = max(1, math.ceil(index_total_count / effective_limit)) if index_total_count else 1

                        payload = {
                            "notifications": sliced,
                            "total": index_total_count,
                            "limit": effective_limit,
                            "page": effective_page,
                            "total_pages": total_pages,
                            "path_strategy": path_strategy,
                            "fallback_reason": None,
                            "notification_files_considered": 0,
                            "notification_files_fully_parsed": 0,
                            "index_notification_count": index_notification_count,
                            "rows_returned": rows_returned,
                        }
                        total_duration_ms = (time.perf_counter() - payload_start) * 1000

                        emit_structured_log(
                            component="ui-notifications",
                            message="/api/notifications served from index",
                            run_id="",
                            run_label="",
                            severity="DEBUG",
                            metadata={
                                "path": "/api/notifications",
                                "path_strategy": path_strategy,
                                "notification_files_considered": 0,
                                "notification_files_fully_parsed": 0,
                                "index_notification_count": index_notification_count,
                                "rows_returned": rows_returned,
                                "total_duration_ms": round(total_duration_ms, 2),
                                "limit": effective_limit,
                                "page": effective_page,
                            },
                        )

                        with _notifications_cache_lock:
                            if len(_notifications_cache) >= 10:
                                oldest_key = next(iter(_notifications_cache))
                                del _notifications_cache[oldest_key]
                            _notifications_cache[notifications_cache_key] = (payload, cache_mtime)

                        if should_build:
                            _single_flight_release(sf_key, payload, success=True, result_type="built")

                        handler._send_json(payload)
                        return
                    else:
                        # Index exists but no notification_index field
                        path_strategy = "notification_file_fallback_path"
                        fallback_reason = "missing_notification_index"
                except Exception as exc:
                    # Malformed index
                    path_strategy = "notification_file_fallback_path"
                    fallback_reason = "malformed_index"
                    logger.debug(
                        "Failed to load ui-index for notifications, falling back to file scan",
                        extra={"error": str(exc)},
                    )
            else:
                # No ui-index.json
                path_strategy = "notification_file_fallback_path"
                fallback_reason = "missing_index"
        else:
            # Filtered request - cannot use index path yet
            path_strategy = "notification_file_fallback_path"
            fallback_reason = "unsupported_filter:" + ":".join(
                filter(
                    None,
                    [
                        "kind" if kind_filter else None,
                        "cluster_label" if cluster_filter else None,
                        "search" if search_filter else None,
                    ],
                )
            )

        # Fallback: use file scan
        if notifications_dir.exists():
            notification_files_considered = len(list(notifications_dir.glob("*.json")))

        try:
            file_payload = query_notifications(
                handler.runs_dir / "health",
                kind=kind_filter if kind_filter else None,
                cluster_label=cluster_filter if cluster_filter else None,
                search=search_filter if search_filter else None,
                limit=limit_value,
                page=page_value,
            )
            notification_files_fully_parsed = file_payload.get("notification_files_fully_parsed", 0)

            # Add strategy/timing fields
            file_payload["path_strategy"] = path_strategy
            file_payload["fallback_reason"] = fallback_reason
            file_payload["notification_files_considered"] = notification_files_considered
            file_payload["notification_files_fully_parsed"] = notification_files_fully_parsed
            file_payload["index_notification_count"] = 0  # Not used in fallback
            file_payload["rows_returned"] = len(file_payload.get("notifications", []))

            payload = file_payload
        except Exception as exc:
            from ..security import sanitize_exception_message

            logger.warning("Failed to build notifications payload", extra={"error": str(exc)})
            payload = {
                "notifications": [],
                "error": sanitize_exception_message(exc),
                "path_strategy": path_strategy,
                "fallback_reason": fallback_reason or "exception",
                "notification_files_considered": notification_files_considered,
                "notification_files_fully_parsed": 0,
                "index_notification_count": 0,
                "rows_returned": 0,
            }

        total_duration_ms = (time.perf_counter() - payload_start) * 1000
        payload["total_duration_ms"] = round(total_duration_ms, 2)

        emit_structured_log(
            component="ui-notifications",
            message="/api/notifications payload built with timing",
            run_id="",
            run_label="",
            severity="DEBUG",
            metadata={
                "path": "/api/notifications",
                "path_strategy": path_strategy,
                "fallback_reason": fallback_reason,
                "notification_files_considered": notification_files_considered,
                "notification_files_fully_parsed": notification_files_fully_parsed,
                "index_notification_count": 0,
                "rows_returned": len(payload.get("notifications", [])),
                "total_duration_ms": round(total_duration_ms, 2),
            },
        )

        with _notifications_cache_lock:
            if len(_notifications_cache) >= 10:
                oldest_key = next(iter(_notifications_cache))
                del _notifications_cache[oldest_key]
            _notifications_cache[notifications_cache_key] = (payload, cache_mtime)

        if should_build:
            _single_flight_release(sf_key, payload, success=True, result_type="built")

        handler._send_json(payload)
        return

    # Incident read routes (no context required) - dispatch before context loading
    if route.startswith("/api/incidents"):
        if handle_incident_routes(handler, route, query):
            return

    # All other endpoints need the context from the current (possibly selected) run
    from urllib.parse import parse_qs

    params = parse_qs(query)
    selected_run_id = params.get("run_id", [None])[0]

    context = handler._load_context(requested_run_id=selected_run_id)
    if context is None:
        return

    if route == "/api/run":
        # Delegate to extraction module for selected-run detail isolation
        from .server_run_detail_reads import handle_run_detail_route

        handle_run_detail_route(handler, query)
        return

    if route == "/api/fleet":
        handler._send_json(build_fleet_payload(context))
        return

    if route == "/api/proposals":
        handler._send_json(build_proposals_payload(context))
        return

    if route == "/api/cluster-detail":
        from urllib.parse import parse_qs

        params = parse_qs(query)
        label = params.get("cluster_label", [None])[0]
        handler._send_json(build_cluster_detail_payload(context, cluster_label=label))
        return

    # Debug routes: delegate to extraction module
    if _handle_debug_routes(handler, route):
        return

    handler._send_text(404, "Not Found")
