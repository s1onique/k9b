"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import functools
import json
import logging
import mimetypes
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, cast
from urllib.parse import parse_qs

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
    PackRefreshStatus,
    UsefulnessClass,
)
from ..external_analysis.deterministic_next_check_promotion import (
    build_promoted_candidate_id,
    collect_promoted_queue_entries,
    write_deterministic_next_check_promotion,
)
from ..external_analysis.manual_next_check import (
    ManualNextCheckError,
    execute_manual_next_check,
)
from ..external_analysis.next_check_approval import (
    log_next_check_approval_event,
    record_next_check_approval,
)
from ..health.ui import _derive_outcome_status
from ..structured_logging import emit_structured_log
from .api import (
    build_cluster_detail_payload,
    build_fleet_payload,
    build_proposals_payload,
    build_run_payload,
)
from .model import UIIndexContext, build_ui_context, load_ui_index
from .notifications import query_notifications

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


def _normalize_runs_dir(runs_dir: Path) -> Path:
    """Normalize runs_dir to the canonical parent directory.

    The canonical runs_dir can be either:
    - 'runs' (parent directory) - UI internally accesses runs/health/ subdirectory
    - 'runs/health' (leaf directory) - directly contains health artifacts

    This function detects which form is being used and normalizes appropriately.
    If user passes runs/health (where artifacts actually live), keep it.
    If user passes runs (parent), keep it.
    If runs/health is empty (no artifacts), normalize to parent runs.

    Args:
        runs_dir: The runs directory as provided by the user

    Returns:
        Normalized runs directory (either parent or leaf)
    """
    resolved = runs_dir.resolve()

    # Check if runs_dir itself is the health directory (e.g., runs/health)
    if resolved.name == "health":
        # Check if this directory itself contains health artifacts
        # (external-analysis, assessments, drilldowns are directly here)
        if any(
            (resolved / subdir).exists()
            for subdir in ["external-analysis", "assessments", "drilldowns"]
        ):
            logger.debug(
                "Kept runs_dir as health leaf directory",
                extra={"input": str(runs_dir), "resolved": str(resolved)},
            )
            return resolved

        # No artifacts in runs/health - normalize to parent runs
        parent = resolved.parent
        logger.debug(
            "Normalized runs_dir from leaf to parent",
            extra={"input": str(runs_dir), "normalized": str(parent)},
        )
        return parent

    # Check if runs_dir has a 'health' subdirectory with artifacts
    health_dir = resolved / "health"
    if health_dir.exists() and any(
        (health_dir / subdir).exists()
        for subdir in ["external-analysis", "assessments", "drilldowns"]
    ):
        logger.debug(
            "Kept runs_dir as parent (has health subdirectory)",
            extra={"input": str(runs_dir), "resolved": str(resolved)},
        )
        return resolved

    return resolved


def _validate_runs_dir(runs_dir: Path) -> None:
    """Validate that runs_dir has the expected structure.

    The canonical runs_dir should have a 'health' subdirectory (or be empty
    if no runs have been executed yet).

    Raises:
        ValueError: If runs_dir appears misconfigured
    """
    resolved = runs_dir.resolve()
    health_subdir = resolved / "health"

    # If neither the parent nor health subdir exists, warn but don't fail
    # This allows fresh startup before any health runs have been executed
    if not resolved.exists() and not health_subdir.exists():
        logger.warning(
            "runs_dir does not exist and may not have been initialized",
            extra={"runs_dir": str(resolved)},
        )
        return

    # If runs/health exists, this is the expected canonical structure
    if health_subdir.exists():
        return

    # Check if user passed runs/health directly (doubled-path bug symptom)
    if resolved.exists() and any(resolved.iterdir()):
        # runs/ exists but no health subdir - might be misconfigured
        logger.warning(
            "runs_dir may be misconfigured: expected parent 'runs' with 'health' subdirectory",
            extra={"runs_dir": str(resolved)},
        )


