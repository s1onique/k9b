"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, cast

from ..external_analysis.artifact import ExternalAnalysisArtifact
from ..structured_logging import emit_structured_log
from .model import UIIndexContext, build_ui_context, load_ui_index

# Re-export handlers and helpers from extracted modules for backward compatibility
from .server_alertmanager import (  # noqa: E402, F401
    handle_alertmanager_source_action,
)
from .server_batch_execution import (  # noqa: E402, F401
    handle_run_batch_next_check_execution,
)
from .server_context import (  # noqa: E402, F401
    load_context_for_run,
    load_request_context,
)
from .server_execution_side_effects import (  # noqa: E402, F401
    _export_usefulness_review_for_run,
    _invalidate_runs_list_cache,
    _persist_batch_execution_history_to_ui_index,
    _refresh_diagnostic_pack_latest,
    _runs_list_cache,
    _runs_list_cache_lock,
)
from .server_feedback import (  # noqa: E402, F401
    handle_alertmanager_relevance_feedback,
    handle_usefulness_feedback,
)
from .server_handler_state import (  # noqa: E402, F401
    get_client_ip,
    get_run_label,
    log_access_completion,
    reset_request_state,
    set_request_timing_state,
)
from .server_next_checks import (  # noqa: E402, F401
    handle_deterministic_promotion,
    handle_next_check_approval,
    handle_next_check_execution,
)
from .server_read_support import (  # noqa: E402, F401
    RunArtifactIndex,  # noqa: E402
    _build_clusters_and_drilldown_availability,
    _build_clusters_from_review,
    _build_execution_history,
    _build_llm_stats_for_run,
    _build_proposal_status_summary,
    _build_queue_from_plan,
    _build_review_enrichment_status_for_past_run,
    _build_run_artifact_index,
    _count_run_artifacts,
    _find_next_check_plan,
    _find_review_enrichment,
    _get_field_with_default,
    _get_field_with_fallback,
    _load_alertmanager_review_artifacts,
    _load_notifications_for_run,
    _load_proposals_for_run,
    _merge_alertmanager_review_into_history_entry,
    _scan_external_analysis,
)
from .server_response import (  # noqa: E402, F401
    send_bytes_response,
    send_file_response,
    send_json_response,
    send_text_response,
    set_response_status,
)
from .server_routes import (  # noqa: E402, F401
    handle_get_request,
    handle_post_request,
)
from .server_runtime import (  # noqa: E402, F401
    _SAFE_LOOPBACK_HOSTS,
    _SLOW_REQUEST_THRESHOLD_MS,
    DEFAULT_STATIC_DIR,
    PROJECT_ROOT,
    _is_exposed_host,
    start_ui_server,
)
from .server_shared import _compute_health_root
from .server_singleflight import (  # noqa: E402, F401
    _notifications_cache,
    _notifications_cache_lock,
    _run_payload_cache,
    _run_payload_cache_lock,
    _single_flight_acquire_impl,
    _single_flight_events,
    _single_flight_lock,
    _single_flight_release_impl,
    _single_flight_wait,
)

logger = logging.getLogger(__name__)

# Maximum cache entries to prevent unbounded memory growth
_MAX_CACHE_ENTRIES = 10


# --------------------------------------------------------------------
# Access-log compatibility wrapper (preserves server.emit_structured_log patch point)
# --------------------------------------------------------------------


def _log_request_access(
    method: str,
    path: str,
    query: str,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
    client_ip: str,
    run_label: str = "",
    is_static_asset: bool = False,
    request_id: str = "",
    route_return_ms: float = 0.0,
    client_request_id: str = "",
) -> None:
    """Compatibility wrapper for access-log emission.

    Preserves the old patch point k8s_diag_agent.ui.server.emit_structured_log
    for backward compatibility with tests. We access emit_structured_log from the
    module's global namespace at call time, not import time, to allow test mocks to work.

    Similarly, _SLOW_REQUEST_THRESHOLD_MS is passed as a parameter so tests can
    patch k8s_diag_agent.ui.server._SLOW_REQUEST_THRESHOLD_MS directly.
    """
    from .server_runtime import _log_request_access_with_emit

    _log_request_access_with_emit(
        emit_fn=emit_structured_log,
        slow_request_threshold_ms=_SLOW_REQUEST_THRESHOLD_MS,
        method=method,
        path=path,
        query=query,
        status_code=status_code,
        duration_ms=duration_ms,
        response_bytes=response_bytes,
        client_ip=client_ip,
        run_label=run_label,
        is_static_asset=is_static_asset,
        request_id=request_id,
        route_return_ms=route_return_ms,
        client_request_id=client_request_id,
    )


