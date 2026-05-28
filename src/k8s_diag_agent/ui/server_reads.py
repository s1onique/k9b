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
Runs-list payload moved to server_runs_list_payload.py. Re-exported here for
backward compatibility with existing callers.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

# Re-export from extraction modules for backward compatibility
from .server_artifact_reads import (
    _count_external_analysis_files,
    _handle_debug_routes,
    _has_batch_eligibility_index,
    _load_promotions_for_run,
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
    from .api import build_cluster_detail_payload, build_fleet_payload, build_proposals_payload, build_run_payload
    from .notifications import query_notifications
    from .server import (
        _notifications_cache,
        _notifications_cache_lock,
        _run_payload_cache,
        _run_payload_cache_lock,
        _single_flight_acquire,
        _single_flight_release,
        _single_flight_wait,
    )

    if route == "/api/runs":
        # Delegate to extraction module for artifact-read isolation
        handle_runs_list_route(handler, query)
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
            logger.warning("Failed to build notifications payload", extra={"error": str(exc)})
            payload = {
                "notifications": [],
                "error": str(exc),
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

    # All other endpoints need the context from the current (possibly selected) run
    from urllib.parse import parse_qs

    params = parse_qs(query)
    selected_run_id = params.get("run_id", [None])[0]

    context = handler._load_context(requested_run_id=selected_run_id)
    if context is None:
        return

    if route == "/api/run":
        # Full request lifecycle instrumentation
        request_received = time.perf_counter()
        request_id = f"{id(handler)}-{int(request_received * 1000000)}"

        # Read client-generated request correlation ID from request headers
        client_request_id = handler.headers.get("X-K9B-Client-Request-Id", "")

        # Emit request-start log at absolute top before any processing
        emit_structured_log(
            component="ui-run-payload",
            message="/api/run request START",
            run_id=context.run.run_id,
            run_label=context.run.run_label,
            severity="DEBUG",
            metadata={
                "path": "/api/run",
                "run_id": context.run.run_id,
                "run_label": context.run.run_label,
                "request_id": request_id,
                "client_request_id": client_request_id,
                "monotonic_received_s": round(request_received, 6),
            },
        )

        timings: dict[str, float] = {}
        timings["request_received_ms"] = 0.0  # First timing point

        provisional_key = f"/api/run:{context.run.run_id}"

        # Single-flight acquire timing
        sf_acquire_start = time.perf_counter()
        should_build, sf_result, sf_wait_start = _single_flight_acquire(provisional_key)
        timings["single_flight_acquire_ms"] = (time.perf_counter() - sf_acquire_start) * 1000

        if not should_build and sf_result is not None:
            sf_wait_ms = 0.0
            result = None
            sf_wait_duration = time.perf_counter()
            result, wait_ms = _single_flight_wait(sf_result, sf_wait_start)
            sf_wait_ms = (time.perf_counter() - sf_wait_duration) * 1000
            timings["single_flight_wait_ms"] = sf_wait_ms
            if result is not None:
                # Cache lookup timing
                cache_lookup_end = time.perf_counter()
                timings["cache_lookup_ms"] = (cache_lookup_end - request_received) * 1000
                # Response creation timing
                response_start = time.perf_counter()
                timings["response_creation_ms"] = 0.0

                emit_structured_log(
                    component="ui-run-payload",
                    message="/api/run payload served from single-flight waiter",
                    run_id=context.run.run_id,
                    run_label=context.run.run_label,
                    severity="DEBUG",
                    metadata={
                        "path": "/api/run",
                        "run_id": context.run.run_id,
                        "run_label": context.run.run_label,
                        "request_id": request_id,
                        "client_request_id": client_request_id,
                        "cache_hit": True,
                        "single_flight_acquire": "waiter",
                        "single_flight_result": "waited",
                        "single_flight_key": provisional_key[:100],
                        "single_flight_wait_ms": round(sf_wait_ms, 2),
                        "cache_lookup_ms": round(cast(float, timings.get("cache_lookup_ms", 0)), 2),
                        "response_creation_ms": round(cast(float, timings.get("response_creation_ms", 0)), 2),
                    },
                )
                timings["response_creation_ms"] = (time.perf_counter() - response_start) * 1000
                # Set timing info for access log correlation
                handler.set_request_timing(request_id, timings.get("cache_lookup_ms", 0))
                handler._send_json(result)
                return

        # Build path - instrument all phases
        ui_index_mtime = 0.0
        ui_index_read_start = time.perf_counter()
        ui_index_path = handler.runs_dir / "health" / "ui-index.json"
        if ui_index_path.exists():
            ui_index_mtime = ui_index_path.stat().st_mtime
        timings["ui_index_read_ms"] = (time.perf_counter() - ui_index_read_start) * 1000

        run_cache_key = (context.run.run_id, ui_index_mtime)

        # Cache lookup phase
        cache_lookup_start = time.perf_counter()
        with _run_payload_cache_lock:
            cached_run_payload = _run_payload_cache.get(run_cache_key)
        timings["cache_lookup_ms"] = (time.perf_counter() - cache_lookup_start) * 1000

        if cached_run_payload is not None:
            cached_payload, _ = cached_run_payload
            _single_flight_release(provisional_key, cached_payload, success=True, result_type="cached")
            total_duration = (time.perf_counter() - request_received) * 1000
            timings["total_duration_ms"] = total_duration

            emit_structured_log(
                component="ui-run-payload",
                message="/api/run payload served from cache",
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                severity="DEBUG",
                metadata={
                    "path": "/api/run",
                    "run_id": context.run.run_id,
                    "run_label": context.run.run_label,
                    "request_id": request_id,
                    "total_duration_ms": round(total_duration, 2),
                    "cache_hit": True,
                    "single_flight_acquire_ms": round(cast(float, timings.get("single_flight_acquire_ms", 0)), 2),
                    "ui_index_read_ms": round(cast(float, timings.get("ui_index_read_ms", 0)), 2),
                    "cache_lookup_ms": round(cast(float, timings.get("cache_lookup_ms", 0)), 2),
                    "single_flight_acquire": "builder",
                    "single_flight_result": "cache_hit",
                    "cache_key": str(run_cache_key)[:100],
                    "payload_bytes": len(json.dumps(cached_payload, ensure_ascii=False).encode("utf-8")),
                    "route_return_ms": round(total_duration, 2),
                },
            )
            # Set timing info for access log correlation
            handler.set_request_timing(request_id, total_duration)
            handler._send_json(cached_payload)
            return

        # Context load phase
        context_load_start = time.perf_counter()
        # NOTE: context is already loaded via handler._load_context() before this block
        timings["context_load_ms"] = (time.perf_counter() - context_load_start) * 1000

        # Promotions load phase - delegate to extraction module
        promotions_load_start = time.perf_counter()
        promotions, promotion_timings = _load_promotions_for_run(handler._health_root, context.run.run_id)
        # Copy timings from extraction module
        for key, value in promotion_timings.items():
            timings[key] = value
        timings["promotions_load_ms"] = (time.perf_counter() - promotions_load_start) * 1000
        promotions_source = cast(str, promotion_timings.get("promotions_source", "unknown"))
        promotions_index_run_id = promotion_timings.get("promotions_index_run_id")
        promotions_fallback_reason = promotion_timings.get("promotions_fallback_reason")

        # Payload build phase
        # Pass health_root to enable execution artifact overlay for worklist derivation
        # This ensures worklist reflects actual execution state from artifacts
        payload_build_start = time.perf_counter()
        run_payload = build_run_payload(context, promotions=promotions, health_root=handler._health_root)
        timings["payload_build_ms"] = (time.perf_counter() - payload_build_start) * 1000

        # JSON serialization phase
        serialize_start = time.perf_counter()
        serialized = json.dumps(run_payload, ensure_ascii=False)
        timings["serialize_ms"] = (time.perf_counter() - serialize_start) * 1000
        timings["payload_bytes"] = len(serialized.encode("utf-8"))

        # External analysis count (fast glob only, no load)
        # Delegate to extraction module for artifact-read isolation
        external_analysis_count = _count_external_analysis_files(handler._health_root, context.run.run_id)
        timings["external_analysis_files_scanned"] = external_analysis_count

        # OPTIMIZATION: Skip notification file scan for initial selected-run detail
        # Notification data is loaded via context from ui-index.json, not from individual files
        # The glob scan of 20141 files was purely for telemetry observability
        # Only scan if explicitly needed (e.g., /api/run?include_notifications=true)
        notification_scan_strategy = "skipped_default"
        timings["notification_files_scanned"] = 0
        timings["notification_scan_ms"] = 0.0
        timings["notification_records_used"] = 0

        # Cache the built payload
        with _run_payload_cache_lock:
            if len(_run_payload_cache) >= 10:
                cache_keys = list(_run_payload_cache.keys())
                oldest_cache_key = cache_keys[0]
                del _run_payload_cache[oldest_cache_key]
            _run_payload_cache[run_cache_key] = (cast(dict[str, Any], run_payload), promotions)

        _single_flight_release(provisional_key, run_payload, success=True, result_type="built")

        # Response creation phase
        response_creation_start = time.perf_counter()
        total_duration = (time.perf_counter() - request_received) * 1000
        timings["total_duration_ms"] = total_duration
        timings["response_creation_ms"] = (time.perf_counter() - response_creation_start) * 1000
        timings["route_return_ms"] = (time.perf_counter() - request_received) * 1000

        emit_structured_log(
            component="ui-run-payload",
            message="/api/run payload built with timing",
            run_id=context.run.run_id,
            run_label=context.run.run_label,
            severity="INFO",
            metadata={
                "path": "/api/run",
                "run_id": context.run.run_id,
                "run_label": context.run.run_label,
                "request_id": request_id,
                "total_duration_ms": round(cast(float, timings.get("total_duration_ms", 0)), 2),
                "single_flight_acquire_ms": round(cast(float, timings.get("single_flight_acquire_ms", 0)), 2),
                "ui_index_read_ms": round(cast(float, timings.get("ui_index_read_ms", 0)), 2),
                "cache_lookup_ms": round(cast(float, timings.get("cache_lookup_ms", 0)), 2),
                "context_load_ms": round(cast(float, timings.get("context_load_ms", 0)), 2),
                "promotions_load_ms": round(cast(float, timings.get("promotions_load_ms", 0)), 2),
                "promoted_glob_ms": round(cast(float, timings.get("promoted_glob_ms", 0)), 2),
                "promotion_glob_count": timings.get("promotion_glob_count", 0),
                "payload_build_ms": round(cast(float, timings.get("payload_build_ms", 0)), 2),
                "serialize_ms": round(cast(float, timings.get("serialize_ms", 0)), 2),
                "payload_bytes": timings.get("payload_bytes", 0),
                "external_analysis_files_scanned": timings.get("external_analysis_files_scanned", 0),
                "notification_scan_strategy": notification_scan_strategy,
                "notification_files_scanned": timings.get("notification_files_scanned", 0),
                "notification_scan_ms": round(cast(float, timings.get("notification_scan_ms", 0)), 2),
                "notification_records_used": timings.get("notification_records_used", 0),
                "promotions_count": timings.get("promotions_count", 0),
                "promotions_source": promotions_source,
                "promotions_index_run_id": promotions_index_run_id or "",
                "promotions_fallback_reason": promotions_fallback_reason or "",
                "cache_hit": False,
                "single_flight_acquire": "builder",
                "single_flight_result": "built",
                "cache_key": str(run_cache_key)[:100],
                "single_flight_key": provisional_key[:100],
                "route_return_ms": round(cast(float, timings.get("route_return_ms", 0)), 2),
            },
        )

        # Set timing info for access log correlation before sending response
        handler.set_request_timing(request_id, timings.get("route_return_ms", 0))
        handler._send_json(run_payload)
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
