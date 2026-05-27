"""Read-only API handlers for the UI server.

This module contains the read-side logic extracted from server.py. Functions
here accept the request handler instance as an argument and perform no mutation.

Keep GET endpoints consistent: no endpoint URL changes, no response JSON shape
changes, no HTTP status code changes.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.

Extraction: Run-context loading moved to server_run_reads.py. Re-exported here
for backward compatibility with existing callers.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

# SECURITY: Import validation helpers for path/glob security hardening
from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

# Re-export from extraction module for backward compatibility
from .server_run_reads import _get_llm_activity_from_index, _load_ui_index_file, load_context_for_run

logger = logging.getLogger(__name__)

__all__ = [
    "_get_llm_activity_from_index",
    "_load_ui_index_file",
    "build_runs_list_payload",
    "handle_api",
    "load_context_for_run",
]


def _has_batch_eligibility_index(ui_index_path: Path) -> bool:
    """Check if ui-index.json has v2+ with batch eligibility fields.

    This is a cheap validator to ensure the index is usable for the
    batch eligibility fast path before using its mtime for cache freshness.

    Args:
        ui_index_path: Path to ui-index.json

    Returns:
        True if the index has version >= 2 and entries have batch eligibility fields
    """
    try:
        raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

    recent_summary = raw_index.get("recent_runs_summary")
    if not isinstance(recent_summary, dict):
        return False

    if recent_summary.get("version", 1) < 2:
        return False

    runs = recent_summary.get("runs")
    if not isinstance(runs, list):
        return False

    if not runs:
        # Empty runs list is valid - just means no runs yet
        return True

    first = runs[0]
    return isinstance(first, dict) and "batchEligibility" in first and "batchExecutable" in first and "batchEligibleCount" in first


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
        _runs_list_cache,
        _runs_list_cache_lock,
        _single_flight_acquire,
        _single_flight_release,
        _single_flight_wait,
    )

    if route == "/api/runs":
        # Parse query parameters for limit, include_status, and include_expensive
        from urllib.parse import parse_qs

        params = parse_qs(query)
        limit_param = params.get("limit", [None])[0]
        include_status_param = params.get("include_status", ["false"])[0]
        include_expensive_param = params.get("include_expensive", ["false"])[0]

        # Parse limit: "all" means None (return all), otherwise parse as int
        if limit_param is not None and str(limit_param).lower() == "all":
            limit_value: int | None = None
        elif limit_param is not None:
            try:
                limit_value = int(limit_param)
            except ValueError:
                limit_value = 100  # Default
        else:
            limit_value = 100  # Default

        include_status = str(include_status_param).lower() == "true"
        include_expensive = str(include_expensive_param).lower() == "true"
        include_batch_eligibility_param = params.get("include_batch_eligibility", ["false"])[0]
        include_batch_eligibility = str(include_batch_eligibility_param).lower() == "true"

        # DEBUG PARAMETER: Enable execution summary diagnostics for preprod debugging
        # This parameter is NOT included in the cache key - diagnostics are always fresh
        debug_execution_summary_param = params.get("debug_execution_summary", ["false"])[0]
        debug_execution_summary = str(debug_execution_summary_param).lower() == "true"

        # CRITICAL: Acquire single-flight FIRST, then compute cache key inside critical section
        # Include limit, include_status, include_expensive, and include_batch_eligibility in cache key for proper cache isolation
        provisional_key = f"/api/runs:{handler.runs_dir}:limit={limit_value}:status={include_status}:expensive={include_expensive}:batch_eligibility={include_batch_eligibility}"
        should_build, sf_result, sf_wait_start = _single_flight_acquire(provisional_key)

        if not should_build and sf_result is not None:
            result, wait_ms = _single_flight_wait(sf_result, sf_wait_start)
            if result is not None:
                emit_structured_log(
                    component="ui-runs-list",
                    message="/api/runs payload served from single-flight waiter",
                    run_id="",
                    run_label="",
                    severity="DEBUG",
                    metadata={
                        "path": "/api/runs",
                        "cache_hit": True,
                        "single_flight_role": "waiter",
                        "single_flight_key": provisional_key[:100],
                        "single_flight_wait_ms": round(wait_ms, 2),
                        "limit": limit_value,
                        "include_status": include_status,
                        "include_expensive": include_expensive,
                    },
                )
                handler._send_json(result)
                return

        health_root = handler.runs_dir / "health"
        cache_mtime = 0.0

        # Check if we can use the fast index path for batch eligibility
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
                else:
                    # STANDARD PATH: Use directory mtimes for cache correctness.
                    mtimes = []
                    reviews_dir = health_root / "reviews"
                    diagnostic_packs_dir = health_root / "diagnostic-packs"
                    for d in [reviews_dir, diagnostic_packs_dir]:
                        if d.exists():
                            mtimes.append(d.stat().st_mtime)
                    # external-analysis mtime is needed for batch eligibility derivation
                    if include_status or include_expensive or include_batch_eligibility:
                        external_analysis_dir = health_root / "external-analysis"
                        if external_analysis_dir.exists():
                            mtimes.append(external_analysis_dir.stat().st_mtime)
                    if mtimes:
                        cache_mtime = max(mtimes)
            except OSError:
                pass

        runs_cache_key = f"{handler.runs_dir}:{cache_mtime}:limit={limit_value}:status={include_status}:expensive={include_expensive}:batch_eligibility={include_batch_eligibility}"

        with _runs_list_cache_lock:
            cached = _runs_list_cache.get(runs_cache_key)
            if cached is not None:
                cached_payload, cached_mtime = cached
                if cached_mtime == cache_mtime:
                    _single_flight_release(provisional_key, cached_payload, success=True, result_type="cached")
                    emit_structured_log(
                        component="ui-runs-list",
                        message="/api/runs payload served from cache",
                        run_id="",
                        run_label="",
                        severity="DEBUG",
                        metadata={
                            "path": "/api/runs",
                            "request_outcome": "cache_hit",
                            "single_flight_acquire": "builder",
                            "single_flight_result": "cache_hit",
                            "cache_key": runs_cache_key[:100],
                            "limit": limit_value,
                            "include_status": include_status,
                            "include_expensive": include_expensive,
                            "include_batch_eligibility": include_batch_eligibility,
                        },
                    )
                    handler._send_json(cached_payload)
                    return

        runs_payload = build_runs_list_payload(handler, limit=limit_value, include_status=include_status, include_expensive=include_expensive, include_batch_eligibility=include_batch_eligibility)

        # Add debug diagnostics if requested (not cached - always fresh)
        # Debug is gated by environment variable K9B_ENABLE_DEBUG_ENDPOINTS=true
        import os
        if debug_execution_summary and os.environ.get("K9B_ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true":
            from .api_debug import build_execution_summary_diagnostics
            health_root = handler.runs_dir / "health"
            # Get first run_id from runs list for diagnostics
            runs_list = runs_payload.get("runs", [])
            if runs_list and isinstance(runs_list, list):
                first_run_id = runs_list[0].get("runId", "") if runs_list else ""
                if first_run_id:
                    diagnostic = build_execution_summary_diagnostics(first_run_id, health_root, debug_flag=True)
                    if diagnostic:
                        runs_payload["_debug_execution_summary"] = diagnostic

        _single_flight_release(provisional_key, runs_payload, success=True, result_type="built")

        handler._send_json(runs_payload)
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

        # Promotions load phase - OPTIMIZED to use index instead of file glob
        promotions_load_start = time.perf_counter()
        timings["promoted_glob_ms"] = 0.0  # No longer doing glob
        timings["promotion_glob_count"] = 0  # No longer doing glob

        # Load promotions from ui-index.json with run_id validation
        promotions_index: Mapping[str, object] | None = None
        promotions_source = "file_scan"
        promotions_index_run_id: str | None = None
        promotions_fallback_reason: str | None = None

        try:
            index = _load_ui_index_file(handler._health_root)
            raw_promotions_index = index.get("promotions_index")
            if isinstance(raw_promotions_index, Mapping):
                # Validate shape - must have run_id field for run-scoped correctness
                if "run_id" not in raw_promotions_index:
                    promotions_fallback_reason = "missing_run_id_field"
                else:
                    promotions_index = raw_promotions_index
                    promotions_index_run_id = str(raw_promotions_index.get("run_id") or "")
                    # CRITICAL: Validate run_id matches selected run to prevent cross-run data leakage
                    if promotions_index_run_id != context.run.run_id:
                        promotions_fallback_reason = f"run_id_mismatch:{promotions_index_run_id}!={context.run.run_id}"
                        promotions_index = None
                    elif not isinstance(raw_promotions_index.get("promotions"), list):
                        promotions_fallback_reason = "invalid_promotions_shape"
                        promotions_index = None
        except Exception as exc:
            promotions_fallback_reason = f"index_load_error:{exc}"
            promotions_index = None

        if promotions_index is not None:
            # Use index-backed promotions (instant)
            raw_promotions = promotions_index.get("promotions", [])
            promotions = list(cast(list[dict[str, object]], raw_promotions)) if isinstance(raw_promotions, list) else []
            promotions_source = "index"
        else:
            # CRITICAL: Do NOT probe external-analysis when index is missing/mismatched
            # Even bounded iterdir() costs 1.5-2.7s on large directories, which blocks /api/run
            # Return empty promotions with explicit reason so operator can regenerate index
            if promotions_fallback_reason is None:
                promotions_fallback_reason = "missing_promotions_index"

            promotions = []
            promotions_source = "skipped_missing_index"
            timings["promoted_glob_ms"] = 0.0
            timings["promotion_glob_count"] = 0

        timings["promotions_load_ms"] = (time.perf_counter() - promotions_load_start) * 1000
        timings["promotions_count"] = len(promotions)
        timings["promotions_source"] = promotions_source  # type: ignore[assignment]
        timings["promotions_index_run_id"] = promotions_index_run_id or ""  # type: ignore[assignment]
        if promotions_fallback_reason:
            timings["promotions_fallback_reason"] = promotions_fallback_reason  # type: ignore[assignment]

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
        # SECURITY: run_id validated by validate_run_id() before glob construction
        # NOTE: F823 false positive - imports are at module level, ruff misidentifies scope
        external_analysis_dir = handler._health_root / "external-analysis"
        external_analysis_count = 0
        if external_analysis_dir.exists():
            try:
                validated_run_id = validate_run_id(context.run.run_id)  # noqa: F823
                glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
                external_analysis_count = len(list(external_analysis_dir.glob(glob_pattern)))
            except SecurityError:  # noqa: F823
                # Safe fallback: return 0 on invalid run_id
                external_analysis_count = 0
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

    # Debug endpoint: /api/debug/runs/{run_id}/execution-summary
    # Only enabled when K9B_ENABLE_DEBUG_ENDPOINTS=true
    if route.startswith("/api/debug/runs/"):
        import os
        import re as regex_module

        if os.environ.get("K9B_ENABLE_DEBUG_ENDPOINTS", "false").lower() != "true":
            handler._send_json({"error": "Debug endpoints disabled - set K9B_ENABLE_DEBUG_ENDPOINTS=true to enable"})
            return

        # Match execution-state-bundle endpoint
        bundle_match = regex_module.match(r"^/api/debug/runs/([^/]+)/execution-state-bundle$", route)
        if bundle_match:
            run_id = bundle_match.group(1)
            health_root = handler.runs_dir / "health"
            from .api_debug import build_execution_state_bundle

            try:
                validate_run_id(run_id)
            except SecurityError:
                handler._send_json({"error": "Invalid run_id format"})
                return

            bundle_bytes = build_execution_state_bundle(run_id, health_root)
            if bundle_bytes is None:
                handler._send_json({"error": "Debug diagnostics disabled"})
                return

            # Send ZIP response (only call _send_bytes - it sets status internally)
            handler._send_bytes(
                bundle_bytes,
                content_type="application/zip",
                filename=f"k9b-execution-state-diagnostics-{run_id}.zip",
            )
            return

        # Match execution-summary endpoint
        match = regex_module.match(r"^/api/debug/runs/([^/]+)/execution-summary$", route)
        if match:
            run_id = match.group(1)
            health_root = handler.runs_dir / "health"
            from .api_debug import build_execution_summary_diagnostics

            diagnostic = build_execution_summary_diagnostics(run_id, health_root, debug_flag=True)
            if diagnostic:
                handler._send_json(diagnostic)
            else:
                handler._send_json({"error": "Diagnostics disabled"})
            return

    # Debug diagnostics enabled flag: GET /api/debug/diagnostics-enabled
    if route == "/api/debug/diagnostics-enabled":
        from .api_debug import is_debug_diagnostics_enabled

        handler._send_json({
            "debugExecutionDiagnosticsEnabled": is_debug_diagnostics_enabled()
        })
        return

    handler._send_text(404, "Not Found")


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
    from ..structured_logging import emit_structured_log
    from .api import build_runs_list

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
        payload = {"runs": [], "error": str(exc)}
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
