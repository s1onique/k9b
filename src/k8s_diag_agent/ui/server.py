"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import functools
import json
import logging
import mimetypes
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, cast
from urllib.parse import unquote

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from ..external_analysis.deterministic_next_check_promotion import (
    collect_promoted_queue_entries,
)
from ..structured_logging import emit_structured_log
from .model import UIIndexContext, build_ui_context, load_ui_index
from .server_shared import _compute_health_root, _normalize_runs_dir, _validate_runs_dir

# Route patterns for path matching
_RUN_ALERTMANAGER_SOURCE_ACTION = re.compile(
    r"^/api/runs/([^/]+)/alertmanager-sources/([^/]+)/action$"
)


# Re-export next-check mutation handlers from server_next_checks
# Re-export feedback mutation handlers from server_feedback
from .server_alertmanager import (  # noqa: E402, F401
    handle_alertmanager_source_action,
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

# Re-export read-only helpers from server_read_support for backward compatibility
from .server_read_support import (  # noqa: E402, F401
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
    _get_field_with_default,
    _get_field_with_fallback,
    _load_alertmanager_review_artifacts,
    _load_notifications_for_run,
    _load_proposals_for_run,
    _merge_alertmanager_review_into_history_entry,
    _scan_external_analysis,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"

# In-memory cache for run payloads to avoid repeated expensive computation
# Key: (run_id, ui_index_mtime), Value: (cached_payload, cached_promotions)
_run_payload_cache: dict[tuple[str, float], tuple[dict[str, Any], list[dict[str, object]]]] = {}
_run_payload_cache_lock = Lock()
# Maximum cache entries to prevent unbounded memory growth
_MAX_CACHE_ENTRIES = 10

# In-memory cache for runs list payload - keyed by runs_dir mtime
# This avoids scanning reviews/ and external-analysis/ directories on every request
_runs_list_cache: dict[str, tuple[dict[str, Any], float]] = {}  # key -> (payload, mtime)
_runs_list_cache_lock = Lock()

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

    emit_structured_log(
        component="ui-access",
        message=message,
        severity=severity,
        run_label=run_label,
        run_id="",
        metadata={
            "method": method,
            "path": path,
            "query": query,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "response_bytes": response_bytes,
            "client_ip": client_ip,
            "run_label": run_label,
        },
    )


def _refresh_diagnostic_pack_latest(run_id: str, runs_dir: Path) -> bool:
    """Refresh the latest diagnostic pack mirror files after manual next-check execution.

    This rebuilds the review_bundle.json and review_input_14b.json files in the
    'latest' directory so the UI always points to current content after operator
    actions.

    Args:
        run_id: The current run ID
        runs_dir: Path to the runs directory

    Returns:
        True if refresh succeeded, False otherwise.
    """
    import subprocess as _subprocess

    # Try multiple locations for the build script to handle both local and containerized environments
    build_script: Path | None = None
    script_locations_tried: list[str] = []

    # First try the scripts directory relative to project root
    primary_script = _SCRIPTS_DIR / "build_diagnostic_pack.py"
    script_locations_tried.append(str(primary_script))
    if primary_script.exists():
        build_script = primary_script

    # Fall back to current working directory (useful in containerized environments)
    if build_script is None:
        cwd_script = Path.cwd() / "scripts" / "build_diagnostic_pack.py"
        script_locations_tried.append(str(cwd_script))
        if cwd_script.exists():
            build_script = cwd_script

    # Last resort: try the script name directly in common locations
    if build_script is None:
        for search_path in [Path.cwd(), Path("/app"), Path("/app/scripts")]:
            candidate = search_path / "build_diagnostic_pack.py"
            script_locations_tried.append(str(candidate))
            if candidate.exists():
                build_script = candidate
                break

    if build_script is None:
        # All locations failed - emit structured log with diagnostic info
        emit_structured_log(
            component="pack-refresh",
            message="Cannot refresh diagnostic pack: build script not found",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "refresh_root": str(_SCRIPTS_DIR),
                "script_path_attempted": script_locations_tried,
                "failed_stage": "script_discovery",
                "error_summary": "build script not found in any searched location",
            },
        )
        return False

    # Determine the correct Python executable to use
    # In containerized environments, use sys.executable; in local dev, also prefer sys.executable
    python_exe = sys.executable
    if not python_exe:
        # Fallback for edge cases
        python_exe = "python3"

    runs_dir_str = str(runs_dir)
    health_root = runs_dir / "health"
    build_cmd = [
        python_exe,
        str(build_script),
        "--run-id",
        run_id,
        "--runs-dir",
        runs_dir_str,
    ]

    try:
        # Emit structured log for start of pack refresh
        emit_structured_log(
            component="pack-refresh",
            message="Starting diagnostic pack refresh",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "python_executable": python_exe,
                "command": build_cmd,
            },
        )

        # Run the build script - it will write the latest mirror files as part of its work
        _subprocess.run(
            build_cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for pack building
        )

        # Emit structured log for successful refresh
        emit_structured_log(
            component="pack-refresh",
            message="Diagnostic pack latest mirror refreshed successfully",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
            },
        )

        # Also export the run-scoped usefulness review artifact for Recent runs Download link
        _export_usefulness_review_for_run(run_id, runs_dir)

        return True
    except _subprocess.CalledProcessError as exc:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "script_execution",
                "returncode": exc.returncode,
                "error_summary": f"script returned non-zero: {exc.returncode}",
                "stderr_preview": exc.stderr[:500] if exc.stderr else "",
            },
        )
        return False
    except _subprocess.TimeoutExpired:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror: timeout",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "script_timeout",
                "error_summary": "build script timed out after 120 seconds",
            },
        )
        return False
    except OSError as exc:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "os_error",
                "error_summary": str(exc),
            },
        )
        return False