def _compute_health_root(runs_dir: Path) -> Path:
    """Compute the health root directory for artifact resolution.

    The health root is where artifact-backed source of truth lives:
    - If runs_dir is the parent (e.g., 'runs'), health_root = runs_dir / 'health'
    - If runs_dir is already the health leaf (e.g., 'runs/health'), health_root = runs_dir

    This distinction is critical because plan artifacts (external-analysis/*-next-check-plan.json)
    live under runs/health/external-analysis/, not directly under runs/external-analysis/.

    Args:
        runs_dir: The normalized runs directory

    Returns:
        The health root path for artifact resolution
    """
    resolved = runs_dir.resolve()

    # If runs_dir itself is the health directory, it's already the health root
    if resolved.name == "health":
        return resolved

    # Otherwise, compute health_root as runs_dir / "health"
    health_root = resolved / "health"

    # If health directory exists, use it; otherwise fall back to runs_dir
    # (allows operation before first health run completes)
    if health_root.exists():
        return health_root

    # Fall back to runs_dir if health doesn't exist yet
    return resolved


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
                self._serve_artifact(query)
            else:
                self._serve_static(route)
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
            if route == "/api/deterministic-next-check/promote":
                self._handle_deterministic_promotion()
                return
            if route == "/api/next-check-execution":
                self._handle_next_check_execution()
                return
            if route == "/api/next-check-approval":
                self._handle_next_check_approval()
                return
            if route == "/api/next-check-execution-usefulness":
                self._handle_usefulness_feedback()
                return
            if route == "/api/run-batch-next-check-execution":
                self._handle_run_batch_next_check_execution()
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
        # Handle /api/runs endpoint with caching and single-flight protection
        if route == "/api/runs":
            # CRITICAL: Acquire single-flight FIRST, then compute cache key inside critical section
            # This ensures all concurrent requests for the same logical resource see the same key
            # (filesystems have millisecond precision, so requests within same ms need same key)
            
            # First, acquire single-flight lock with a provisional key
            # We'll use a time-based key that ensures coalescing for requests within same second
            provisional_key = f"/api/runs:{self.runs_dir}"
            should_build, sf_result, sf_wait_start = _single_flight_acquire(provisional_key)

            if not should_build and sf_result is not None:
                # Wait for in-flight result (waiter role)
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
                        },
                    )
                    self._send_json(result)
                    return
                # If result is None (timeout or builder failed), fall through to build

            # Now compute cache key INSIDE the critical section (we hold single-flight)
            health_root = self.runs_dir / "health"
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

            runs_cache_key = f"{self.runs_dir}:{cache_mtime}"
            
            # Check cache under lock
            with _runs_list_cache_lock:
                cached = _runs_list_cache.get(str(self.runs_dir))
                if cached is not None:
                    cached_payload, cached_mtime = cached
                    if cached_mtime == cache_mtime:
                        # Cache hit - release single-flight and return cached
                        # This happens when: (1) this request got single-flight lock but cache was populated
                        # by another thread, or (2) single-flight coalesced with an in-flight build
                        _single_flight_release(provisional_key, cached_payload, success=True, result_type="cached")
                        
                        # Determine the true outcome based on result_type:
                        # - "builder" role with "cached" result = acquired lock but served from existing cache
                        #   (no new work done, result was already built by a previous request)
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
                            },
                        )
                        self._send_json(cached_payload)
                        return

            # Build the payload (builder role) - or rebuild if single-flight failed
            # Note: _build_runs_list_payload already emits its own timing log with inner timings
            runs_payload = self._build_runs_list_payload()

            # Release single-flight with the result - _single_flight_release handles the release log
            _single_flight_release(provisional_key, runs_payload, success=True, result_type="built")
            
            # The canonical payload outcome log is now emitted by _build_runs_list_payload()
            # which has all the detailed timing information. We don't duplicate here.

            self._send_json(runs_payload)
            return

        # Handle /api/notifications with caching and single-flight protection
        if route == "/api/notifications":
            params = parse_qs(query)
            # Build cache key from query params + notifications dir mtime
            notifications_dir = self.runs_dir / "health" / "notifications"
            cache_mtime = 0.0
            if notifications_dir.exists():
                try:
                    cache_mtime = notifications_dir.stat().st_mtime
                except OSError:
                    pass

            # Create cache key including all query params
            kind = params.get("kind", [None])[0] or ""
            cluster_label = params.get("cluster_label", [None])[0] or ""
            search = params.get("search", [None])[0] or ""
            limit = str(self._parse_limit(params.get("limit", [None])[0]) or 50)
            page = str(self._parse_page(params.get("page", [None])[0]))
            notifications_cache_key = f"{cache_mtime}:{kind}:{cluster_label}:{search}:{limit}:{page}"

            # Try single-flight to avoid duplicate concurrent builds
            sf_key = f"/api/notifications:{notifications_cache_key}"
            should_build, sf_result, sf_wait_start = _single_flight_acquire(sf_key)

            if not should_build and sf_result is not None:
                # Wait for in-flight result
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
                            "cache_key": notifications_cache_key[:50],  # Truncate for safety
                        },
                    )
                    self._send_json(result)
                    return

            # Build with caching - check cache first
            with _notifications_cache_lock:
                notifications_cached = _notifications_cache.get(notifications_cache_key)
                if notifications_cached is not None:
                    notifications_payload, notifications_mtime = notifications_cached
                    if notifications_mtime == cache_mtime:
                        # Release single-flight if we had it
                        if should_build:
                            _single_flight_release(sf_key, notifications_payload, success=True, result_type="cached")
                        # Log with explicit outcome - builder role but cache hit
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
                        self._send_json(notifications_payload)
                        return

            # Count notification files for observability
            notification_count = 0
            if notifications_dir.exists():
                notification_count = len(list(notifications_dir.glob("*.json")))
            
            # Build the payload
            try:
                payload = query_notifications(
                    self.runs_dir / "health",
                    kind=params.get("kind", [None])[0],
                    cluster_label=params.get("cluster_label", [None])[0],
                    search=params.get("search", [None])[0],
                    limit=self._parse_limit(params.get("limit", [None])[0]),
                    page=self._parse_page(params.get("page", [None])[0]),
                )
            except Exception as exc:
                logger.warning("Failed to build notifications payload", extra={"error": str(exc)})
                payload = {"notifications": [], "error": str(exc)}

            # Cache the built payload
            with _notifications_cache_lock:
                # Evict old entries if cache is full
                if len(_notifications_cache) >= _MAX_CACHE_ENTRIES:
                    oldest_key = next(iter(_notifications_cache))
                    del _notifications_cache[oldest_key]
                _notifications_cache[notifications_cache_key] = (payload, cache_mtime)

            # Release single-flight with result - _single_flight_release handles the release log
            if should_build:
                _single_flight_release(sf_key, payload, success=True, result_type="built")
                # The canonical payload outcome logging is handled by _single_flight_release
                # No additional log needed here - _build_runs_list_payload style

            self._send_json(payload)
            return

        # All other endpoints need the context from the current (possibly selected) run
        # Parse run_id from query string if provided
        params = parse_qs(query)
        selected_run_id = params.get("run_id", [None])[0]

        context = self._load_context(requested_run_id=selected_run_id)
        if context is None:
            return
        if route == "/api/run":
            # CRITICAL: Acquire single-flight FIRST, then compute cache key inside critical section
            # This ensures all concurrent requests for the same run see the same key
            
            # First, acquire single-flight lock with a provisional key based on run_id only
            # This ensures all concurrent requests for the same run coalesce
            provisional_key = f"/api/run:{context.run.run_id}"
            should_build, sf_result, sf_wait_start = _single_flight_acquire(provisional_key)

            if not should_build and sf_result is not None:
                # Wait for in-flight result (waiter role)
                result, wait_ms = _single_flight_wait(sf_result, sf_wait_start)
                if result is not None:
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
                            "cache_hit": True,
                            "single_flight_acquire": "waiter",
                            "single_flight_result": "waited",
                            "single_flight_key": provisional_key[:100],
                            "single_flight_wait_ms": round(wait_ms, 2),
                        },
                    )
                    self._send_json(result)
                    return
                # If result is None (timeout or builder failed), fall through to build

            # Now compute cache key INSIDE the critical section (we hold single-flight)
            timings: dict[str, float] = {}
            total_start = time.perf_counter()

            # Stage 1: Get ui-index.json mtime for cache key
            ui_index_mtime = 0.0
            ui_index_path = self.runs_dir / "health" / "ui-index.json"
            if ui_index_path.exists():
                ui_index_mtime = ui_index_path.stat().st_mtime
            timings["ui_index_read_ms"] = (time.perf_counter() - total_start) * 1000

            # Build cache key using the mtime we just read (inside single-flight)
            run_cache_key = (context.run.run_id, ui_index_mtime)
            
            # Check regular cache for existing payload (under the lock)
            with _run_payload_cache_lock:
                cached_run_payload: tuple[dict[str, Any], list[dict[str, object]]] | None = _run_payload_cache.get(run_cache_key)

            if cached_run_payload is not None:
                # Cache hit - release single-flight and return cached
                cached_payload, _ = cached_run_payload
                _single_flight_release(provisional_key, cached_payload, success=True, result_type="cached")
                total_duration = (time.perf_counter() - total_start) * 1000
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
                        "total_duration_ms": round(total_duration, 2),
                        "cache_hit": True,
                        "single_flight_acquire": "builder",
                        "single_flight_result": "cache_hit",
                        "cache_key": str(run_cache_key)[:100],
                    },
                )
                self._send_json(cached_payload)
                return

            # Cache miss - build the payload (builder role)
            context_load_start = time.perf_counter()
            # _load_context was already called above, so context is already loaded
            timings["context_load_ms"] = (time.perf_counter() - context_load_start) * 1000

            # Stage 3: Load promotions (optimized with glob pattern + early run_id filter)
            promotions_load_start = time.perf_counter()
            
            # Sub-stage 3a: Find promotion files with glob pattern
            promoted_glob_start = time.perf_counter()
            external_analysis_dir = self._health_root / "external-analysis"
            promotion_glob_count = 0
            if external_analysis_dir.exists():
                promotion_files = list(external_analysis_dir.glob("*-next-check-promotion-*.json"))
                promotion_glob_count = len(promotion_files)
            timings["promoted_glob_ms"] = (time.perf_counter() - promoted_glob_start) * 1000
            timings["promotion_glob_count"] = promotion_glob_count
            
            # Sub-stage 3b: Load promotions (uses optimized collect_promoted_queue_entries)
            promotions = collect_promoted_queue_entries(self._health_root, context.run.run_id)
            timings["promotions_load_ms"] = (time.perf_counter() - promotions_load_start) * 1000
            timings["promotions_count"] = len(promotions)

            # Stage 4: Build the run payload
            payload_build_start = time.perf_counter()
            run_payload = build_run_payload(context, promotions=promotions)
            timings["payload_build_ms"] = (time.perf_counter() - payload_build_start) * 1000

            # Stage 5: Serialize to JSON
            serialize_start = time.perf_counter()
            _ = json.dumps(run_payload, ensure_ascii=False)  # Measure only, result not used
            timings["serialize_ms"] = (time.perf_counter() - serialize_start) * 1000

            # Count files scanned for context
            external_analysis_dir = self._health_root / "external-analysis"
            external_analysis_count = 0
            if external_analysis_dir.exists():
                external_analysis_count = len(list(external_analysis_dir.glob(f"{context.run.run_id}-*.json")))
            timings["external_analysis_files_scanned"] = external_analysis_count

            notifications_dir = self.runs_dir / "health" / "notifications"
            notification_count = 0
            if notifications_dir.exists():
                notification_count = len(list(notifications_dir.glob("*.json")))
            timings["notification_files_scanned"] = notification_count

            # Cache the built payload
            with _run_payload_cache_lock:
                # Evict old entries if cache is full
                if len(_run_payload_cache) >= _MAX_CACHE_ENTRIES:
                    # Remove oldest entry (first key in dict)
                    cache_keys = list(_run_payload_cache.keys())
                    oldest_cache_key: tuple[str, float] = cache_keys[0]
                    del _run_payload_cache[oldest_cache_key]
                _run_payload_cache[run_cache_key] = (run_payload, promotions)  # type: ignore[assignment]

            # Release single-flight with result and log as builder
            _single_flight_release(provisional_key, run_payload, success=True, result_type="built")

            total_duration = (time.perf_counter() - total_start) * 1000
            timings["total_duration_ms"] = total_duration

            # Emit structured timing log with deeper cold-path breakdown
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
                    "total_duration_ms": round(timings.get("total_duration_ms", 0), 2),
                    "context_load_ms": round(timings.get("context_load_ms", 0), 2),
                    "ui_index_read_ms": round(timings.get("ui_index_read_ms", 0), 2),
                    # Cold-path breakdown: promotions loading
                    "promotions_load_ms": round(timings.get("promotions_load_ms", 0), 2),
                    "promoted_glob_ms": round(timings.get("promoted_glob_ms", 0), 2),
                    "promotion_glob_count": timings.get("promotion_glob_count", 0),
                    # Payload building
                    "payload_build_ms": round(timings.get("payload_build_ms", 0), 2),
                    "serialize_ms": round(timings.get("serialize_ms", 0), 2),
                    # File counts (observability)
                    "external_analysis_files_scanned": timings.get("external_analysis_files_scanned", 0),
                    "notification_files_scanned": timings.get("notification_files_scanned", 0),
                    "promotions_count": timings.get("promotions_count", 0),
                    "cache_hit": False,
                    "single_flight_acquire": "builder",
                    "single_flight_result": "built",
                    "cache_key": str(run_cache_key)[:100],
                    "single_flight_key": provisional_key[:100],
                },
            )

            self._send_json(run_payload)
            return
        if route == "/api/fleet":
            self._send_json(build_fleet_payload(context))
            return
        if route == "/api/proposals":
            self._send_json(build_proposals_payload(context))
            return
        if route == "/api/cluster-detail":
            params = parse_qs(query)
            label = params.get("cluster_label", [None])[0]
            self._send_json(build_cluster_detail_payload(context, cluster_label=label))
            return
        self._send_text(404, "Not Found")

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

    def _handle_next_check_execution(self) -> None:
        context = self._load_context()
        if context is None:
            return
        plan = context.run.next_check_plan
        if not plan or not plan.artifact_path:
            self._send_json({"error": "Next-check plan unavailable"}, 400)
            return
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
        candidate_index_raw = payload.get("candidateIndex")
        candidate_index = candidate_index_raw if isinstance(candidate_index_raw, int) else None
        if candidate_index_raw is not None and candidate_index is None:
            self._send_json({"error": "candidateIndex must be an integer"}, 400)
            return
        request_cluster = payload.get("clusterLabel")
        if not isinstance(request_cluster, str) or not request_cluster:
            self._send_json({"error": "clusterLabel is required"}, 400)
            return
        candidate_id_raw = payload.get("candidateId")
        candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) and candidate_id_raw else None
        if candidate_id is None and candidate_index is None:
            self._send_json({"error": "candidateId or candidateIndex is required"}, 400)
            return

        # Extract planArtifactPath from request if provided
        plan_artifact_path_from_request = payload.get("planArtifactPath")
        cluster_label = payload.get("clusterLabel")

        # Compute health_root for artifact resolution - this is critical!
        # Plan artifacts live under runs/health/external-analysis/, not runs/external-analysis/
        health_root = _compute_health_root(self.runs_dir)
        runs_root = self.runs_dir.resolve()
        health_root_resolved = health_root.resolve()

        # Try the primary plan artifact first
        candidate_entry: dict[str, object] | None = None
        resolved_index: int | None = None
        plan_path_used: Path | None = None

        # Diagnostic logging helper
        def _log_resolution_attempt(
            stage: str,
            candidate_id_val: str | None,
            candidate_index_val: int | None,
            path_attempted: Path | None,
            found: bool,
        ) -> None:
            logger.debug(
                f"Next-check resolution {stage}",
                extra={
                    "run_id": context.run.run_id,
                    "candidate_id": candidate_id_val,
                    "candidate_index": candidate_index_val,
                    "cluster_label": cluster_label,
                    "request_plan_artifact_path": plan_artifact_path_from_request,
                    "path_attempted": str(path_attempted) if path_attempted else None,
                    "path_exists": path_attempted.exists() if path_attempted else None,
                    "found": found,
                    "stage": stage,
                },
            )

        # Track resolution details for comprehensive structured logging
        # Use health_root for artifact resolution since that's where artifacts live
        index_plan_artifact_path = plan.artifact_path if plan else None
        index_plan_artifact_exists = False
        resolved_index_plan_artifact_path: Path | None = None
        if index_plan_artifact_path:
            # Resolve relative to health_root, not runs_root
            resolved_index_plan_artifact_path = (health_root / index_plan_artifact_path).resolve()
            index_plan_artifact_exists = resolved_index_plan_artifact_path.exists()

        # Use the explicit plan artifact path from request if available, otherwise fall back to index
        request_plan_artifact_path_raw = plan_artifact_path_from_request
        resolved_request_plan_artifact_path: Path | None = None
        request_plan_artifact_exists = False
        request_plan_artifact_within_health_root = False

        if request_plan_artifact_path_raw and isinstance(request_plan_artifact_path_raw, str):
            # Validate and use the provided path - resolve relative to health_root
            resolved_request_plan_artifact_path = (health_root / request_plan_artifact_path_raw).resolve()
            request_plan_artifact_within_health_root = str(resolved_request_plan_artifact_path).startswith(str(health_root_resolved))
            request_plan_artifact_exists = resolved_request_plan_artifact_path.exists()

            # Emit INFO structured log before resolution begins
            emit_structured_log(
                component="next-check-execution",
                message="Next-check plan artifact resolution starting",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                severity="INFO",
                metadata={
                    "runs_root": str(runs_root),
                    "health_root": str(health_root_resolved),
                    "request_plan_artifact_path_raw": request_plan_artifact_path_raw,
                    "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                    "index_plan_artifact_path": index_plan_artifact_path,
                    "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                },
            )

            if request_plan_artifact_within_health_root and request_plan_artifact_exists:
                plan_path = resolved_request_plan_artifact_path
                _log_resolution_attempt("explicit_path_valid", candidate_id, candidate_index, plan_path, True)
            else:
                # Fall back to index path if the requested path is invalid
                emit_structured_log(
                    component="next-check-execution",
                    message="Next-check plan artifact path invalid, falling back to index",
                    run_label=context.run.run_label,
                    run_id=context.run.run_id,
                    severity="WARNING",
                    metadata={
                        "requested_path": request_plan_artifact_path_raw,
                        "resolved_request_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                        "request_path_valid": request_plan_artifact_exists,
                        "request_path_within_health_root": request_plan_artifact_within_health_root,
                        "fallback_index_path": plan.artifact_path,
                        "resolved_fallback_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                    },
                )
                plan_path = resolved_index_plan_artifact_path
                _log_resolution_attempt("explicit_path_invalid_fallback", candidate_id, candidate_index, plan_path, False)
        else:
            plan_path = resolved_index_plan_artifact_path

        # Track whether we found candidate in each resolution stage
        candidate_found_in_request_artifact = False
        candidate_found_in_index_artifact = False
        fallback_search_attempted = False
        fallback_matched_artifact_path: str | None = None

        # Validate plan_path is within health_root and exists
        if plan_path and str(plan_path).startswith(str(health_root_resolved)) and plan_path.exists():
            index_plan_artifact_exists = True
            try:
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                candidates = plan_data.get("candidates")
                raw_entry, resolved_index = self._resolve_plan_candidate(
                    candidates if isinstance(candidates, Sequence) else (),
                    candidate_id,
                    candidate_index,
                )
                if raw_entry is not None and resolved_index is not None:
                    candidate_entry = dict(raw_entry)
                    plan_path_used = plan_path
                    # Check if this was from explicit request or index
                    if request_plan_artifact_path_raw and request_plan_artifact_exists:
                        candidate_found_in_request_artifact = True
                    else:
                        candidate_found_in_index_artifact = True
            except Exception:
                # Plan artifact read failed, will try fallback
                pass

        # If not found in primary plan, search across all plan artifacts in health_root
        if candidate_entry is None or resolved_index is None:
            fallback_search_attempted = True
            # Use health_root for fallback search - this is the key fix!
            fallback_entry, fallback_index, fallback_path = self._find_candidate_in_all_plan_artifacts_from_health_root(
                health_root,
                context.run.run_id,
                candidate_id,
                candidate_index,
            )
            if fallback_entry is not None and fallback_index is not None:
                candidate_entry = fallback_entry
                resolved_index = fallback_index
                plan_path_used = fallback_path
                if fallback_path:
                    fallback_matched_artifact_path = str(fallback_path)

        if candidate_entry is None or resolved_index is None:
            # Emit structured log for failure case - provides comprehensive debug info
            emit_structured_log(
                component="next-check-execution",
                message="Next-check candidate resolution failed",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                severity="ERROR",
                metadata={
                    # Request context
                    "candidate_id": candidate_id,
                    "candidate_index_requested": candidate_index,
                    "candidate_index_resolved": None,
                    "cluster_label": cluster_label,
                    # Resolution path details
                    "request_plan_artifact_path_raw": request_plan_artifact_path_raw,
                    "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                    "request_plan_artifact_exists": request_plan_artifact_exists,
                    "request_plan_artifact_within_health_root": request_plan_artifact_within_health_root,
                    "index_plan_artifact_path": index_plan_artifact_path,
                    "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                    "index_plan_artifact_exists": index_plan_artifact_exists,
                    "runs_root": str(runs_root),
                    "health_root": str(health_root_resolved),
                    # Resolution outcome
                    "candidate_found_in_request_artifact": candidate_found_in_request_artifact,
                    "candidate_found_in_index_artifact": candidate_found_in_index_artifact,
                    "fallback_search_attempted": fallback_search_attempted,
                    "fallback_matched_artifact_path": fallback_matched_artifact_path,
                    "final_resolution_source": (
                        "explicit_request_path" if candidate_found_in_request_artifact
                        else "index_path" if candidate_found_in_index_artifact
                        else "fallback_search" if fallback_matched_artifact_path
                        else "none"
                    ),
                    # Error details
                    "error_summary": "Candidate not found after checking all resolution paths",
                },
            )
            # Log detailed debug info for operator to diagnose
            logger.warning(
                "Next-check candidate not found during execution",
                extra={
                    "run_id": context.run.run_id,
                    "candidate_id": candidate_id,
                    "candidate_index": candidate_index,
                    "plan_path_used": str(plan_path) if plan_path else None,
                    "plan_artifact_path_from_request": plan_artifact_path_from_request,
                    "fallback_search_attempted": True,
                },
            )
            # Provide clearer error message for operator
            if candidate_id and candidate_index is not None:
                self._send_json({"error": "Candidate not found. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            elif candidate_id:
                self._send_json({"error": "Candidate not found by ID. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            else:
                self._send_json({"error": "Candidate not found at specified index. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            return

        candidate = candidate_entry
        candidate_index = resolved_index

        # Use the fallback plan path if the primary wasn't found
        # Convert fallback relative path to absolute for validation
        if plan_path_used is not None and not plan_path_used.is_absolute():
            plan_path_used = self.runs_dir / plan_path_used
        effective_plan_path = plan_path_used if plan_path_used else plan_path
        if not effective_plan_path or not str(effective_plan_path).startswith(str(self.runs_dir.resolve())):
            self._send_json({"error": "Plan artifact path invalid"}, 400)
            return

        candidate_view = None
        plan_view = context.run.next_check_plan
        if plan_view:
            for entry in plan_view.candidates:
                if entry.candidate_index == candidate_index:
                    candidate_view = entry
                    break
        if candidate_view:
            enriched_candidate = dict(candidate)
            if candidate_view.approval_status:
                enriched_candidate["approvalStatus"] = candidate_view.approval_status
            if candidate_view.approval_artifact_path:
                enriched_candidate["approvalArtifactPath"] = candidate_view.approval_artifact_path
            if candidate_view.approval_timestamp:
                enriched_candidate["approvalTimestamp"] = candidate_view.approval_timestamp
            candidate = enriched_candidate
        if not isinstance(candidate, Mapping):
            self._send_json({"error": "Invalid candidate record"}, 500)
            return
        target_cluster = candidate.get("targetCluster")
        if not isinstance(target_cluster, str) or not target_cluster:
            self._send_json({"error": "Candidate target cluster missing"}, 400)
            return
        if target_cluster != request_cluster:
            self._send_json({"error": "Candidate target cluster mismatch"}, 400)
            return
        cluster_context = None
        for cluster in context.clusters:
            if cluster.label == target_cluster:
                cluster_context = cluster.context
                break
        if not cluster_context:
            self._send_json({"error": "Cluster context unavailable"}, 400)
            return
        try:
            artifact = execute_manual_next_check(
                health_root=self._health_root,
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                plan_artifact_path=effective_plan_path,
                candidate_index=candidate_index,
                candidate=candidate,
                target_context=cluster_context,
                target_cluster=target_cluster,
            )
        except ManualNextCheckError as exc:
            error_payload: dict[str, object] = {"error": str(exc)}
            blocking_reason = getattr(exc, "blocking_reason", None)
            if blocking_reason is not None:
                error_payload["blockingReason"] = blocking_reason.value
            self._send_json(error_payload, 400)
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            self._send_json({"error": f"Execution failed: {exc}"}, 500)
            return
        artifact_path = _relative_path(self.runs_dir, artifact.artifact_path)

        # Compute execution state from the artifact for client-side card state update
        # This ensures the UI shows truthful execution state even when pack refresh fails
        execution_state = _determine_execution_state_from_artifact(artifact)
        approval_status = str(candidate.get("approvalStatus") or candidate.get("approvalState") or "not-required")
        outcome_status = _derive_outcome_status(approval_status, execution_state)

        response_payload = {
            "status": artifact.status.value,
            "summary": artifact.summary,
            "artifactPath": artifact_path,
            "durationMs": artifact.duration_ms,
            "command": artifact.payload.get("command") if isinstance(artifact.payload, Mapping) else None,
            "targetCluster": target_cluster,
            "planCandidateIndex": candidate_index,
            "rawOutput": artifact.raw_output,
            "errorSummary": artifact.error_summary,
            "timedOut": artifact.timed_out,
            "stdoutTruncated": artifact.stdout_truncated,
            "stderrTruncated": artifact.stderr_truncated,
            "outputBytesCaptured": artifact.output_bytes_captured,
            # Card state fields - enable frontend to update card directly without waiting for refresh
            "executionState": execution_state,
            "outcomeStatus": outcome_status,
            "latestArtifactPath": artifact_path,
            "latestTimestamp": artifact.timestamp.isoformat() if artifact.timestamp else None,
        }

        # Refresh diagnostic pack latest mirrors after successful execution
        # This is a best-effort operation - don't fail the request if it doesn't work
        refresh_status: PackRefreshStatus = PackRefreshStatus.SUCCEEDED
        refresh_warning: str | None = None
        refresh_ok = _refresh_diagnostic_pack_latest(context.run.run_id, self.runs_dir)
        if not refresh_ok:
            # Add a non-fatal warning to the response if refresh failed
            refresh_status = PackRefreshStatus.FAILED
            refresh_warning = "Execution artifact saved. Pack refresh failed; queue/review state may be stale until next refresh."
            response_payload["warning"] = refresh_warning

        # Persist the pack refresh outcome into the execution artifact for durable visibility
        if artifact.artifact_path:
            artifact_path_obj = Path(artifact.artifact_path)
            if artifact_path_obj.exists():
                try:
                    # Read the existing artifact
                    artifact_data = json.loads(artifact_path_obj.read_text(encoding="utf-8"))
                    # Update with pack refresh outcome
                    artifact_data["pack_refresh_status"] = refresh_status.value
                    artifact_data["pack_refresh_warning"] = refresh_warning
                    # Write back the updated artifact
                    artifact_path_obj.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
                    # Also update the in-memory artifact for the response
                    response_payload["packRefreshStatus"] = refresh_status.value
                    response_payload["packRefreshWarning"] = refresh_warning
                except Exception as exc:
                    # Log but don't fail - refresh outcome is non-fatal
                    logger.warning(
                        "Failed to persist pack refresh status to artifact",
                        extra={"artifact": str(artifact_path_obj), "error": str(exc)},
                    )

        # Emit comprehensive structured log for next-check execution resolution
        # This captures all resolution stages for debugging and observability
        emit_structured_log(
            component="next-check-execution",
            message="Next-check candidate resolved and executed",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            severity="INFO",
            metadata={
                # Request context
                "candidate_id": candidate_id,
                "candidate_index_requested": candidate_index,
                "candidate_index_resolved": resolved_index,
                "cluster_label": cluster_label,
                # Resolution path details
                "explicit_request_path_provided": request_plan_artifact_path_raw is not None,
                "explicit_request_path_raw": request_plan_artifact_path_raw,
                "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                "explicit_request_path_exists": request_plan_artifact_exists,
                "explicit_request_path_validated": request_plan_artifact_within_health_root and request_plan_artifact_exists if request_plan_artifact_path_raw else None,
                "index_plan_artifact_path": index_plan_artifact_path,
                "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                "index_plan_artifact_exists": index_plan_artifact_exists,
                "runs_root": str(runs_root),
                "health_root": str(health_root_resolved),
                # Resolution outcome
                "candidate_found_in_request_artifact": candidate_found_in_request_artifact,
                "candidate_found_in_index_artifact": candidate_found_in_index_artifact,
                "fallback_search_attempted": fallback_search_attempted,
                "fallback_matched_artifact_path": fallback_matched_artifact_path,
                "final_source": (
                    "explicit_request_path" if candidate_found_in_request_artifact
                    else "index_path" if candidate_found_in_index_artifact
                    else "fallback_search" if fallback_matched_artifact_path
                    else "unknown"
                ),
                # Execution result
                "execution_status": artifact.status.value,
                "execution_duration_ms": artifact.duration_ms,
                "execution_timed_out": artifact.timed_out,
                "refresh_status": refresh_status.value,
            },
        )

        # Persist the execution history entry to ui-index.json so load_ui_index() picks it up
        # This is the authoritative source for the UI's read model.
        ui_index_path = self.runs_dir / "health" / "ui-index.json"
        try:
            index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
            run_entry = index_data.get("run") or {}
            history_list: list[dict[str, object]] = list(run_entry.get("next_check_execution_history") or [])
            # Append the execution history entry (same format as _build_execution_history produces)
            # Use target_cluster (the validated cluster from candidate) and candidate (the resolved candidate dict)
            history_entry: dict[str, object] = {
                "timestamp": artifact.timestamp.isoformat() if hasattr(artifact, "timestamp") and artifact.timestamp else datetime.now(UTC).isoformat(),
                "clusterLabel": target_cluster if target_cluster else cluster_label,
                "candidateDescription": candidate.get("description") if candidate else None,
                "commandFamily": candidate.get("suggestedCommandFamily") if candidate else None,
                "status": artifact.status.value,
                "durationMs": artifact.duration_ms,
                "artifactPath": artifact_path or str(artifact_path),
                "timedOut": artifact.timed_out or False,
                "stdoutTruncated": artifact.stdout_truncated or False,
                "stderrTruncated": artifact.stderr_truncated or False,
            }
            history_list.append(history_entry)
            run_entry["next_check_execution_history"] = history_list
            index_data["run"] = run_entry
            ui_index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug(
                "Persisted execution history to ui-index.json",
                extra={"ui_index": str(ui_index_path), "run_id": context.run.run_id, "history_count": len(history_list)},
            )
        except Exception as exc:
            # Fallback: just touch the file to invalidate cache (history won't appear until next health loop)
            logger.warning(
                "Failed to persist execution history to ui-index.json, falling back to touch-only invalidation",
                extra={"ui_index": str(ui_index_path), "error": str(exc)},
            )
            try:
                ui_index_path.touch()
            except Exception:
                pass

        self._send_json(response_payload)

    def _handle_deterministic_promotion(self) -> None:
        context = self._load_context()
        if context is None:
            return
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
        cluster_label = payload.get("clusterLabel")
        if not isinstance(cluster_label, str) or not cluster_label:
            self._send_json({"error": "clusterLabel is required"}, 400)
            return
        description = payload.get("description")
        if not isinstance(description, str) or not description.strip():
            self._send_json({"error": "description is required"}, 400)
            return
        matching_cluster = next(
            (cluster for cluster in context.clusters if cluster.label == cluster_label),
            None,
        )
        if matching_cluster is None:
            self._send_json({"error": "Cluster label is not part of this run."}, 400)
            return
        workstream = payload.get("workstream") if isinstance(payload.get("workstream"), str) else None
        urgency = payload.get("urgency") if isinstance(payload.get("urgency"), str) else None
        why_now = payload.get("whyNow") if isinstance(payload.get("whyNow"), str) else None
        top_problem = payload.get("topProblem") if isinstance(payload.get("topProblem"), str) else None
        method = payload.get("method") if isinstance(payload.get("method"), str) else None
        raw_evidence = payload.get("evidenceNeeded")
        evidence = [str(item) for item in raw_evidence or [] if isinstance(item, str)]
        priority_score = payload.get("priorityScore")
        priority_value: int | None = None
        if isinstance(priority_score, (int, float)):
            priority_value = int(priority_score)
        elif isinstance(priority_score, str):
            try:
                priority_value = int(priority_score)
            except ValueError:
                priority_value = None
        target_context = payload.get("context") if isinstance(payload.get("context"), str) else None
        if not target_context and matching_cluster:
            target_context = matching_cluster.context
        summary = {
            "description": description.strip(),
            "method": method,
            "evidenceNeeded": evidence,
            "workstream": workstream,
            "urgency": urgency,
            "whyNow": why_now,
            "topProblem": top_problem,
            "priorityScore": priority_value,
        }
        promotions = collect_promoted_queue_entries(self._health_root, context.run.run_id)
        candidate_id = build_promoted_candidate_id(
            description, cluster_label, context.run.run_id
        )
        existing_ids = {entry.get("candidateId") for entry in promotions if entry.get("candidateId")}
        if candidate_id in existing_ids:
            self._send_json(
                {"error": "A similar deterministic check has already been promoted."},
                409,
            )
            return
        try:
            artifact, _ = write_deterministic_next_check_promotion(
                runs_dir=self.runs_dir,
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                cluster_label=cluster_label,
                target_context=target_context,
                summary=summary,
            )
        except Exception as exc:
            self._send_json({"error": f"Unable to persist promotion: {exc}"}, 500)
            return
        response = {
            "status": "success",
            "summary": "Deterministic next check promoted to the queue.",
            "artifactPath": artifact.artifact_path,
            "candidateId": candidate_id,
        }
        self._send_json(response)

    def _handle_next_check_approval(self) -> None:
        context = self._load_context()
        if context is None:
            return
        plan = context.run.next_check_plan
        if not plan or not plan.artifact_path:
            self._send_json({"error": "Next-check plan unavailable"}, 400)
            return
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
        candidate_index_raw = payload.get("candidateIndex")
        candidate_index = candidate_index_raw if isinstance(candidate_index_raw, int) else None
        if candidate_index_raw is not None and candidate_index is None:
            self._send_json({"error": "candidateIndex must be an integer"}, 400)
            return
        request_cluster = payload.get("clusterLabel")
        if not isinstance(request_cluster, str) or not request_cluster:
            self._send_json({"error": "clusterLabel is required"}, 400)
            return
        candidate_id_raw = payload.get("candidateId")
        candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) and candidate_id_raw else None
        if candidate_id is None and candidate_index is None:
            self._send_json({"error": "candidateId or candidateIndex is required"}, 400)
            return

        # Try the primary plan artifact first
        candidate_entry: dict[str, object] | None = None
        resolved_index: int | None = None

        plan_path = (self._health_root / plan.artifact_path).resolve()
        if str(plan_path).startswith(str(self.runs_dir.resolve())) and plan_path.exists():
            try:
                plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
                candidates = plan_data.get("candidates")
                raw_entry, resolved_index = self._resolve_plan_candidate(
                    candidates if isinstance(candidates, Sequence) else (),
                    candidate_id,
                    candidate_index,
                )
                if raw_entry is not None and resolved_index is not None:
                    candidate_entry = dict(raw_entry)
            except Exception:
                # Plan artifact read failed, will try fallback
                pass

        # If not found in primary plan, search across all plan artifacts
        if candidate_entry is None or resolved_index is None:
            fallback_entry, fallback_index, _ = self._find_candidate_in_all_plan_artifacts(
                context.run.run_id,
                candidate_id,
                candidate_index,
            )
            if fallback_entry is not None and fallback_index is not None:
                candidate_entry = fallback_entry
                resolved_index = fallback_index

        if candidate_entry is None or resolved_index is None:
            # Provide clearer error message for operator
            if candidate_id and candidate_index is not None:
                self._send_json({"error": "Candidate not found. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            elif candidate_id:
                self._send_json({"error": "Candidate not found by ID. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            else:
                self._send_json({"error": "Candidate not found at specified index. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
            return
        candidate = candidate_entry
        raw_candidate_id_value = candidate.get("candidateId")
        candidate_id_value = (
            raw_candidate_id_value if isinstance(raw_candidate_id_value, str) else None
        )
        candidate_index = resolved_index
        target_cluster = candidate.get("targetCluster")
        if target_cluster and target_cluster != request_cluster:
            self._send_json({"error": "Candidate target cluster mismatch"}, 400)
            return
        requires_approval = bool(candidate.get("requiresOperatorApproval"))
        if not requires_approval:
            log_next_check_approval_event(
                severity="WARNING",
                message="Approval rejected because candidate does not require approval",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_description=str(candidate.get("description") or ""),
                target_cluster=request_cluster,
                event="approval-rejected",
            )
            self._send_json({"error": "Candidate does not require approval"}, 400)
            return
        if candidate.get("duplicateOfExistingEvidence"):
            log_next_check_approval_event(
                severity="WARNING",
                message="Approval rejected because candidate duplicates existing evidence",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_description=str(candidate.get("description") or ""),
                target_cluster=request_cluster,
                event="approval-rejected",
            )
            self._send_json({"error": "Candidate duplicates deterministic evidence"}, 400)
            return
        if target_cluster is None and request_cluster and request_cluster not in {cluster.label for cluster in context.clusters}:
            # allow request even if plan candidate lacks explicit target, as long as cluster exists
            pass
        plan_candidate_description = str(candidate.get("description") or "")
        log_next_check_approval_event(
            severity="INFO",
            message="Operator requested approval for next-check candidate",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            plan_artifact_path=plan.artifact_path,
            candidate_index=candidate_index,
            candidate_id=candidate_id_value,
            candidate_description=plan_candidate_description,
            target_cluster=request_cluster,
            event="approval-requested",
        )
        try:
            artifact = record_next_check_approval(
                runs_dir=self.runs_dir,
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_id=candidate_id_value,
                candidate_description=plan_candidate_description,
                target_cluster=request_cluster,
            )
        except Exception as exc:  # pragma: no cover - fail safe
            self._send_json({"error": f"Approval failed: {exc}"}, 500)
            return
        artifact_path = _relative_path(self.runs_dir, artifact.artifact_path)
        response = {
            "status": artifact.status.value,
            "summary": artifact.summary,
            "artifactPath": artifact_path,
            "durationMs": artifact.duration_ms,
            "candidateIndex": candidate_index,
            "approvalTimestamp": artifact.timestamp.isoformat(),
        }
        self._send_json(response)

    def _handle_usefulness_feedback(self) -> None:
        """Handle operator feedback on next-check execution usefulness.

        Accepts artifactPath, usefulnessClass (useful|partial|noisy|empty),
        and optional usefulnessSummary, then updates the execution artifact in-place.
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

        # Validate required fields
        artifact_path_rel = payload.get("artifactPath")
        if not isinstance(artifact_path_rel, str) or not artifact_path_rel:
            self._send_json({"error": "artifactPath is required"}, 400)
            return

        usefulness_class_raw = payload.get("usefulnessClass")
        if not isinstance(usefulness_class_raw, str) or not usefulness_class_raw:
            self._send_json({"error": "usefulnessClass is required"}, 400)
            return

        # Validate usefulness class - only allow the 4 contract values
        try:
            usefulness_class = UsefulnessClass(usefulness_class_raw)
        except ValueError:
            self._send_json(
                {
                    "error": "Invalid usefulnessClass. Must be one of: useful, partial, noisy, empty"
                },
                400,
            )
            return

        # Optional summary
        usefulness_summary = payload.get("usefulnessSummary")
        if usefulness_summary is not None and not isinstance(usefulness_summary, str):
            self._send_json({"error": "usefulnessSummary must be a string"}, 400)
            return

        # Resolve artifact path securely
        try:
            artifact_path = (self.runs_dir / artifact_path_rel).resolve()
        except Exception:
            self._send_json({"error": "Invalid artifact path"}, 400)
            return

        # Verify path is within runs_dir
        if not str(artifact_path).startswith(str(self.runs_dir.resolve())):
            self._send_json({"error": "Artifact path must be within runs directory"}, 400)
            return

        if not artifact_path.exists():
            self._send_json({"error": "Artifact not found"}, 404)
            return

        # Read, update, and write the artifact
        try:
            artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._send_json({"error": f"Unable to read artifact: {exc}"}, 500)
            return

        # Update usefulness fields
        artifact_data["usefulness_class"] = usefulness_class.value
        if usefulness_summary:
            artifact_data["usefulness_summary"] = usefulness_summary
        elif "usefulness_summary" in artifact_data:
            # Clear if empty string provided
            del artifact_data["usefulness_summary"]

        try:
            artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
        except Exception as exc:
            self._send_json({"error": f"Unable to persist feedback: {exc}"}, 500)
            return

        logger.info(
            "Operator recorded usefulness feedback",
            extra={
                "artifact": str(artifact_path),
                "usefulness_class": usefulness_class.value,
                "usefulness_summary": usefulness_summary,
            },
        )

        self._send_json({
            "status": "success",
            "summary": "Usefulness feedback recorded",
            "usefulnessClass": usefulness_class.value,
            "usefulnessSummary": usefulness_summary,
        })

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

        # If not dry run, refresh diagnostic pack
        if not dry_run and result.executed_count > 0:
            _refresh_diagnostic_pack_latest(run_id, self.runs_dir)

        self._send_json(response)

    def _serve_static(self, route: str) -> None:
        target = route or "/"
        if target.endswith("/"):
            target += "index.html"
        candidate = (self.static_dir / target.lstrip("/")).resolve()
        static_root = self.static_dir.resolve()
        if not str(candidate).startswith(str(static_root)) or not candidate.exists():
            candidate = static_root / "index.html"
            if not candidate.exists():
                self._send_text(404, "Static assets unavailable")
                return
        self._send_file(candidate)

    def _serve_artifact(self, query: str) -> None:
        params = parse_qs(query)
        paths = params.get("path")
        if not paths:
            self._send_text(400, "Artifact path required")
            return
        requested = Path(paths[0])
        requested_relative = str(requested)
        try:
            artifact_path = (self.runs_dir / requested).resolve()
        except Exception:  # pragma: no cover - defensive guard
            self._log_artifact_request(requested_relative, None, None, "invalid-path", 400)
            self._send_text(400, "Invalid artifact path")
            return
        root_resolved = self.runs_dir.resolve()
        normalized_path = str(artifact_path)
        within_allowed_root = normalized_path.startswith(str(root_resolved))
        if not within_allowed_root:
            self._log_artifact_request(
                requested_relative, normalized_path, str(root_resolved),
                "path-escape-attempt", 400
            )
            self._send_text(400, "Invalid artifact path")
            return
        exists = artifact_path.exists()
        if not exists:
            self._log_artifact_request(
                requested_relative, normalized_path, str(root_resolved),
                "not-found", 404
            )
            self._send_text(404, "Artifact not found")
            return
        status = "success"
        if artifact_path.suffix.lower() == ".zip":
            try:
                artifact_bytes = artifact_path.read_bytes()
            except OSError as exc:
                self._log_artifact_request(
                    requested_relative, normalized_path, str(root_resolved),
                    "read-error", 500
                )
                self._send_text(500, f"Unable to read artifact: {exc}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(artifact_bytes)))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"{artifact_path.name}\"",
            )
            self.end_headers()
            self.wfile.write(artifact_bytes)
            self._log_artifact_request(
                requested_relative, normalized_path, str(root_resolved),
                status, 200
            )
            return
        try:
            payload = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._log_artifact_request(
                requested_relative, normalized_path, str(root_resolved),
                "read-error", 500
            )
            self._send_text(500, f"Unable to read artifact: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))
        self._log_artifact_request(
            requested_relative, normalized_path, str(root_resolved),
            status, 200
        )

    def _log_artifact_request(
        self,
        requested_relative: str,
        normalized_absolute: str | None,
        runs_root: str | None,
        result: str,
        status_code: int,
    ) -> None:
        """Log structured information about artifact download requests."""
        emit_structured_log(
            component="artifact-download",
            message="Artifact download request",
            severity="INFO" if status_code < 400 else "WARNING",
            run_label="",
            run_id="",
            metadata={
                "requested_relative_path": requested_relative,
                "normalized_absolute_path": normalized_absolute,
                "runs_root": runs_root,
                "health_root": str(Path(runs_root) / "health") if runs_root else None,
                "exists": normalized_absolute and Path(normalized_absolute).exists() if normalized_absolute else False,
                "within_allowed_root": normalized_absolute and runs_root and normalized_absolute.startswith(runs_root) if (normalized_absolute and runs_root) else False,
                "result": result,
                "status_code": status_code,
            },
        )

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
        import json
        from datetime import UTC, datetime

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

        # Find next-check plan artifact
        next_check_plan = _find_next_check_plan(external_analysis_dir, run_id)

        # Build next_check_queue from plan if exists
        next_check_queue = _build_queue_from_plan(next_check_plan)

        # Build next_check_execution_history
        execution_history = _build_execution_history(external_analysis_dir, run_id)

        # Build llm_stats from external-analysis artifacts for this run
        llm_stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

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
            "review_enrichment_status": None,
            "provider_execution": None,
            "next_check_plan": next_check_plan,
            "next_check_queue": next_check_queue,
            "next_check_queue_explanation": None,
            "next_check_execution_history": execution_history,
            "deterministic_next_checks": None,
            "planner_availability": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
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


def _build_clusters_from_review(
    run_id: str, review_data: dict[str, object], runs_dir: Path
) -> list[dict[str, object]]:
    """Build clusters list from review artifact's selected_drilldowns."""
    clusters: list[dict[str, object]] = []
    selected_drilldowns = review_data.get("selected_drilldowns", [])

    if not isinstance(selected_drilldowns, list):
        return clusters

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        # Check if drilldown artifact exists
        drilldowns_dir = runs_dir / "health" / "drilldowns"
        drilldown_artifact = None
        drilldown_timestamp = None
        if drilldowns_dir.exists():
            for df in drilldowns_dir.glob(f"{run_id}-{label}-*.json"):
                try:
                    df_data = json.loads(df.read_text(encoding="utf-8"))
                    drilldown_artifact = str(df.relative_to(runs_dir))
                    drilldown_timestamp = df_data.get("timestamp")
                    break
                except Exception:
                    continue

        clusters.append({
            "label": label,
            "context": context,
            "cluster_class": "primary",
            "cluster_role": "worker",
            "baseline_cohort": "fleet",
            "node_count": drilldown.get("node_count", 0),
            "control_plane_version": "unknown",
            "health_rating": "degraded",  # Selected drilldowns indicate issues
            "warnings": drilldown.get("warning_event_count", 0),
            "non_running_pods": drilldown.get("non_running_pod_count", 0),
            "baseline_policy_path": "",
            "missing_evidence": drilldown.get("missing_evidence", []),
            "latest_run_timestamp": review_data.get("timestamp", ""),
            "top_trigger_reason": drilldown.get("reasons", [None])[0] if drilldown.get("reasons") else None,
            "drilldown_available": drilldown_artifact is not None,
            "drilldown_timestamp": drilldown_timestamp,
            "artifact_paths": {
                "snapshot": None,
                "assessment": None,
                "drilldown": drilldown_artifact,
            },
        })

    return clusters


def _count_run_artifacts(artifacts_dir: Path, run_id: str) -> int:
    """Count artifacts belonging to a specific run in a directory."""
    if not artifacts_dir.exists():
        return 0
    count = 0
    for artifact_file in artifacts_dir.glob(f"{run_id}-*.json"):
        count += 1
    return count


def _load_proposals_for_run(
    proposals_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load proposals for a specific run and return proposals data + count."""
    proposals: list[dict[str, object]] = []

    if not proposals_dir.exists():
        return proposals, 0

    for proposal_file in sorted(proposals_dir.glob(f"{run_id}-*.json")):
        try:
            proposal_data = json.loads(proposal_file.read_text(encoding="utf-8"))
            if isinstance(proposal_data, dict):
                proposals.append(proposal_data)
        except Exception:
            continue

    return proposals, len(proposals)


def _scan_external_analysis(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object]:
    """Scan external-analysis directory for artifacts belonging to a run."""
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}

    if not external_analysis_dir.exists():
        return {"count": 0, "status_counts": [], "artifacts": entries}

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            status = str(artifact_data.get("status", "unknown")).lower()
            counts[status] = counts.get(status, 0) + 1

            entries.append({
                "tool_name": artifact_data.get("tool_name", "unknown"),
                "cluster_label": artifact_data.get("cluster_label"),
                "run_id": artifact_data.get("run_id"),
                "run_label": artifact_data.get("run_label"),
                "status": status,
                "summary": artifact_data.get("summary"),
                "findings": artifact_data.get("findings", []),
                "suggested_next_checks": artifact_data.get("suggested_next_checks", []),
                "timestamp": artifact_data.get("timestamp"),
                "artifact_path": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "duration_ms": artifact_data.get("duration_ms"),
                "provider": artifact_data.get("provider"),
                "purpose": artifact_data.get("purpose"),
                "payload": artifact_data.get("payload"),
                "error_summary": artifact_data.get("error_summary"),
                "skip_reason": artifact_data.get("skip_reason"),
            })
        except Exception:
            continue

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"count": len(entries), "status_counts": status_counts, "artifacts": entries}


def _load_notifications_for_run(
    notifications_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load notifications for a specific run."""
    notifications: list[dict[str, object]] = []

    if not notifications_dir.exists():
        return notifications, 0

    for notif_file in sorted(notifications_dir.glob("*.json")):
        try:
            notif_data = json.loads(notif_file.read_text(encoding="utf-8"))
            if not isinstance(notif_data, dict):
                continue

            # Filter by run_id if present
            notif_run_id = notif_data.get("run_id")
            if notif_run_id and notif_run_id != run_id:
                continue

            notifications.append({
                "kind": notif_data.get("kind", "info"),
                "summary": notif_data.get("summary", ""),
                "timestamp": notif_data.get("timestamp", ""),
                "run_id": notif_run_id,
                "cluster_label": notif_data.get("cluster_label"),
                "context": notif_data.get("context"),
                "details": notif_data.get("details", []),
                "artifact_path": str(notif_file.relative_to(notifications_dir.parent)),
            })
        except Exception:
            continue

    return notifications, len(notifications)


def _build_drilldown_availability_from_review(
    review_data: dict[str, object], drilldowns_dir: Path, run_id: str
) -> dict[str, object]:
    """Build drilldown availability from review clusters + drilldown artifacts."""
    selected_drilldowns = review_data.get("selected_drilldowns", [])
    if not isinstance(selected_drilldowns, list):
        selected_drilldowns = []

    total = len(selected_drilldowns)
    available = 0
    missing_labels: list[str] = []
    coverage: list[dict[str, object]] = []

    # Check which drilldowns have artifacts
    existing_drilldowns = set()
    if drilldowns_dir.exists():
        for df in drilldowns_dir.glob(f"{run_id}-*.json"):
            # Extract cluster label from filename pattern
            df_name = df.stem
            # Pattern: {run_id}-{cluster_label}-...
            if df_name.startswith(run_id + "-"):
                cluster_label = df_name[len(run_id) + 1:].split("-")[0]
                existing_drilldowns.add(cluster_label)

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        if label in existing_drilldowns:
            available += 1
            timestamp = review_data.get("timestamp")  # Use review timestamp as approximation
            available_flag = True
            # Find the actual artifact path
            artifact_path = None
            for df in drilldowns_dir.glob(f"{run_id}-{label}-*.json"):
                artifact_path = str(df.relative_to(drilldowns_dir.parent))
                break
        else:
            timestamp = None
            artifact_path = None
            missing_labels.append(label)
            available_flag = False

        coverage.append({
            "label": label,
            "context": context,
            "available": available_flag,
            "timestamp": timestamp,
            "artifact_path": artifact_path,
        })

    return {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "missing_clusters": missing_labels,
        "coverage": coverage,
    }


def _find_review_enrichment(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object] | None:
    """Find and parse review enrichment artifact for a run."""
    if not external_analysis_dir.exists():
        return None

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-review-enrichment*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "review-enrichment":
                continue

            payload = artifact_data.get("payload", {})

            def _list_from(key: str) -> list[str]:
                value = payload.get(key)
                if isinstance(value, list):
                    return [str(item) for item in value]
                return []

            return {
                "status": artifact_data.get("status", "unknown"),
                "provider": artifact_data.get("provider"),
                "timestamp": artifact_data.get("timestamp"),
                "summary": artifact_data.get("summary"),
                "triageOrder": _list_from("triageOrder"),
                "topConcerns": _list_from("topConcerns"),
                "evidenceGaps": _list_from("evidenceGaps"),
                "nextChecks": _list_from("nextChecks"),
                "focusNotes": _list_from("focusNotes"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "errorSummary": artifact_data.get("error_summary"),
                "skipReason": artifact_data.get("skip_reason"),
            }
        except Exception:
            continue

    return None


def _find_next_check_plan(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object] | None:
    """Find and parse next-check plan artifact for a run."""
    if not external_analysis_dir.exists():
        return None

    # Look for plan artifacts - they have purpose = "next-check-planning"
    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "next-check-planning":
                continue

            payload = artifact_data.get("payload", {})
            candidates = payload.get("candidates", [])

            return {
                "status": artifact_data.get("status", "unknown"),
                "summary": payload.get("summary"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "reviewPath": payload.get("reviewPath"),
                "enrichmentArtifactPath": payload.get("enrichmentArtifactPath"),
                "candidateCount": len(candidates) if isinstance(candidates, list) else 0,
                "candidates": candidates,
                "orphanedApprovals": [],
                "outcomeCounts": [],
                "orphanedApprovalCount": 0,
            }
        except Exception:
            continue

    return None


def _build_queue_from_plan(plan: dict[str, object] | None) -> list[dict[str, object]]:
    """Build next-check queue from plan artifact."""
    if not plan:
        return []

    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list):
        return []

    queue: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue

        requires_approval = bool(candidate.get("requiresOperatorApproval"))
        safe_to_automate = bool(candidate.get("safeToAutomate"))

        # Determine queue status
        queue_status = "safe-ready"
        if requires_approval:
            approval_state = str(candidate.get("approvalState", "")).lower()
            if approval_state == "approved":
                queue_status = "approved-ready"
            else:
                queue_status = "approval-needed"
        elif not safe_to_automate:
            queue_status = "duplicate-or-stale"

        queue.append({
            "candidateId": candidate.get("candidateId"),
            "candidateIndex": candidate.get("candidateIndex", idx),
            "description": candidate.get("description", ""),
            "targetCluster": candidate.get("targetCluster"),
            "priorityLabel": candidate.get("priorityLabel"),
            "suggestedCommandFamily": candidate.get("suggestedCommandFamily"),
            "safeToAutomate": safe_to_automate,
            "requiresOperatorApproval": requires_approval,
            "approvalState": candidate.get("approvalState"),
            "executionState": candidate.get("executionState", "unexecuted"),
            "outcomeStatus": candidate.get("outcomeStatus"),
            "latestArtifactPath": candidate.get("latestArtifactPath"),
            "queueStatus": queue_status,
            "sourceReason": candidate.get("sourceReason"),
            "expectedSignal": candidate.get("expectedSignal"),
            "normalizationReason": candidate.get("normalizationReason"),
            "safetyReason": candidate.get("safetyReason"),
            "approvalReason": candidate.get("approvalReason"),
            "duplicateReason": candidate.get("duplicateReason"),
            "blockingReason": candidate.get("blockingReason"),
            "targetContext": None,
            "commandPreview": None,
            "planArtifactPath": plan.get("artifactPath"),
        })

    return queue


def _get_field_with_fallback(data: dict[str, object], *keys: str) -> object | None:
    """Get a value from dict with fallback keys, preserving false/0 values.
    
    Checks each key in order and returns the first one that exists (even if falsy).
    Returns None if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return None


def _get_field_with_default(data: dict[str, object], default: object, *keys: str) -> object:
    """Get a value from dict with fallback keys, returning default if not found.
    
    Checks each key in order and returns the first one that exists (even if falsy).
    Returns the provided default value if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return default


def _build_execution_history(
    external_analysis_dir: Path, run_id: str
) -> list[dict[str, object]]:
    """Build next-check execution history from execution artifacts.
    
    Uses prefix-based matching to handle any artifact naming pattern,
    matching any file starting with run_id and ending with '-next-check-execution'.
    This mirrors the approach used in build_runs_list() for consistency.
    """
    history: list[dict[str, object]] = []

    if not external_analysis_dir.exists():
        return history

    # Pre-sort files by length (longest first) to handle prefixed run_ids correctly
    # e.g., "run-2024-01-15" should match before "run-2024"
    all_files = sorted(external_analysis_dir.glob("*-next-check-execution*.json"), key=lambda p: len(p.name), reverse=True)

    for artifact_file in all_files:
        filename = artifact_file.stem  # filename without extension
        # Verify run_id boundary: must be followed by hyphen (for child runs) or end of string
        # Without this check, "run-2024" would match "run-20240-execution.json"
        if not filename.startswith(run_id):
            continue
        if len(filename) > len(run_id) and filename[len(run_id)] != "-":
            continue
        
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "next-check-execution":
                continue

            # Verify run_id matches in artifact data as additional safety check
            # Only enforce if artifact has a run_id field (backward compatibility)
            artifact_run_id = artifact_data.get("run_id")
            if artifact_run_id is not None and artifact_run_id != run_id:
                continue

            payload = artifact_data.get("payload", {})

            history.append({
                "timestamp": artifact_data.get("timestamp"),
                "clusterLabel": _get_field_with_fallback(payload, "clusterLabel", "cluster_label"),
                "candidateDescription": _get_field_with_fallback(payload, "candidateDescription", "candidate_description"),
                "commandFamily": _get_field_with_fallback(payload, "commandFamily", "command_family"),
                "status": artifact_data.get("status", "unknown"),
                "durationMs": _get_field_with_default(artifact_data, 0, "duration_ms", "durationMs"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "timedOut": _get_field_with_default(artifact_data, False, "timed_out", "timedOut"),
                "stdoutTruncated": _get_field_with_default(artifact_data, False, "stdout_truncated", "stdoutTruncated"),
                "stderrTruncated": _get_field_with_default(artifact_data, False, "stderr_truncated", "stderrTruncated"),
                "outputBytesCaptured": _get_field_with_default(artifact_data, 0, "output_bytes_captured", "outputBytesCaptured"),
            })
        except Exception:
            continue

    # Sort by timestamp descending (most recent first) using ISO timestamp comparison
    history.sort(key=lambda x: cast(str, x.get("timestamp") or ""), reverse=True)

    return history[:5]  # Limit to 5 most recent


def _build_llm_stats_for_run(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object]:
    """Build LLM stats from external-analysis artifacts for a specific run."""
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    latest_timestamp: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}

    if not external_analysis_dir.exists():
        return {
            "totalCalls": 0,
            "successfulCalls": 0,
            "failedCalls": 0,
            "lastCallTimestamp": None,
            "p50LatencyMs": None,
            "p95LatencyMs": None,
            "p99LatencyMs": None,
            "providerBreakdown": [],
            "scope": "current_run",
        }

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            status = str(artifact_data.get("status", "")).lower()
            if status not in ("success", "failed"):
                continue

            total_calls += 1
            if status == "success":
                successful_calls += 1
            if status == "failed":
                failed_calls += 1

            # Track latest timestamp
            timestamp = artifact_data.get("timestamp")
            if timestamp:
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp

            # Track provider breakdown
            provider = str(artifact_data.get("tool_name") or artifact_data.get("provider") or "unknown")
            if provider not in provider_counts:
                provider_counts[provider] = {"calls": 0, "failedCalls": 0}
            provider_counts[provider]["calls"] += 1
            if status == "failed":
                provider_counts[provider]["failedCalls"] += 1

        except Exception:
            continue

    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]

    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp,
        "p50LatencyMs": None,
        "p95LatencyMs": None,
        "p99LatencyMs": None,
        "providerBreakdown": provider_breakdown,
        "scope": "current_run",
    }


def _build_proposal_status_summary(proposals: list[dict[str, object]]) -> dict[str, object]:
    """Build proposal status summary from proposals list."""
    counts: dict[str, int] = {}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        status = str(proposal.get("status", "unknown")).lower()
        counts[status] = counts.get(status, 0) + 1

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"status_counts": status_counts}


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
