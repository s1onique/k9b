"""Read-only API handlers for the UI server.

This module contains the read-side logic extracted from server.py. Functions
here accept the request handler instance as an argument and perform no mutation.

Keep GET endpoints consistent: no endpoint URL changes, no response JSON shape
changes, no HTTP status code changes.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.
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

logger = logging.getLogger(__name__)


def _load_ui_index_file(health_root: Path) -> dict[str, object]:
    """Load ui-index.json from health root directory.

    This is a local helper to avoid importing load_ui_index from ui.model,
    which would create a circular import back into ui.server_reads.

    Args:
        health_root: Path to the health directory containing ui-index.json

    Returns:
        The parsed ui-index.json contents as a dict

    Raises:
        FileNotFoundError: If ui-index.json doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    index_path = health_root / "ui-index.json"
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return cast(dict[str, object], raw)
    # If not a dict (edge case), return empty dict
    return {}


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
    from ..external_analysis.deterministic_next_check_promotion import collect_promoted_queue_entries
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

        # CRITICAL: Acquire single-flight FIRST, then compute cache key inside critical section
        # Include limit, include_status, and include_expensive in cache key for proper cache isolation
        provisional_key = f"/api/runs:{handler.runs_dir}:limit={limit_value}:status={include_status}:expensive={include_expensive}"
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
        if health_root.exists():
            try:
                reviews_dir = health_root / "reviews"
                external_analysis_dir = health_root / "external-analysis"
                diagnostic_packs_dir = health_root / "diagnostic-packs"
                mtimes = []
                for d in [reviews_dir, external_analysis_dir, diagnostic_packs_dir]:
                    if d.exists():
                        mtimes.append(d.stat().st_mtime)
                if mtimes:
                    cache_mtime = max(mtimes)
            except OSError:
                pass

        runs_cache_key = f"{handler.runs_dir}:{cache_mtime}:limit={limit_value}:status={include_status}:expensive={include_expensive}"

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
                        },
                    )
                    handler._send_json(cached_payload)
                    return

        runs_payload = build_runs_list_payload(handler, limit=limit_value, include_status=include_status, include_expensive=include_expensive)

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
                filter(None, [
                    "kind" if kind_filter else None,
                    "cluster_label" if cluster_filter else None,
                    "search" if search_filter else None,
                ])
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
                        "cache_hit": True,
                        "single_flight_acquire": "waiter",
                        "single_flight_result": "waited",
                        "single_flight_key": provisional_key[:100],
                        "single_flight_wait_ms": round(sf_wait_ms, 2),
                        "cache_lookup_ms": round(timings.get("cache_lookup_ms", 0), 2),
                        "response_creation_ms": round(timings.get("response_creation_ms", 0), 2),
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
                    "single_flight_acquire_ms": round(timings.get("single_flight_acquire_ms", 0), 2),
                    "ui_index_read_ms": round(timings.get("ui_index_read_ms", 0), 2),
                    "cache_lookup_ms": round(timings.get("cache_lookup_ms", 0), 2),
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
            # Fallback to run-scoped file-based loading with measured timing
            # CRITICAL: Set explicit fallback reason so telemetry is not empty
            if promotions_fallback_reason is None:
                promotions_fallback_reason = "missing_promotions_index"
            
            # OPTIMIZATION: Skip expensive glob when index is missing and external-analysis is large
            # If index is missing, there's no lightweight way to know which files are promotions
            # So we must either glob (slow) or return empty (fast but incorrect)
            # Prefer fast failure with explicit reason so operator can regenerate index
            external_analysis_dir = handler._health_root / "external-analysis"
            if external_analysis_dir.exists():
                # Check if directory is "large" (>100 files suggests we'd rather skip than glob)
                # Only do fast check, not full glob
                try:
                    # Bounded directory size check - stop as soon as count > 100
                    # This avoids materializing the full directory listing for large dirs
                    file_count = 0
                    if external_analysis_dir.is_dir():
                        for _ in external_analysis_dir.iterdir():
                            file_count += 1
                            if file_count > 100:
                                break
                    if file_count > 100:
                        # Skip fallback glob for large directories to avoid 1-4s penalty
                        # Return empty promotions with explicit reason
                        promotions = []
                        promotions_fallback_reason = "skipped_large_directory"
                        promotions_source = "skipped_missing_index"
                        timings["promoted_glob_ms"] = 0.0
                        timings["promotion_glob_count"] = 0
                        # NOTE: promotions_fallback_reason is emitted in structured log below
                    else:
                        # Directory is small enough to glob safely
                        fallback_glob_start = time.perf_counter()
                        promotion_files = list(external_analysis_dir.glob(f"{context.run.run_id}-next-check-promotion-*.json"))
                        timings["promoted_glob_ms"] = (time.perf_counter() - fallback_glob_start) * 1000
                        timings["promotion_glob_count"] = len(promotion_files)
                        promotions = collect_promoted_queue_entries(handler._health_root, context.run.run_id)
                        promotions_source = "file_scan"
                except OSError:
                    # Cannot check directory - skip fallback to be safe
                    promotions = []
                    promotions_fallback_reason = "directory_access_error"
                    promotions_source = "skipped_missing_index"
                    timings["promoted_glob_ms"] = 0.0
                    timings["promotion_glob_count"] = 0
            else:
                # Directory doesn't exist - no promotions possible
                promotions = []
                promotions_fallback_reason = "missing_external_analysis_dir"
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
        payload_build_start = time.perf_counter()
        run_payload = build_run_payload(context, promotions=promotions)
        timings["payload_build_ms"] = (time.perf_counter() - payload_build_start) * 1000

        # JSON serialization phase
        serialize_start = time.perf_counter()
        serialized = json.dumps(run_payload, ensure_ascii=False)
        timings["serialize_ms"] = (time.perf_counter() - serialize_start) * 1000
        timings["payload_bytes"] = len(serialized.encode("utf-8"))

        # External analysis count (fast glob only, no load)
        external_analysis_dir = handler._health_root / "external-analysis"
        external_analysis_count = 0
        if external_analysis_dir.exists():
            external_analysis_count = len(list(external_analysis_dir.glob(f"{context.run.run_id}-*.json")))
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
                "total_duration_ms": round(timings.get("total_duration_ms", 0), 2),
                "single_flight_acquire_ms": round(timings.get("single_flight_acquire_ms", 0), 2),
                "ui_index_read_ms": round(timings.get("ui_index_read_ms", 0), 2),
                "cache_lookup_ms": round(timings.get("cache_lookup_ms", 0), 2),
                "context_load_ms": round(timings.get("context_load_ms", 0), 2),
                "promotions_load_ms": round(timings.get("promotions_load_ms", 0), 2),
                "promoted_glob_ms": round(timings.get("promoted_glob_ms", 0), 2),
                "promotion_glob_count": timings.get("promotion_glob_count", 0),
                "payload_build_ms": round(timings.get("payload_build_ms", 0), 2),
                "serialize_ms": round(timings.get("serialize_ms", 0), 2),
                "payload_bytes": timings.get("payload_bytes", 0),
                "external_analysis_files_scanned": timings.get("external_analysis_files_scanned", 0),
                "notification_scan_strategy": notification_scan_strategy,
                "notification_files_scanned": timings.get("notification_files_scanned", 0),
                "notification_scan_ms": round(timings.get("notification_scan_ms", 0), 2),
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
                "route_return_ms": round(timings.get("route_return_ms", 0), 2),
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

    handler._send_text(404, "Not Found")