def _export_usefulness_review_for_run(run_id: str, runs_dir: Path) -> bool:
    """Export run-scoped usefulness review artifact after pack refresh.

    This produces the run-scoped JSON file at:
    runs/health/diagnostic-packs/<run_id>/next_check_usefulness_review.json

    The Recent runs Download link in the UI requires this exact run-scoped file
    to exist for the Download button to appear.

    Args:
        run_id: The current run ID
        runs_dir: Path to the runs directory

    Returns:
        True if export succeeded, False otherwise.
    """
    try:
        # Import here to avoid circular imports
        from scripts.export_next_check_usefulness_review import (
            export_next_check_usefulness_review,
        )

        emit_structured_log(
            component="pack-refresh",
            message="Exporting run-scoped usefulness review artifact",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "operation": "export_usefulness_review",
            },
        )

        # Export to run-scoped path only (not /latest/ mirror)
        # The /latest/ mirror is already created by build_diagnostic_pack.py
        export_result = export_next_check_usefulness_review(
            runs_dir,
            run_id=run_id,
            use_run_scoped_path=True,
        )

        # Extract output path from result
        output_path = export_result.output_path
        if output_path is None:
            emit_structured_log(
                component="pack-refresh",
                message="Export returned no output path",
                run_id=run_id,
                run_label="",
                severity="WARNING",
                metadata={
                    "run_id": run_id,
                    "operation": "export_usefulness_review",
                },
            )
            return False

        # Verify the file was written
        file_exists = output_path.exists()

        emit_structured_log(
            component="pack-refresh",
            message="Exported run-scoped usefulness review artifact",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "output_path": str(output_path),
                "file_exists": file_exists,
                "operation": "export_usefulness_review",
            },
        )

        return file_exists
    except Exception as exc:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to export run-scoped usefulness review artifact",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "operation": "export_usefulness_review",
                "error": str(exc),
            },
        )
        return False


