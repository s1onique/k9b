"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,  # noqa: E402, F401 (re-export for backward compatibility)
)
from pathlib import Path

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
from .server_parse_utils import (  # noqa: E402, F401
    parse_limit,
    parse_page,
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
    start_ui_server_impl,
)
from .server_shared import (  # noqa: E402, F401
    _compute_health_root,
    _normalize_runs_dir,
    _validate_runs_dir,
)
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
        # Inject emit_structured_log from module namespace to preserve test mock compatibility
        return load_context_for_run(self, run_id, emit_fn=emit_structured_log)

    def _parse_limit(self, value: str | None) -> int | None:
        """Parse a limit parameter from query string (delegates to server_parse_utils)."""
        return parse_limit(value)

    def _parse_page(self, value: str | None) -> int:
        """Parse a page parameter from query string (delegates to server_parse_utils)."""
        return parse_page(value)

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
