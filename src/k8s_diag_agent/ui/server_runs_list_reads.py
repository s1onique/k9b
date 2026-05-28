"""Runs-list read handler for the UI server.

This module contains the /api/runs route handler extracted from server_reads.py.
It handles runs-list artifact reads including batch eligibility fast-path caching.

Keep behavior exact: HTTP status codes, error messages, and security checks are
preserved from the original implementation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

from ..structured_logging import emit_structured_log
from .server_artifact_reads import _has_batch_eligibility_index

logger = __name__


__all__ = [
    "handle_runs_list_route",
]


def handle_runs_list_route(handler: HealthUIRequestHandler, query: str) -> None:
    """Handle GET /api/runs route.

    Extracts the /api/runs route from handle_api() for artifact-read isolation.
    This handler reads runs-list artifacts and uses batch eligibility fast-path
    caching based on ui-index.json mtime.

    Args:
        handler: The HealthUIRequestHandler instance
        query: The query string
    """
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

    # Import cache/state from server module
    from .server import (
        _runs_list_cache,
        _runs_list_cache_lock,
        _single_flight_acquire,
        _single_flight_release,
        _single_flight_wait,
    )

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

    # Import here to avoid circular import
    from .server_runs_list_payload import build_runs_list_payload

    runs_payload = build_runs_list_payload(handler, limit=limit_value, include_status=include_status, include_expensive=include_expensive, include_batch_eligibility=include_batch_eligibility)

    # Add debug diagnostics if requested (not cached - always fresh)
    # Debug is gated by environment variable K9B_ENABLE_DEBUG_ENDPOINTS=true
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
