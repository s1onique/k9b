"""Selected-run detail read handlers for the UI server.

This module contains the /api/run detail route handler extracted from server_reads.py.
Functions here handle loading and building the payload for a specific selected run.

Extraction rational: /api/run is a distinct route with complex instrumentation, caching,
and single-flight logic. This is a separate concern from the main dispatcher in
server_reads.py.

Keep behavior exact: response shapes, error codes, cache behavior, and timing
instrumentation are preserved from the original implementation.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_run_detail_route(handler: HealthUIRequestHandler, query: str) -> None:
    """Handle GET /api/run for the selected run.

    This is the selected-run detail endpoint extracted from server_reads.py.
    All cache/single-flight logic is preserved inline here since it needs access
    to handler state.

    Args:
        handler: The HealthUIRequestHandler instance
        query: The query string
    """
    # Import here to avoid circular import at module level
    from urllib.parse import parse_qs

    from ..structured_logging import emit_structured_log
    from .api import build_run_payload
    from .server import (
        _single_flight_acquire,
        _single_flight_release,
        _single_flight_wait,
    )
    from .server_singleflight import (
        _run_payload_cache,
        _run_payload_cache_lock,
    )

    params = parse_qs(query)
    selected_run_id = params.get("run_id", [None])[0]

    context = handler._load_context(requested_run_id=selected_run_id)
    if context is None:
        return

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

    # Promotions load phase - delegate to extraction module
    from .server_artifact_reads import _count_external_analysis_files, _load_promotions_for_run

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
