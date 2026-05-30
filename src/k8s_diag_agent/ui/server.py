"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import functools
import json
import logging
import sys
import time
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, cast

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from ..external_analysis.deterministic_next_check_promotion import (
    collect_promoted_queue_entries,
)
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
from .server_shared import _compute_health_root, _normalize_runs_dir, _validate_runs_dir

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"

# In-memory cache for run payloads to avoid repeated expensive computation
# Key: (run_id, ui_index_mtime), Value: (cached_payload, cached_promotions)
_run_payload_cache: dict[tuple[str, float], tuple[dict[str, Any], list[dict[str, object]]]] = {}
_run_payload_cache_lock = Lock()
# Maximum cache entries to prevent unbounded memory growth
_MAX_CACHE_ENTRIES = 10

# In-memory cache for notifications - keyed by (notifications_dir_mtime, query_params)
# This avoids scanning all notification files on every request
_notifications_cache: dict[str, tuple[dict[str, Any], float]] = {}  # key -> (payload, mtime)
_notifications_cache_lock = Lock()

# Single-flight locks to prevent duplicate concurrent builds for the same cache key
# Key: cache key, Value: tuple of (threading.Event, result_holder list)
# result_holder: list with one element to hold the result when ready
_single_flight_events: dict[str, tuple[object, list]] = {}
_single_flight_lock = Lock()

# Directory name for stable "latest" diagnostic pack mirror files
_LATEST_PACK_DIR_NAME = "latest"

# Scripts directory
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Slow request threshold in milliseconds
_SLOW_REQUEST_THRESHOLD_MS = 1000


def _single_flight_acquire(key: str, request_path: str = "", cache_key: str = "") -> tuple[bool, tuple[object, list] | None, float]:
    """Acquire single-flight lock for the given key.

    Returns:
        Tuple of (should_build, result_holder_or_event, wait_start_time).
        - should_build=True means this caller should build the result
        - should_build=False means wait for the in-flight build and use its result
        - wait_start_time is the timestamp when waiting started (for measuring wait duration)
    """
    import time as time_module

    wait_start = time_module.perf_counter()
    with _single_flight_lock:
        if key in _single_flight_events:
            # There's already an in-flight request - return event to wait on
            # Emit structured log for waiter acquire
            emit_structured_log(
                component="single-flight",
                message="Single-flight waiter acquiring",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "acquire_result": "waiter",
                    "cache_key": cache_key[:100] if cache_key else "",
                    "request_path": request_path,
                },
            )
            return False, _single_flight_events[key], wait_start
        else:
            # Create new in-flight state
            # result_holder: list with one element to hold result when ready
            result_holder: list = [None]
            event = result_holder  # Use list as mutable container for result
            _single_flight_events[key] = (event, result_holder)
            # Emit structured log for builder acquire
            emit_structured_log(
                component="single-flight",
                message="Single-flight builder acquiring",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "acquire_result": "builder",
                    "cache_key": cache_key[:100] if cache_key else "",
                    "request_path": request_path,
                },
            )
            return True, (event, result_holder), wait_start


def _single_flight_release(key: str, result: object, success: bool = True, result_type: str = "built") -> None:
    """Release single-flight lock and set result.

    Args:
        key: The single-flight key
        result: The result to store (can be None on failure)
        success: Whether the build succeeded - if False, also clean up the entry
        result_type: Type of result - "built" (freshly built), "cached" (served from cache), "error" (build failed)
    """
    import time as time_module

    with _single_flight_lock:
        if key in _single_flight_events:
            event, result_holder = _single_flight_events[key]
            result_holder[0] = result  # Store result in the holder

            # Give waiters a moment to read the result before cleaning up
            # This prevents the race where a waiter checks right after we set result but before it reads
            # We keep the entry in the dict with a sentinel marker to indicate "ready"
            result_holder.append("_READY_")  # Marker to indicate result is ready

            # Brief delay to allow waiters to pick up the result (max 50ms)
            # This is a tradeoff - we trade a small delay for correctness
            time_module.sleep(0.005)  # 5ms to let waiters wake up and read

            # Now delete to allow retries after waiters have had a chance
            del _single_flight_events[key]

            # Emit structured log for release
            emit_structured_log(
                component="single-flight",
                message="Single-flight released",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "release_success": success,
                    "result_type": result_type,
                },
            )

            # Log release for debugging
            logger.debug(
                f"Single-flight released for key: {key[:50]}...",
                extra={"key": key[:100], "action": "release", "success": success},
            )