def build_runs_list_payload(
    handler: HealthUIRequestHandler,
    *,
    limit: int | None = 100,
    include_status: bool = False,
    include_expensive: bool = False,
) -> dict[str, object]:
    """Build the list of available runs with their triage state.

    A run is considered "triaged" if at least one next-check execution artifact
    has the usefulness_class field set.

    Performance optimization:
    - By default (limit=100), only computes batch eligibility for the returned window.
    - Set include_expensive=True to compute batch eligibility for all runs.
    - Set limit=None to return all runs without batch eligibility computation.

    Args:
        handler: The HealthUIRequestHandler instance
        limit: Maximum number of runs to return (default 100). None for all runs.
        include_status: If True, compute status/review/execution projection for returned
            window. This is a bounded, cheaper operation than include_expensive.
        include_expensive: If True, compute batch eligibility for all runs (expensive).
            Note: include_expensive=True implies include_status=True.

    Returns:
        The runs list payload dict
    """
    from ..structured_logging import emit_structured_log
    from .api import build_runs_list

    timings: dict[str, float] = {}
    total_start = time.perf_counter()

    health_root = handler.runs_dir / "health"
    cache_mtime = 0.0
    if health_root.exists():
        try:
            reviews_dir = health_root / "reviews"
            external_analysis_dir = health_root / "external-analysis"
            diagnostic_packs_dir = health_root / "diagnostic-packs"

            mtimes = []
            for d in [reviews_dir, external_analysis_dir, diagnostic_packs_dir]:
                if d.exists():
                    mtimes.append(d.stat().st_mtime)

            if mtimes:
                cache_mtime = max(mtimes)
        except OSError:
            pass
    timings["index_read_ms"] = (time.perf_counter() - total_start) * 1000

    # Include cache_mtime for filesystem freshness. Without it, a new run or execution
    # artifact would cause stale cache hits for the same parameter combination.
    cache_key = f"{handler.runs_dir}:{cache_mtime}:limit={limit}:status={include_status}:expensive={include_expensive}"

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
            "total_duration_ms": round(timings.get("total_duration_ms", 0), 2),
            "index_read_ms": round(timings.get("index_read_ms", 0), 2),
            "reviews_scan_ms": round(timings.get("reviews_scan_ms", 0), 2),
            "external_analysis_scan_ms": round(timings.get("external_analysis_scan_ms", 0), 2),
            "payload_build_ms": round(timings.get("payload_build_ms", 0), 2),
            "serialize_ms": round(timings.get("serialize_ms", 0), 2),
            "review_files_count": timings.get("review_files_count", 0),
            "execution_files_scanned": timings.get("execution_files_scanned", 0),
            "runs_count": len(cast(list, payload.get("runs", []))),
            "cache_hit": False,
            "limit": limit,
            "include_expensive": include_expensive,
            "reviews_glob_ms": round(timings.get("reviews_glob_ms", 0), 2),
            "reviews_parsed": timings.get("reviews_parsed", 0),
            "reviews_glob_only_ms": round(timings.get("reviews_glob_only_ms", 0), 2),
            "reviews_files_found": timings.get("reviews_files_found", 0),
            "reviews_parse_ms": round(timings.get("reviews_parse_ms", 0), 2),
            "execution_artifacts_glob_ms": round(timings.get("execution_artifacts_glob_ms", 0), 2),
            "execution_glob_only_ms": round(timings.get("execution_glob_only_ms", 0), 2),
            "execution_parse_ms": round(timings.get("execution_parse_ms", 0), 2),
            "execution_artifacts_scanned": timings.get("execution_artifacts_scanned", 0),
            "execution_count_derivation_ms": round(timings.get("execution_count_derivation_ms", 0), 2),
            "execution_count_derivation_matches": timings.get("execution_count_derivation_matches", 0),
            "execution_lookup_strategy": timings.get("execution_lookup_strategy", "unknown"),
            "execution_run_prefixes_queried": timings.get("execution_run_prefixes_queried", 0),
            "execution_files_found_total": timings.get("execution_files_found_total", 0),
            "execution_files_considered": timings.get("execution_files_considered", 0),
            "execution_files_parsed": timings.get("execution_files_parsed", 0),
            "execution_files_skipped_outside_window": timings.get("execution_files_skipped_outside_window", 0),
            "execution_lookup_ms": round(timings.get("execution_lookup_ms", 0), 2),
            "row_assembly_ms": round(timings.get("row_assembly_ms", 0), 2),
            "sort_ms": round(timings.get("sort_ms", 0), 2),
            "batch_eligible_runs": timings.get("batch_eligible_runs", 0),
            "review_artifact_prescan_ms": round(timings.get("review_artifact_prescan_ms", 0), 2),
            "batch_eligibility_prescan_ms": round(timings.get("batch_eligibility_prescan_ms", 0), 2),
            "batch_plan_glob_ms": round(timings.get("batch_plan_glob_ms", 0), 2),
            "batch_plan_files_found": timings.get("batch_plan_files_found", 0),
            "batch_plan_parse_ms": round(timings.get("batch_plan_parse_ms", 0), 2),
            "batch_exec_glob_ms": round(timings.get("batch_exec_glob_ms", 0), 2),
            "batch_exec_files_found": timings.get("batch_exec_files_found", 0),
            "batch_exec_parse_ms": round(timings.get("batch_exec_parse_ms", 0), 2),
            "batch_run_id_matching_ms": round(timings.get("batch_run_id_matching_ms", 0), 2),
            "batch_cache_construction_ms": round(timings.get("batch_cache_construction_ms", 0), 2),
            "review_status_row_ms": round(timings.get("review_status_row_ms", 0), 2),
            "review_download_path_row_ms": round(timings.get("review_download_path_row_ms", 0), 2),
            "batch_eligibility_row_ms": round(timings.get("batch_eligibility_row_ms", 0), 2),
            "artifact_lookup_row_ms": round(timings.get("artifact_lookup_row_ms", 0), 2),
            "timestamp_normalization_row_ms": round(timings.get("timestamp_normalization_row_ms", 0), 2),
            "label_normalization_row_ms": round(timings.get("label_normalization_row_ms", 0), 2),
            "per_row_fs_checks_ms": round(timings.get("per_row_fs_checks_ms", 0), 2),
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