def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
) -> None:
    # Normalize and validate runs_dir
    normalized_runs_dir = _normalize_runs_dir(runs_dir)
    _validate_runs_dir(normalized_runs_dir)

    assets = static_dir or DEFAULT_STATIC_DIR
    handler = functools.partial(HealthUIRequestHandler, runs_dir=normalized_runs_dir, static_dir=assets)
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

    def __init__(self, *args: object, runs_dir: Path, static_dir: Path, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        self.static_dir = static_dir
        self._health_root = _compute_health_root(runs_dir)
        # Access logging state
        self._start_time: float = 0.0
        self._request_method: str = ""
        self._request_path: str = ""
        self._request_query: str = ""
        self._is_static: bool = False
        self._response_bytes: int = 0
        self._status_code: int = 200
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

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
        except Exception:
            pass
        return ""

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        self._request_method = "GET"
        self._request_path = route
        self._request_query = query
        self._is_static = not route.startswith("/api/") and route != "/artifact"
        self._start_time = time.perf_counter()
        self._status_code = 200
        self._response_bytes = 0

        try:
            if route.startswith("/api/"):
                self._handle_api(route, query)
            elif route == "/artifact":
                from .server_static import serve_artifact
                serve_artifact(self, query)
            else:
                from .server_static import serve_static
                serve_static(self, route)
        except Exception:
            # Log any uncaught exceptions as ERROR access logs
            self._status_code = 500
            self._log_access_completion()
            raise
        else:
            self._log_access_completion()

    def do_POST(self) -> None:
        route, _, _ = self.path.partition("?")
        self._request_method = "POST"
        self._request_path = route
        self._request_query = ""
        self._is_static = False
        self._start_time = time.perf_counter()
        self._status_code = 200
        self._response_bytes = 0

        try:
            # Delegate next-check mutation handlers to server_next_checks module
            if route == "/api/deterministic-next-check/promote":
                handle_deterministic_promotion(self)
                return
            if route == "/api/next-check-execution":
                handle_next_check_execution(self)
                return
            if route == "/api/next-check-approval":
                handle_next_check_approval(self)
                return
            if route == "/api/next-check-execution-usefulness":
                handle_usefulness_feedback(self)
                return
            if route == "/api/alertmanager-relevance-feedback":
                handle_alertmanager_relevance_feedback(self)
                return
            if route == "/api/run-batch-next-check-execution":
                self._handle_run_batch_next_check_execution()
                return
            # Alertmanager source action endpoint: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action
            # Body: { "action": "promote"|"disable", "reason": "..." }
            runs_am_source_match = _RUN_ALERTMANAGER_SOURCE_ACTION.match(route)
            if runs_am_source_match:
                run_id = runs_am_source_match.group(1)
                # Decode URL-encoded source_id before lookup/validation
                # e.g., "crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager" -> "crd:monitoring/kube-prometheus-stack-alertmanager"
                source_id = unquote(runs_am_source_match.group(2))
                handle_alertmanager_source_action(self, run_id, source_id)
                return
            self._status_code = 404
            self._send_text(404, "Not Found")
        except Exception:
            # Log any uncaught exceptions as ERROR access logs
            self._status_code = 500
            self._log_access_completion()
            raise
        else:
            self._log_access_completion()

    def _log_access_completion(self) -> None:
        """Log access completion with latency and status."""
        if self._start_time == 0.0:
            return

        duration_ms = (time.perf_counter() - self._start_time) * 1000

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
        # First try the promoted entries (deterministic checks)
        promotions = collect_promoted_queue_entries(self._health_root, run_id)
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
            # Find all next-check-plan artifacts for this run
            for artifact_file in external_analysis_dir.glob(f"{run_id}-next-check-plan*.json"):
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
                except Exception:
                    # Skip malformed artifacts, continue searching
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
        # First try the promoted entries (deterministic checks) from health_root
        promotions = collect_promoted_queue_entries(health_root, run_id)
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
            # Find all next-check-plan artifacts for this run
            for artifact_file in external_analysis_dir.glob(f"{run_id}-next-check-plan*.json"):
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
                except Exception:
                    # Skip malformed artifacts, continue searching
                    continue

        return None, None, None

    def _handle_run_batch_next_check_execution(self) -> None:
        """Handle batch execution of next-check candidates for a specific run.

        Accepts run_id in the payload and executes all eligible candidates
        that haven't been executed yet.
        """
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length <= 0:
            self._send_json({"error": "Request body required"}, 400)
            return
        try:
            raw_payload = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_payload)
        except Exception:
            self._send_json({"error": "Invalid JSON payload"}, 400)
            return

        run_id = payload.get("runId")
        if not isinstance(run_id, str) or not run_id:
            self._send_json({"error": "runId is required"}, 400)
            return

        # Default to False (actual execution) - UI Execute button should send dryRun: false
        # Preview/dry-run can be triggered by explicitly sending dryRun: true
        # Handle both boolean and string values - JSON.stringify converts boolean to "true"/"false" strings
        dry_run_raw = payload.get("dryRun", False)
        if isinstance(dry_run_raw, bool):
            dry_run = dry_run_raw
        elif isinstance(dry_run_raw, str):
            # Handle string "true"/"false" from JSON.stringify (converts boolean to string)
            dry_run = dry_run_raw.lower() == "true"
        else:
            dry_run = bool(dry_run_raw)

        # Log the parsed dry_run value for observability
        emit_structured_log(
            component="batch-execution",
            message="Batch execution request parsed",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "dry_run_parsed": dry_run,
                "dry_run_source": "request_payload" if "dryRun" in payload else "default_false",
            },
        )

        # Import the batch execution function from the package
        try:
            from k8s_diag_agent.batch import run_batch_next_checks
        except Exception as exc:
            self._send_json({"error": f"Failed to load batch execution module: {exc}"}, 500)
            return

        try:
            result = run_batch_next_checks(
                runs_dir=self.runs_dir,
                run_id=run_id,
                dry_run=dry_run,
            )
        except FileNotFoundError:
            self._send_json({"error": f"Run not found: {run_id}"}, 404)
            return
        except Exception as exc:
            self._send_json({"error": f"Batch execution failed: {exc}"}, 500)
            return

        # Convert result to response
        # Use "would_execute" for dry-run mode to clearly distinguish from actual execution
        execution_mode = "would_execute" if dry_run else "executed"
        response = {
            "status": "success",
            "summary": f"Batch execution {execution_mode} for run {run_id}",
            "runId": run_id,
            "dryRun": dry_run,
            "totalCandidates": result.total_candidates,
            "eligibleCandidates": result.eligible_candidates,
            "executedCount": result.executed_count,
            "skippedAlreadyExecuted": result.skipped_already_executed,
            "skippedIneligible": result.skipped_ineligible,
            "failedCount": result.failed_count,
            "successCount": result.success_count,
        }

        # If not dry run, refresh diagnostic pack and update UI read model
        if not dry_run and result.executed_count > 0:
            _refresh_diagnostic_pack_latest(run_id, self.runs_dir)
            _persist_batch_execution_history_to_ui_index(self.runs_dir, run_id)

        self._send_json(response)

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
        except Exception as exc:  # pragma: no cover - read-model may be malformed
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

        # Check if the run exists by looking for its review artifact
        reviews_dir = self.runs_dir / "health" / "reviews"
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

        # Derive run metadata from review artifact
        run_label = review_data.get("run_label", run_id)
        timestamp = review_data.get("timestamp", datetime.now(UTC).isoformat())

        # Get cluster info from review's selected_drilldowns
        selected_drilldowns = review_data.get("selected_drilldowns", [])
        cluster_count = len(selected_drilldowns) if isinstance(selected_drilldowns, list) else 0

        # Build clusters list from review data
        clusters = _build_clusters_from_review(run_id, review_data, self.runs_dir)

        # Scan for drilldowns belonging to this run
        drilldown_count = _count_run_artifacts(self.runs_dir / "health" / "drilldowns", run_id)

        # Scan for proposals belonging to this run
        proposals_data, proposal_count = _load_proposals_for_run(self.runs_dir / "health" / "proposals", run_id)

        # Scan for external-analysis artifacts for this run
        external_analysis_dir = self._health_root / "external-analysis"
        external_analysis_data = _scan_external_analysis(external_analysis_dir, run_id)
        external_analysis_count = external_analysis_data.get("count", 0)

        # Scan for notifications for this run
        notification_history, notification_count = _load_notifications_for_run(
            self.runs_dir / "health" / "notifications", run_id
        )

        # Build drilldown availability from review clusters + drilldown artifacts
        drilldown_availability = _build_drilldown_availability_from_review(
            review_data, self.runs_dir / "health" / "drilldowns", run_id
        )

        # Find review enrichment artifact
        review_enrichment = _find_review_enrichment(external_analysis_dir, run_id)

        # Build review_enrichment_status for past runs.
        # For past runs, we derive status from the enrichment artifact and
        # the review artifact's config metadata, independent of current policy.
        has_enrichment_artifact = review_enrichment is not None
        review_enrichment_status: dict[str, object] | None = None

        if not has_enrichment_artifact:
            # Derive status from run config in review artifact.
            # Use the dedicated helper that only checks run-level config,
            # not current policy (which may have changed since the run).
            external_analysis_config = review_data.get("external_analysis_settings")
            run_config: dict[str, object] | None = None
            if isinstance(external_analysis_config, dict):
                candidate = external_analysis_config.get("review_enrichment")
                # Guard against malformed nested config (e.g., "review_enrichment": "bogus")
                if isinstance(candidate, dict):
                    run_config = candidate

            review_enrichment_status = _build_review_enrichment_status_for_past_run(run_config)

        # Find next-check plan artifact
        next_check_plan = _find_next_check_plan(external_analysis_dir, run_id)

        # Build next_check_queue from plan if exists
        next_check_queue = _build_queue_from_plan(next_check_plan)

        # Build next_check_execution_history
        execution_history = _build_execution_history(external_analysis_dir, run_id)

        # Build llm_stats from external-analysis artifacts for this run
        llm_stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

        # Load Alertmanager compact artifact if available
        # Alertmanager artifacts are written at health_root, not external-analysis/
        alertmanager_compact_entry = None
        compact_path = self._health_root / f"{run_id}-alertmanager-compact.json"
        if compact_path.exists():
            try:
                import json as _json
                compact_raw = _json.loads(compact_path.read_text(encoding="utf-8"))
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
                    # Per-cluster breakdown for cluster-scoped UI panels
                    "by_cluster": compact_raw.get("by_cluster", []),
                }
            except Exception:
                pass  # Compact not available - non-fatal

        # Load Alertmanager sources inventory if available
        # Uses _serialize_alertmanager_sources from health/ui.py to apply operator overrides
        # Alertmanager artifacts are written at health_root, not external-analysis/
        alertmanager_sources_entry = None
        sources_path = self._health_root / f"{run_id}-alertmanager-sources.json"
        if sources_path.exists():
            # Import here to avoid circular import at module level
            from ..health.ui import _serialize_alertmanager_sources as _serialize_am_sources
            try:
                alertmanager_sources_entry = _serialize_am_sources(self._health_root, run_id)
            except Exception:
                pass  # Sources not available - non-fatal

        # Build run entry with artifact-backed values
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
            "historical_llm_stats": None,  # Historical stats are retained globally, not per-run
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

        # Build proposal status summary
        proposal_status_summary = _build_proposal_status_summary(proposals_data)

        # Build a minimal UI index structure with artifact-backed data
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
        
        # Stage 1: Read review artifacts
        reviews_scan_start = time.perf_counter()
        reviews_dir = health_root / "reviews"
        review_count = 0
        if reviews_dir.exists():
            review_count = len(list(reviews_dir.glob("*-review.json")))
        timings["reviews_scan_ms"] = (time.perf_counter() - reviews_scan_start) * 1000
        timings["review_files_count"] = review_count
        
        # Stage 2: Scan external-analysis for execution artifacts
        external_analysis_scan_start = time.perf_counter()
        external_analysis_dir = health_root / "external-analysis"
        execution_count = 0
        if external_analysis_dir.exists():
            execution_count = len(list(external_analysis_dir.glob("*-next-check-execution*.json")))
        timings["external_analysis_scan_ms"] = (time.perf_counter() - external_analysis_scan_start) * 1000
        timings["execution_files_scanned"] = execution_count
        
        # Stage 3: Build the runs list payload with inner timings
        payload_build_start = time.perf_counter()
        payload: dict[str, object]
        try:
            result = build_runs_list(self.runs_dir, _timings=True)
            if isinstance(result, tuple):
                raw_payload, inner_timings = result
                payload = cast(dict[str, object], raw_payload)
                # Merge inner timings into outer timings (cast values to float)
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
        payload = json.dumps(body, ensure_ascii=False)
        encoded = payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            self._send_text(500, f"Unable to read asset: {exc}")
            return
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