# --------------------------------------------------------------------
# Single-flight compatibility wrappers (inject server.emit_structured_log patch point)
# --------------------------------------------------------------------


def _single_flight_acquire(
    key: str,
    request_path: str = "",
    cache_key: str = "",
) -> tuple[bool, tuple[object, list] | None, float]:
    """Compatibility wrapper that injects emit_structured_log for test mock compatibility.

    This preserves the old patch point k8s_diag_agent.ui.server.emit_structured_log
    for backward compatibility with tests.
    """
    return _single_flight_acquire_impl(
        emit_fn=emit_structured_log,
        key=key,
        request_path=request_path,
        cache_key=cache_key,
    )


def _single_flight_release(
    key: str,
    result: object,
    success: bool = True,
    result_type: str = "built",
) -> None:
    """Compatibility wrapper that injects emit_structured_log for test mock compatibility.

    This preserves the old patch point k8s_diag_agent.ui.server.emit_structured_log
    for backward compatibility with tests.
    """
    return _single_flight_release_impl(
        emit_fn=emit_structured_log,
        key=key,
        result=result,
        success=success,
        result_type=result_type,
    )


# NOTE: Single-flight helpers (_single_flight_acquire, _single_flight_release,
# _single_flight_wait, _single_flight_events, _single_flight_lock) are imported from
# server_singleflight for backward compatibility. See import section above.
#
# NOTE: Run-payload cache (_run_payload_cache, _run_payload_cache_lock) is imported from
# server_singleflight for backward compatibility. See import section above.
#
# NOTE: Notifications cache (_notifications_cache, _notifications_cache_lock) is imported
# from server_singleflight for backward compatibility. See import section above.
#
# NOTE: PROJECT_ROOT, DEFAULT_STATIC_DIR, _is_exposed_host,
# _SAFE_LOOPBACK_HOSTS, _SLOW_REQUEST_THRESHOLD_MS, start_ui_server are imported from
# server_runtime for backward compatibility. See import section above.
#
# NOTE: _refresh_diagnostic_pack_latest and _export_usefulness_review_for_run
# are imported from server_execution_side_effects for backward compatibility.
# See import section above.
#
# NOTE: reset_request_state, get_client_ip, get_run_label, set_request_timing_state,
# log_access_completion are imported from server_handler_state for backward compatibility.
# See import section above.