def load_context_for_run(
    handler: HealthUIRequestHandler, run_id: str
) -> Any:
    """Load UI context for a specific run from its durable artifacts.

    This allows browsing non-latest runs by reading their artifacts
    and building the context from that specific run's data.

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID to load

    Returns:
        UIIndexContext for the requested run, or None if not found.
    """
    from datetime import UTC, datetime

    from .model import build_ui_context
    from .server_read_support import (
        _build_clusters_from_review,
        _build_drilldown_availability_from_review,
        _build_execution_history,
        _build_llm_stats_for_run,
        _build_proposal_status_summary,
        _build_queue_from_plan,
        _build_review_enrichment_status_for_past_run,
        _count_run_artifacts,
        _find_next_check_plan,
        _find_review_enrichment,
        _load_notifications_for_run,
        _load_proposals_for_run,
        _scan_external_analysis,
    )

    reviews_dir = handler.runs_dir / "health" / "reviews"
    review_artifact_path = reviews_dir / f"{run_id}-review.json"

    if not review_artifact_path.exists():
        logger.debug(
            "Run review artifact not found",
            extra={"run_id": run_id, "path": str(review_artifact_path)},
        )
        return None

    try:
        review_data = json.loads(review_artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Failed to read run review artifact",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None

    run_label = review_data.get("run_label", run_id)
    timestamp = review_data.get("timestamp", datetime.now(UTC).isoformat())

    selected_drilldowns = review_data.get("selected_drilldowns", [])
    cluster_count = len(selected_drilldowns) if isinstance(selected_drilldowns, list) else 0

    clusters = _build_clusters_from_review(run_id, review_data, handler.runs_dir)

    drilldown_count = _count_run_artifacts(handler.runs_dir / "health" / "drilldowns", run_id)

    proposals_data, proposal_count = _load_proposals_for_run(handler.runs_dir / "health" / "proposals", run_id)

    external_analysis_dir = handler._health_root / "external-analysis"
    external_analysis_data = _scan_external_analysis(external_analysis_dir, run_id)
    external_analysis_count = external_analysis_data.get("count", 0)

    notification_history, notification_count = _load_notifications_for_run(
        handler.runs_dir / "health" / "notifications", run_id
    )

    drilldown_availability = _build_drilldown_availability_from_review(
        review_data, handler.runs_dir / "health" / "drilldowns", run_id
    )

    review_enrichment = _find_review_enrichment(external_analysis_dir, run_id)

    has_enrichment_artifact = review_enrichment is not None
    review_enrichment_status: dict[str, object] | None = None

    if not has_enrichment_artifact:
        external_analysis_config = review_data.get("external_analysis_settings")
        run_config: dict[str, object] | None = None
        if isinstance(external_analysis_config, dict):
            candidate = external_analysis_config.get("review_enrichment")
            if isinstance(candidate, dict):
                run_config = candidate

        review_enrichment_status = _build_review_enrichment_status_for_past_run(run_config)

    next_check_plan = _find_next_check_plan(external_analysis_dir, run_id)

    next_check_queue = _build_queue_from_plan(next_check_plan)

    execution_history = _build_execution_history(external_analysis_dir, run_id)

    llm_stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

    alertmanager_compact_entry = None
    compact_path = handler._health_root / f"{run_id}-alertmanager-compact.json"
    if compact_path.exists():
        try:
            compact_raw = json.loads(compact_path.read_text(encoding="utf-8"))
            alertmanager_compact_entry = {
                "status": compact_raw.get("status"),
                "alert_count": compact_raw.get("alert_count", 0),
                "severity_counts": compact_raw.get("severity_counts", {}),
                "state_counts": compact_raw.get("state_counts", {}),
                "top_alert_names": compact_raw.get("top_alert_names", []),
                "affected_namespaces": compact_raw.get("affected_namespaces", []),
                "affected_clusters": compact_raw.get("affected_clusters", []),
                "affected_services": compact_raw.get("affected_services", []),
                "truncated": compact_raw.get("truncated", False),
                "captured_at": compact_raw.get("captured_at"),
                "by_cluster": compact_raw.get("by_cluster", []),
            }
        except Exception:
            pass

    alertmanager_sources_entry = None
    sources_path = handler._health_root / f"{run_id}-alertmanager-sources.json"
    if sources_path.exists():
        from ..health.ui import _serialize_alertmanager_sources as _serialize_am_sources
        try:
            alertmanager_sources_entry = _serialize_am_sources(handler._health_root, run_id)
        except Exception:
            pass

    run_entry = {
        "run_id": run_id,
        "run_label": run_label,
        "timestamp": timestamp,
        "collector_version": review_data.get("collector_version", "0.0.0"),
        "cluster_count": cluster_count,
        "drilldown_count": drilldown_count,
        "proposal_count": proposal_count,
        "external_analysis_count": external_analysis_count,
        "notification_count": notification_count,
        "llm_stats": llm_stats,
        "historical_llm_stats": None,
        "llm_activity": {"entries": [], "summary": {"retainedEntries": 0}},
        "llm_policy": None,
        "review_enrichment": review_enrichment,
        "review_enrichment_status": review_enrichment_status,
        "provider_execution": None,
        "next_check_plan": next_check_plan,
        "next_check_queue": next_check_queue,
        "next_check_queue_explanation": None,
        "next_check_execution_history": execution_history,
        "deterministic_next_checks": None,
        "planner_availability": None,
        "diagnostic_pack_review": None,
        "diagnostic_pack": None,
        "alertmanager_compact": alertmanager_compact_entry,
        "alertmanager_sources": alertmanager_sources_entry,
    }

    proposal_status_summary = _build_proposal_status_summary(proposals_data)

    index: dict[str, object] = {
        "run": run_entry,
        "clusters": clusters,
        "latest_assessment": None,
        "latest_findings": None,
        "proposals": proposals_data,
        "proposal_status_summary": proposal_status_summary,
        "notification_history": notification_history,
        "drilldown_availability": drilldown_availability,
        "run_stats": {"total_runs": 0},
        "auto_drilldown_interpretations": {},
        "external_analysis": external_analysis_data,
    }

    try:
        return build_ui_context(index)
    except Exception as exc:
        logger.warning(
            "Failed to build context for run",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None
