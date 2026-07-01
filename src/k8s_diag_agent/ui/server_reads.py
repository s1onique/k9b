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
Runs-list payload moved to server_runs_list_payload.py. Selected-run detail handler
moved to server_run_detail_reads.py. Re-exported here for backward compatibility
with existing callers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

# Re-export from extraction modules for backward compatibility
from .server_artifact_reads import (
    _handle_debug_routes,
    _has_batch_eligibility_index,
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


def handle_runtime_status_route(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/runtime-status route.

    Args:
        handler: The HTTP request handler instance
    """
    from .api_runtime_status import handle_runtime_status_route as _handle

    _handle(handler)


def handle_health_details_route(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/health/details route.

    This endpoint provides self-diagnosis when /api/health returns 500.

    Args:
        handler: The HTTP request handler instance
    """
    from .api_health_details import handle_health_details as _handle

    _handle(handler)


def handle_api(handler: HealthUIRequestHandler, route: str, query: str) -> None:
    """Handle API GET requests (read-only endpoints).

    This is the top-level GET dispatcher extracted from server.py's _handle_api.
    All cache/single-flight logic is preserved inline here since it needs access
    to handler state.

    Routes that need context loading (fleet, proposals, cluster-detail) are handled
    specially. All other routes are dispatched through the registry dispatcher.

    Args:
        handler: The HealthUIRequestHandler instance
        route: The request path without query string
        query: The query string
    """
    # Import dispatcher here to avoid circular imports at module level
    from .api_dispatch import dispatch_api_operation

    # Try dispatching through the registry first
    if dispatch_api_operation(handler, "GET", route, query):
        return

    # Routes that need context loading - handled specially below
    # These cannot be dispatched through the registry because they need
    # the UI context to be loaded first
    context_routes = {
        "/api/fleet",
        "/api/proposals",
        "/api/cluster-detail",
        "/api/run",
    }

    if route in context_routes:
        # Import here to avoid circular import at module level
        from urllib.parse import parse_qs

        from .api import build_cluster_detail_payload, build_fleet_payload, build_proposals_payload

        params = parse_qs(query)
        selected_run_id = params.get("run_id", [None])[0]

        context = handler._load_context(requested_run_id=selected_run_id)
        if context is None:
            return

        if route == "/api/run":
            from .server_run_detail_reads import handle_run_detail_route
            handle_run_detail_route(handler, query)
            return

        if route == "/api/fleet":
            handler._send_json(build_fleet_payload(context))
            return

        if route == "/api/proposals":
            handler._send_json(build_proposals_payload(context))
            return

        if route == "/api/cluster-detail":
            params = parse_qs(query)
            label = params.get("cluster_label", [None])[0]
            handler._send_json(build_cluster_detail_payload(context, cluster_label=label))
            return

    # Debug routes: delegate to extraction module
    if _handle_debug_routes(handler, route):
        return

    handler._send_text(404, "Not Found")