def _single_flight_wait(event_holder: tuple[object, list], wait_start: float) -> tuple[object | None, float]:
    """Wait for single-flight result to be ready.

    Args:
        event_holder: Tuple of (event, result_holder) from _single_flight_acquire
        wait_start: Timestamp when waiting started (from _single_flight_acquire)

    Returns:
        Tuple of (result, wait_duration_ms)
    """
    import time as time_module

    # Brief spin-wait for result (max ~100ms)
    # Check for both result[0] being non-None AND the _READY_ marker
    for i in range(10):
        time_module.sleep(0.01)
        result_holder = event_holder[1]
        # Check if result is ready: either marker present or result is not None
        if len(result_holder) >= 2 and result_holder[-1] == "_READY_":
            # Result is ready, return it
            wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
            # Return the actual result (first element)
            return result_holder[0], wait_duration_ms
        if result_holder[0] is not None:
            # Fallback: result was set but marker not yet added (race condition)
            wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
            return result_holder[0], wait_duration_ms

    # If still not ready, return None (caller will handle)
    wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
    return None, wait_duration_ms


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
    """Log structured HTTP access event with latency telemetry.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g., /api/run)
        query: Query string (e.g., run_id=abc)
        status_code: HTTP response status code
        duration_ms: Request handling duration in milliseconds
        response_bytes: Response body size in bytes
        client_ip: Client IP address
        run_label: Run label when known, else empty string
        is_static_asset: Whether this is a static asset request
        request_id: Correlation ID for linking access log to route timing logs
        route_return_ms: Time from request start to route handler returning (before send)
        client_request_id: Client-generated request ID from X-K9B-Client-Request-Id header
    """
    # Determine severity based on status code and latency
    if status_code >= 500:
        severity = "ERROR"
    elif status_code >= 400:
        severity = "WARNING"
    elif duration_ms >= _SLOW_REQUEST_THRESHOLD_MS:
        severity = "WARNING"
    elif is_static_asset:
        # Use DEBUG for static assets to reduce noise
        severity = "DEBUG"
    else:
        severity = "INFO"

    # Build message
    message = f"{method} {path}"
    if query:
        message += f"?{query}"

    metadata = {
        "method": method,
        "path": path,
        "query": query,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "response_bytes": response_bytes,
        "client_ip": client_ip,
        "run_label": run_label,
    }

    # Add correlation fields if available
    if request_id:
        metadata["request_id"] = request_id
    if client_request_id:
        metadata["client_request_id"] = client_request_id
    if route_return_ms > 0:
        metadata["route_return_ms"] = round(route_return_ms, 2)
        # Compute network/flush overhead for debugging
        send_overhead = duration_ms - route_return_ms
        if send_overhead > 0:
            metadata["send_overhead_ms"] = round(send_overhead, 2)

    emit_structured_log(
        component="ui-access",
        message=message,
        severity=severity,
        run_label=run_label,
        run_id="",
        metadata=metadata,
    )


# NOTE: _refresh_diagnostic_pack_latest and _export_usefulness_review_for_run
# are imported from server_execution_side_effects for backward compatibility.
# See import section above.


# Safe loopback hosts that don't require --unsafe-bind
_SAFE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_exposed_host(host: str) -> bool:
    """Check if the host is exposed (non-loopback).

    Safe loopback hosts: 127.0.0.1, localhost, ::1
    Unsafe/exposed hosts: 0.0.0.0, ::, external IPs, non-loopback hostnames.
    """
    return host.lower() not in _SAFE_LOOPBACK_HOSTS