class HealthUIRequestHandler(BaseHTTPRequestHandler):
    server_version = "HealthUI/2.0"

    def __init__(self, *args: object, runs_dir: Path, static_dir: Path, auth_token: str | None = None, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        self.static_dir = static_dir
        self._auth_token = auth_token
        self._health_root = _compute_health_root(runs_dir)
        # Access logging state - initialized in __init__ for safety,
        # but RESET per-request in do_GET/do_POST to measure actual request time
        # (not connection/handler lifetime which includes keep-alive idle time)
        self._start_time: float = 0.0
        self._request_method: str = ""
        self._request_path: str = ""
        self._request_query: str = ""
        self._is_static: bool = False
        self._response_bytes: int = 0
        self._status_code: int = 200
        # Correlation ID for linking access log to route timing logs
        self._request_id: str = ""
        # Time when route handler returned (before send)
        self._route_return_ms: float = 0.0
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # CRITICAL: Reset timing state here to ensure fresh state per connection
        # This handles the case where the same handler instance processes multiple
        # requests on a keep-alive connection
        self._reset_request_state()

    def _reset_request_state(self) -> None:
        """Reset all per-request state to measure actual request processing time."""
        reset_request_state(self)

    def _get_client_ip(self) -> str:
        """Extract client IP from request."""
        return get_client_ip(self)

    def _get_run_label(self) -> str:
        """Extract run_label from the current context if available."""
        return get_run_label(self)

    def do_GET(self) -> None:
        # CRITICAL: Reset timing state FIRST to measure actual request processing time
        self._reset_request_state()

        # Delegate to extracted route handler (re-exported at module level)
        handle_get_request(self)

    def do_POST(self) -> None:
        # CRITICAL: Reset timing state FIRST to measure actual request processing time
        self._reset_request_state()

        # Delegate to extracted route handler (re-exported at module level)
        handle_post_request(self)

    def set_request_timing(self, request_id: str, route_return_ms: float) -> None:
        """Set correlation and timing info for access log from server_reads."""
        set_request_timing_state(self, request_id, route_return_ms)

    def _log_access_completion(self) -> None:
        """Log access completion with latency and status."""
        # Inject emit_structured_log at call time to preserve test mock compatibility
        # via server.emit_structured_log patch point
        log_access_completion(self, emit_fn=emit_structured_log, slow_request_threshold_ms=_SLOW_REQUEST_THRESHOLD_MS)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_api(self, route: str, query: str) -> None:
        """Handle API GET requests by delegating to server_reads module."""
        from .server_reads import handle_api as _handle_api_reads

        _handle_api_reads(self, route, query)

    def _resolve_plan_candidate(
        self,
        candidates: Sequence[object],
        requested_candidate_id: str | None,
        requested_candidate_index: int | None,
    ) -> tuple[Mapping[str, object] | None, int | None]:
        """Resolve a plan candidate by ID or index (delegates to server_next_check_utils)."""
        from .server_next_check_utils import resolve_plan_candidate as _resolve

        entry, idx = _resolve(candidates, requested_candidate_id, requested_candidate_index)
        return (entry, idx) if entry is not None else (None, None)

    def _find_candidate_in_all_plan_artifacts(
        self,
        run_id: str,
        candidate_id: str | None,
        candidate_index: int | None,
    ) -> tuple[dict[str, object] | None, int | None, Path | None]:
        """Search for a candidate across all planner artifacts (delegates to server_next_check_utils)."""
        from .server_next_check_utils import find_candidate_in_all_plan_artifacts as _find

        return _find(self._health_root, run_id, candidate_id, candidate_index)

    def _find_candidate_in_all_plan_artifacts_from_health_root(
        self,
        health_root: Path,
        run_id: str,
        candidate_id: str | None,
        candidate_index: int | None,
    ) -> tuple[dict[str, object] | None, int | None, Path | None]:
        """Search for a candidate in health_root (delegates to server_next_check_utils)."""
        from .server_next_check_utils import find_candidate_in_all_plan_artifacts as _find

        return _find(health_root, run_id, candidate_id, candidate_index)

    def _load_context(self, requested_run_id: str | None = None) -> UIIndexContext | None:
        """Load the UI context, optionally for a specific run.

        If requested_run_id is provided, try to load context from that run's review
        artifact. Otherwise, load from the ui-index.json (latest run).

        Args:
            requested_run_id: Optional run ID to load. If None, loads latest run.

        Returns:
            UIIndexContext or None if loading fails.
        """
        # If a specific run is requested, try to build context from its review artifact
        if requested_run_id:
            context = self._load_context_for_run(requested_run_id)
            if context is not None:
                return context
            # If the requested run doesn't exist, fall back to latest
            # Log a warning but don't fail - this provides explicit behavior
            logger.warning(
                "Requested run not found, falling back to latest",
                extra={"requested_run_id": requested_run_id},
            )

        # Default: load from ui-index.json (latest run)
        try:
            # ui-index.json is written to runs/health/ by write_health_ui_index
            index = load_ui_index(self.runs_dir / "health")
            return build_ui_context(index)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
            self._send_text(500, f"Unable to read ui-index.json: {exc}")
            return None

    def _load_context_for_run(self, run_id: str) -> UIIndexContext | None:
        """Load UI context for a specific run from its durable artifacts.

        This allows browsing non-latest runs by reading their artifacts
        and building the context from that specific run's data.

        Args:
            run_id: The run ID to load.

        Returns:
            UIIndexContext for the requested run, or None if not found.
        """
        # Thin compatibility wrapper - delegates to extracted module
        return load_context_for_run(self, run_id)

    def _build_runs_list_payload(self) -> dict[str, object]:
        """Build the list of available runs with their triage state.

        A run is considered "triaged" if at least one next-check execution artifact
        has the usefulness_class field set (operator has reviewed it).

        Uses caching keyed by the health directory mtime to avoid rescanning
        the reviews/ and external-analysis/ directories on every request.
        """
        from .api import build_runs_list

        timings: dict[str, float] = {}
        total_start = time.perf_counter()

        # Get the mtime of the health root to use as cache key
        health_root = self.runs_dir / "health"
        cache_mtime = 0.0
        if health_root.exists():
            try:
                # Use the latest mtime from relevant subdirectories
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

        # Check cache
        cache_key = str(self.runs_dir)
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
                        },
                    )
                    return cached_payload

        # Build the runs list payload with inner timings
        # build_runs_list() now handles all scanning including index-backed path
        payload_build_start = time.perf_counter()
        payload: dict[str, object]
        try:
            result = build_runs_list(self.runs_dir, include_status=True, _timings=True)
            if isinstance(result, tuple):
                raw_payload, inner_timings = result
                payload = cast(dict[str, object], raw_payload)
                # Merge inner timings into outer timings (cast values to float)
                for key, value in inner_timings.items():
                    timings[key] = cast(float, value)
            else:
                payload = cast(dict[str, object], result)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
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
                },
            )
            payload = {"runs": [], "error": str(exc)}
        timings["payload_build_ms"] = (time.perf_counter() - payload_build_start) * 1000

        # Stage 4: Serialize to JSON (for timing measurement)
        serialize_start = time.perf_counter()
        _ = json.dumps(payload, ensure_ascii=False)  # Measure only, result not used
        timings["serialize_ms"] = (time.perf_counter() - serialize_start) * 1000

        # Cache the built payload
        with _runs_list_cache_lock:
            # Evict old entries if cache is full
            if len(_runs_list_cache) >= _MAX_CACHE_ENTRIES:
                oldest_key = next(iter(_runs_list_cache))
                del _runs_list_cache[oldest_key]
            _runs_list_cache[cache_key] = (cast(dict[str, Any], payload), cache_mtime)

        total_duration = (time.perf_counter() - total_start) * 1000
        timings["total_duration_ms"] = total_duration

        # Emit structured timing log with all inner timings from build_runs_list()
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
                # Inner timings from build_runs_list()
                "reviews_glob_ms": round(timings.get("reviews_glob_ms", 0), 2),
                "reviews_parsed": timings.get("reviews_parsed", 0),
                # Stage 1 sub-stages (breakdown of reviews_glob_ms)
                "reviews_glob_only_ms": round(timings.get("reviews_glob_only_ms", 0), 2),
                "reviews_files_found": timings.get("reviews_files_found", 0),
                "reviews_parse_ms": round(timings.get("reviews_parse_ms", 0), 2),
                "execution_artifacts_glob_ms": round(timings.get("execution_artifacts_glob_ms", 0), 2),
                # Stage 2 sub-stages (breakdown of execution_artifacts_glob_ms)
                "execution_glob_only_ms": round(timings.get("execution_glob_only_ms", 0), 2),
                "execution_parse_ms": round(timings.get("execution_parse_ms", 0), 2),
                "execution_artifacts_scanned": timings.get("execution_artifacts_scanned", 0),
                "execution_count_derivation_ms": round(timings.get("execution_count_derivation_ms", 0), 2),
                "execution_count_derivation_matches": timings.get("execution_count_derivation_matches", 0),
                "row_assembly_ms": round(timings.get("row_assembly_ms", 0), 2),
                "sort_ms": round(timings.get("sort_ms", 0), 2),
                "batch_eligible_runs": timings.get("batch_eligible_runs", 0),
                # Pre-scan timings (Stage 3a/3b)
                "review_artifact_prescan_ms": round(timings.get("review_artifact_prescan_ms", 0), 2),
                "batch_eligibility_prescan_ms": round(timings.get("batch_eligibility_prescan_ms", 0), 2),
                # Stage 3b sub-stages (breakdown of batch_eligibility_prescan_ms)
                "batch_plan_glob_ms": round(timings.get("batch_plan_glob_ms", 0), 2),
                "batch_plan_files_found": timings.get("batch_plan_files_found", 0),
                "batch_plan_parse_ms": round(timings.get("batch_plan_parse_ms", 0), 2),
                "batch_exec_glob_ms": round(timings.get("batch_exec_glob_ms", 0), 2),
                "batch_exec_files_found": timings.get("batch_exec_files_found", 0),
                "batch_exec_parse_ms": round(timings.get("batch_exec_parse_ms", 0), 2),
                "batch_run_id_matching_ms": round(timings.get("batch_run_id_matching_ms", 0), 2),
                "batch_cache_construction_ms": round(timings.get("batch_cache_construction_ms", 0), 2),
                # Row assembly sub-stages (detailed breakdown of row_assembly_ms)
                "review_status_row_ms": round(timings.get("review_status_row_ms", 0), 2),
                "review_download_path_row_ms": round(timings.get("review_download_path_row_ms", 0), 2),
                "batch_eligibility_row_ms": round(timings.get("batch_eligibility_row_ms", 0), 2),
                "artifact_lookup_row_ms": round(timings.get("artifact_lookup_row_ms", 0), 2),
                "timestamp_normalization_row_ms": round(timings.get("timestamp_normalization_row_ms", 0), 2),
                "label_normalization_row_ms": round(timings.get("label_normalization_row_ms", 0), 2),
                "per_row_fs_checks_ms": round(timings.get("per_row_fs_checks_ms", 0), 2),
                "rows_built": timings.get("rows_built", 0),
                # Per-row filesystem call counters (prove no per-row FS work)
                "path_exists_calls": timings.get("path_exists_calls", 0),
                "stat_calls": timings.get("stat_calls", 0),
                "diagnostic_pack_path_checks": timings.get("diagnostic_pack_path_checks", 0),
                "run_scoped_review_path_checks": timings.get("run_scoped_review_path_checks", 0),
                "per_run_glob_calls": timings.get("per_run_glob_calls", 0),
                "per_run_directory_list_calls": timings.get("per_run_directory_list_calls", 0),
            },
        )

        return payload

    def _parse_limit(self, value: str | None) -> int | None:
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def _parse_page(self, value: str | None) -> int:
        parsed = self._parse_limit(value)
        return parsed if parsed else 1

    def _send_json(self, body: object, code: int = 200) -> None:
        """Send a JSON response with structured timing instrumentation."""
        send_json_response(self, body, code, request_path=self._request_path)

    def _send_file(self, path: Path) -> None:
        """Send a file response with appropriate content type."""
        send_file_response(self, path)

    def _set_status(self, code: int) -> None:
        """Set the response status code."""
        set_response_status(self, code)

    def _send_bytes(self, data: bytes, *, content_type: str = "application/octet-stream", filename: str | None = None) -> None:
        """Send raw bytes response with optional Content-Disposition header."""
        send_bytes_response(self, data, content_type=content_type, filename=filename)

    def _send_text(self, code: int, message: str) -> None:
        """Send a plain text response."""
        send_text_response(self, code, message)


def _relative_path(base: Path, target: object | None) -> str | None:
    """Compatibility wrapper for relative path helper.

    Delegates to server_next_check_utils.relative_path while preserving
    the old symbol name for callers that import from k8s_diag_agent.ui.server.
    """
    from .server_next_check_utils import relative_path

    return relative_path(base, target)


def _determine_execution_state_from_artifact(artifact: ExternalAnalysisArtifact) -> str:
    """Compatibility wrapper for execution state from artifact.

    Delegates to server_next_check_utils.determine_execution_state_from_artifact
    while preserving the old symbol name for callers that import from
    k8s_diag_agent.ui.server.
    """
    from .server_next_check_utils import determine_execution_state_from_artifact as _impl

    return _impl(artifact)