def _relative_path(base: Path, target: object | None) -> str | None:
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)


def _persist_batch_execution_history_to_ui_index(runs_dir: Path, run_id: str) -> None:
    """Update ui-index.json with execution history entries from batch execution.

    This mirrors the behavior of single next-check execution, which also updates
    the UI read model directly. Without this, batch executions would not appear
    in the Execution History section until the next health loop.

    Uses the same entry-building logic as _build_execution_history to ensure
    consistent field handling (candidateId, provenance fields, etc.).

    Args:
        runs_dir: Path to the runs directory
        run_id: The run ID to update
    """
    health_root = runs_dir / "health"
    ui_index_path = health_root / "ui-index.json"

    # Load existing ui-index.json
    try:
        index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "Failed to read ui-index.json for batch execution history update",
            extra={"ui_index": str(ui_index_path), "run_id": run_id},
        )
        return

    run_entry = index_data.get("run") or {}
    existing_history = list(run_entry.get("next_check_execution_history") or [])

    # Build complete history from current artifacts using the same logic
    # as _build_execution_history for consistency
    external_dir = health_root / "external-analysis"
    if not external_dir.exists():
        return

    # Use _build_execution_history to get properly-shaped entries with all fields
    fresh_history = _build_execution_history(external_dir, run_id)

    if not fresh_history:
        return

    # Track existing entries by (candidateIndex, timestamp) to avoid duplicates
    existing_keys: set[tuple[int | None, str]] = set()
    for entry in existing_history:
        idx = entry.get("candidateIndex")
        if isinstance(idx, int):
            idx_key: int | None = idx
        else:
            idx_key = None
        ts_val: str = cast(str, _get_field_with_fallback(entry, "timestamp") or "")
        existing_keys.add((idx_key, ts_val))

    # Merge: add entries not already present
    merged_history = list(existing_history)
    new_count = 0
    for entry in fresh_history:
        idx = entry.get("candidateIndex")
        if isinstance(idx, int):
            fresh_idx_key: int | None = idx
        else:
            fresh_idx_key = None
        fresh_ts: str = cast(str, entry.get("timestamp") or "")
        key = (fresh_idx_key, fresh_ts)
        if key not in existing_keys:
            merged_history.append(entry)
            new_count += 1
            existing_keys.add(key)

    # Sort by timestamp descending (most recent first), consistent with _build_execution_history
    merged_history.sort(key=lambda x: cast(str, x.get("timestamp") or ""), reverse=True)

    # Limit to 5 most recent, consistent with _build_execution_history
    merged_history = merged_history[:5]

    if new_count > 0:
        run_entry["next_check_execution_history"] = merged_history
        index_data["run"] = run_entry

        try:
            ui_index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug(
                "Persisted batch execution history to ui-index.json",
                extra={
                    "ui_index": str(ui_index_path),
                    "run_id": run_id,
                    "new_entries": new_count,
                    "total_entries": len(merged_history),
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist batch execution history to ui-index.json",
                extra={"ui_index": str(ui_index_path), "run_id": run_id, "error": str(exc)},
            )


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