def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
    unsafe_bind: bool = False,
    auth_token: str | None = None,
) -> None:
    # Check for exposed host binding
    if _is_exposed_host(host):
        if not unsafe_bind:
            print(
                f"ERROR: Refusing to bind to exposed address '{host}' without --unsafe-bind.",
                file=sys.stderr,
            )
            print(
                "The UI/API has mutation endpoints (POST /api/next-check-approval, "
                "/api/next-check-execution, /api/deterministic-next-check/promote, etc.)",
                file=sys.stderr,
            )
            print(
                "To bind to non-loopback addresses, use --unsafe-bind to acknowledge the risk.",
                file=sys.stderr,
            )
            print(
                "Alternatively, bind to a loopback address (127.0.0.1, localhost, or ::1) "
                "and use port-forwarding for remote access.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # Host is exposed and unsafe_bind is True - print security warning
        print(
            f"WARNING: Starting operator UI on exposed address '{host}:{port}'.",
            file=sys.stderr,
        )
        print(
            "The UI/API has mutation endpoints that can modify cluster state.",
            file=sys.stderr,
        )
        # Strong warning if no token configured
        if not auth_token:
            print(
                "WARNING: No K9B_UI_TOKEN configured. Mutation endpoints are unprotected.",
                file=sys.stderr,
            )
            print(
                "Set the K9B_UI_TOKEN environment variable or --auth-token CLI flag to protect them.",
                file=sys.stderr,
            )
        print(
            "Ensure this host is only accessible from trusted networks, "
            "or use a reverse proxy with authentication in front of this service.",
            file=sys.stderr,
        )
        print(file=sys.stderr)

    # Normalize and validate runs_dir
    normalized_runs_dir = _normalize_runs_dir(runs_dir)
    _validate_runs_dir(normalized_runs_dir)

    assets = static_dir or DEFAULT_STATIC_DIR
    handler = functools.partial(
        HealthUIRequestHandler,
        runs_dir=normalized_runs_dir,
        static_dir=assets,
        auth_token=auth_token,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"Operator UI listening on http://{host}:{port}/ (runs: {normalized_runs_dir}, assets: {assets})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down operator UI server", file=sys.stderr)
        server.shutdown()
    finally:
        server.server_close()


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
        """Reset all per-request state to measure actual request processing time.

        This must be called at the start of each do_GET/do_POST to ensure
        duration_ms reflects request processing, not connection idle time.
        """
        self._start_time = time.perf_counter()
        self._request_id = ""
        self._route_return_ms = 0.0
        self._response_bytes = 0
        self._status_code = 200

    def _get_client_ip(self) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (reverse proxy)
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()
        # Fall back to direct connection
        client = self.client_address
        if isinstance(client, tuple):
            return client[0]
        return str(client)

    def _get_run_label(self) -> str:
        """Extract run_label from the current context if available."""
        # Try to get run_label from the loaded context
        # This is a best-effort attempt; if context can't be loaded, return empty
        try:
            context = self._load_context()
            if context and context.run:
                return context.run.run_label or ""
        except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
            # Narrowed: _load_context already handles file/JSON errors;
            # remaining candidates are simple attribute accesses
            pass
        return ""

    def do_GET(self) -> None:
        # CRITICAL: Reset timing state FIRST to measure actual request processing time
        # This fixes the bug where duration_ms included connection/handler lifetime
        # instead of just the request processing time
        self._reset_request_state()

        # Delegate to extracted route handler (re-exported at module level)
        handle_get_request(self)

    def do_POST(self) -> None:
        # CRITICAL: Reset timing state FIRST to measure actual request processing time
        # This fixes the bug where duration_ms included connection/handler lifetime
        # instead of just the request processing time
        self._reset_request_state()

        # Delegate to extracted route handler (re-exported at module level)
        handle_post_request(self)

    def set_request_timing(self, request_id: str, route_return_ms: float) -> None:
        """Set correlation and timing info for access log from server_reads.

        Called by server_reads.py after building the route payload but before
        sending the response. This allows the access log to include correlation
        IDs and route timing alongside the actual request duration.

        Args:
            request_id: Correlation ID for linking access log to route timing logs
            route_return_ms: Time from request start to route handler returning (before send)
        """
        self._request_id = request_id
        self._route_return_ms = route_return_ms

    def _log_access_completion(self) -> None:
        """Log access completion with latency and status."""
        if self._start_time == 0.0:
            return

        duration_ms = (time.perf_counter() - self._start_time) * 1000

        # Read client_request_id from request headers
        client_request_id = self.headers.get("X-K9B-Client-Request-Id", "")

        _log_request_access(
            method=self._request_method,
            path=self._request_path,
            query=self._request_query,
            status_code=self._status_code,
            duration_ms=duration_ms,
            response_bytes=self._response_bytes,
            client_ip=self._get_client_ip(),
            run_label=self._get_run_label() if self._request_path.startswith("/api/") else "",
            is_static_asset=self._is_static,
            request_id=self._request_id,
            route_return_ms=self._route_return_ms,
            client_request_id=client_request_id,
        )

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
        if not isinstance(candidates, Sequence):
            return None, None
        entries = list(candidates)
        found_entry: Mapping[str, object] | None = None
        found_position: int | None = None
        if requested_candidate_id:
            for idx, entry in enumerate(entries):
                if not isinstance(entry, Mapping):
                    continue
                entry_id = entry.get("candidateId")
                if isinstance(entry_id, str) and entry_id == requested_candidate_id:
                    found_entry = dict(entry)
                    found_position = idx
                    break
        if found_entry is None and requested_candidate_index is not None:
            if 0 <= requested_candidate_index < len(entries):
                entry = entries[requested_candidate_index]
                if isinstance(entry, Mapping):
                    found_entry = dict(entry)
                    found_position = requested_candidate_index
        if found_entry is None:
            return None, None
        candidate_index_value: int | None = None
        explicit_index = found_entry.get("candidateIndex")
        if isinstance(explicit_index, int):
            candidate_index_value = explicit_index
        elif found_position is not None:
            candidate_index_value = found_position
        elif requested_candidate_index is not None:
            candidate_index_value = requested_candidate_index
        return found_entry, candidate_index_value

    def _find_candidate_in_all_plan_artifacts(
        self,
        run_id: str,
        candidate_id: str | None,
        candidate_index: int | None,
    ) -> tuple[dict[str, object] | None, int | None, Path | None]:
        """Search for a candidate across all planner artifacts for the given run.

        This handles cases where the plan artifact path in the queue may differ from
        the current next_check_plan.artifact_path (e.g., due to plan regeneration).

        Returns tuple of (candidate_entry, resolved_index, plan_path) if found.
        """
        # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
        from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return empty result
            return None, None, None

        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")

        # First try the promoted entries (deterministic checks)
        promotions = collect_promoted_queue_entries(self._health_root, validated_run_id)
        if promotions:
            entry, idx = self._resolve_plan_candidate(
                promotions,
                candidate_id,
                candidate_index,
            )
            if entry is not None and idx is not None:
                return dict(entry), idx, None

        # Scan all external-analysis artifacts for planner artifacts
        external_analysis_dir = self._health_root / "external-analysis"
        if external_analysis_dir.exists():
            # SECURITY: run_id validated by validate_run_id() before glob construction
            for artifact_file in external_analysis_dir.glob(glob_pattern):
                try:
                    artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                    # Check if this is a planning artifact
                    purpose = artifact_data.get("purpose")
                    if purpose != "next-check-planning":
                        continue

                    payload = artifact_data.get("payload", {})
                    candidates = payload.get("candidates", [])
                    entry, idx = self._resolve_plan_candidate(
                        candidates if isinstance(candidates, Sequence) else (),
                        candidate_id,
                        candidate_index,
                    )
                    if entry is not None and idx is not None:
                        # Return full relative path within runs_dir (external-analysis/filename)
                        return dict(entry), idx, Path("external-analysis") / artifact_file.name
                except (OSError, json.JSONDecodeError):
                    # Skip malformed/unreadable artifacts, continue searching
                    # File I/O errors (OSError) and JSON parse errors (JSONDecodeError) are non-fatal
                    continue

        return None, None, None

    def _find_candidate_in_all_plan_artifacts_from_health_root(
        self,
        health_root: Path,
        run_id: str,
        candidate_id: str | None,
        candidate_index: int | None,
    ) -> tuple[dict[str, object] | None, int | None, Path | None]:
        """Search for a candidate across all planner artifacts in health_root for the given run.

        This is the fixed version that uses health_root (runs/health/external-analysis/)
        instead of runs_root (runs/external-analysis/).

        Returns tuple of (candidate_entry, resolved_index, plan_path) if found.
        """
        # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
        from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return empty result
            return None, None, None

        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")

        # First try the promoted entries (deterministic checks) from health_root
        promotions = collect_promoted_queue_entries(health_root, validated_run_id)
        if promotions:
            entry, idx = self._resolve_plan_candidate(
                promotions,
                candidate_id,
                candidate_index,
            )
            if entry is not None and idx is not None:
                return dict(entry), idx, None

        # Scan all external-analysis artifacts for planner artifacts in health_root
        external_analysis_dir = health_root / "external-analysis"
        if external_analysis_dir.exists():
            # SECURITY: run_id validated by validate_run_id() before glob construction
            for artifact_file in external_analysis_dir.glob(glob_pattern):
                try:
                    artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                    # Check if this is a planning artifact
                    purpose = artifact_data.get("purpose")
                    if purpose != "next-check-planning":
                        continue

                    payload = artifact_data.get("payload", {})
                    candidates = payload.get("candidates", [])
                    entry, idx = self._resolve_plan_candidate(
                        candidates if isinstance(candidates, Sequence) else (),
                        candidate_id,
                        candidate_index,
                    )
                    if entry is not None and idx is not None:
                        # Return full relative path within health_root (external-analysis/filename)
                        return dict(entry), idx, Path("external-analysis") / artifact_file.name
                except (OSError, json.JSONDecodeError):
                    # Skip malformed/unreadable artifacts, continue searching
                    # File I/O errors (OSError) and JSON parse errors (JSONDecodeError) are non-fatal
                    continue

        return None, None, None

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
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)


def _determine_execution_state_from_artifact(artifact: ExternalAnalysisArtifact) -> str:
    """Determine execution state from an execution artifact.

    This is a local version that works directly with the artifact object,
    used to compute execution state for the API response without needing
    to build a full NextCheckExecutionRecord.

    Args:
        artifact: The execution artifact from manual next-check execution.

    Returns:
        Execution state string: "executed-success", "executed-failed", or "timed-out".
    """
    if artifact.timed_out:
        return "timed-out"
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return "executed-success"
    return "executed-failed"
