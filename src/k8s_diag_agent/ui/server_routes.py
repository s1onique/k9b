"""Route dispatch and API orchestration for the UI server.

This module contains route dispatch handlers extracted from server.py
to keep the main server module below size thresholds. These handlers manage:
- HTTP method routing (GET, POST, OPTIONS)
- Path matching and route delegation
- Authentication validation for mutation endpoints
- Exception boundaries at the route level

All functions are designed to work with HealthUIRequestHandler instances.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


# Route patterns for path matching
_RUN_ALERTMANAGER_SOURCE_ACTION = re.compile(
    r"^/api/runs/([^/]+)/alertmanager-sources/([^/]+)/action$"
)
_INCIDENT_DIAGNOSIS_LOOP_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/diagnosis-loop/one-pass$"
)
_INCIDENT_ONE_PASS_DIAGNOSIS_SERVICE_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/one-pass-diagnosis$"
)
# NEW: Incident automatic diagnosis loop one-pass (uses real collector, not fake-runner)
_INCIDENT_AUTOMATIC_DIAGNOSIS_LOOP_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/automatic-diagnosis-loop/one-pass$"
)


def handle_get_request(handler: HealthUIRequestHandler) -> None:
    """Handle GET requests by routing to appropriate handlers.

    Args:
        handler: The HTTP request handler instance
    """
    route, _, query = handler.path.partition("?")
    handler._request_method = "GET"
    handler._request_path = route
    handler._request_query = query
    handler._is_static = not route.startswith("/api/") and route != "/artifact"

    try:
        # AUTH-06: Check authentication for protected routes (API and artifact serving)
        # Note: /artifact requires auth as it may expose sensitive cluster data
        # Auth routes (/api/auth/*) are always public
        # Protected routes: /api/* (except auth routes) and /artifact/*
        is_protected_api = route.startswith("/api/") and not _is_auth_route(route)
        is_protected_artifact = route == "/artifact" or route.startswith("/artifact/")
        if is_protected_api or is_protected_artifact:
            from .auth_guard import check_route_auth

            if not check_route_auth(handler):
                handler._status_code = 401
                handler._log_access_completion()
                return

        if route.startswith("/api/"):
            _handle_api_get(handler, route, query)
        elif route == "/artifact" or route.startswith("/artifact/"):
            from .server_static import serve_artifact

            serve_artifact(handler, query)
        else:
            from .server_static import serve_static

            serve_static(handler, route)
    except Exception:
        # REVIEWED: Final HTTP framework boundary for GET route dispatch.
        # Prevents raw tracebacks / broken sockets from escaping to clients.
        # Returns existing controlled 500 behavior via self._status_code = 500.
        # Narrower exceptions are handled inside route-specific handlers
        # (serve_static, serve_artifact, _handle_api_get) before this catch.
        handler._status_code = 500
        handler._log_access_completion()
        raise
    else:
        handler._log_access_completion()


def handle_post_request(handler: HealthUIRequestHandler) -> None:
    """Handle POST requests by routing to appropriate mutation handlers.

    Validates session-based authentication for mutation endpoints,
    then delegates to route-specific handlers.

    Args:
        handler: The HTTP request handler instance
    """
    route, _, _ = handler.path.partition("?")
    handler._request_method = "POST"
    handler._request_path = route
    handler._request_query = ""
    handler._is_static = False

    # AUTH-06: Check authentication for protected routes (includes POST mutations)
    if not _is_auth_route(route):
        from .auth_guard import check_route_auth

        if not check_route_auth(handler):
            handler._status_code = 401
            handler._log_access_completion()
            return

    try:
        _dispatch_post_route(handler, route)
    except Exception:
        # REVIEWED: Final HTTP framework boundary for POST route dispatch.
        # Prevents raw tracebacks / broken sockets from escaping to clients.
        # Returns existing controlled 500 behavior via self._status_code = 500.
        # Narrower exceptions are handled inside route-specific handlers
        # (handle_* functions) before this catch.
        handler._status_code = 500
        handler._log_access_completion()
        raise
    else:
        handler._log_access_completion()


def _is_auth_route(route: str) -> bool:
    """Check if route is an auth route (public, no auth required).

    Args:
        route: The request path

    Returns:
        True if route is an auth route, False otherwise
    """
    # Auth routes are always public
    if route.startswith("/api/auth/"):
        return True
    return False


def _handle_api_get(handler: HealthUIRequestHandler, route: str, query: str) -> None:
    """Handle API GET requests by delegating to server_reads module.

    Args:
        handler: The HTTP request handler instance
        route: The request path
        query: The query string
    """
    from .server_reads import handle_api as _handle_api_reads

    _handle_api_reads(handler, route, query)


def _dispatch_post_route(handler: HealthUIRequestHandler, route: str) -> None:
    """Dispatch POST request to appropriate route handler.

    Args:
        handler: The HTTP request handler instance
        route: The request path

    Raises:
        Sets handler._status_code = 404 if no route matches.
    """
    # Import handlers here to avoid circular imports at module level
    from .server_alertmanager import handle_alertmanager_source_action
    from .server_batch_execution import handle_run_batch_next_check_execution
    from .server_feedback import handle_alertmanager_relevance_feedback, handle_usefulness_feedback
    from .server_incident import handle_incident_snapshot_api
    from .server_next_checks import (
        handle_deterministic_promotion,
        handle_next_check_approval,
        handle_next_check_execution,
    )
    from .server_review_packet import handle_incident_review_packet_api

    # AUTH routes - public, no auth required (they SET the session)
    if route == "/api/auth/login":
        from .auth_routes import handle_login

        handle_login(handler)
        return

    if route == "/api/auth/logout":
        from .auth_routes import handle_logout

        handle_logout(handler)
        return

    # Incident snapshot capture
    if route == "/api/incidents/snapshot":
        handle_incident_snapshot_api(handler)
        return

    # Incident review packet generation
    if route == "/api/incidents/review-packet":
        handle_incident_review_packet_api(handler)
        return

    # Incident diagnosis loop one-pass
    # POST /api/incidents/{incident_id}/diagnosis-loop/one-pass
    incident_dl_match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(route)
    if incident_dl_match:
        from .server_incident_diagnosis_loop import (
            handle_incident_diagnosis_loop_one_pass_api,
        )

        incident_id = incident_dl_match.group(1)
        handle_incident_diagnosis_loop_one_pass_api(handler, incident_id)
        return

    # Incident one-pass diagnosis service (calls run_incident_one_pass_diagnosis)
    # POST /api/incidents/{incident_id}/one-pass-diagnosis
    incident_svc_match = _INCIDENT_ONE_PASS_DIAGNOSIS_SERVICE_PATTERN.match(route)
    if incident_svc_match:
        from .server_incident_one_pass_diagnosis_service import (
            handle_incident_one_pass_diagnosis_service_api,
        )

        incident_id = incident_svc_match.group(1)
        handle_incident_one_pass_diagnosis_service_api(handler, incident_id)
        return

    # Delegate next-check mutation handlers to server_next_checks module
    if route == "/api/deterministic-next-check/promote":
        handle_deterministic_promotion(handler)
        return
    if route == "/api/next-check-execution":
        handle_next_check_execution(handler)
        return
    if route == "/api/next-check-approval":
        handle_next_check_approval(handler)
        return
    if route == "/api/next-check-execution-usefulness":
        handle_usefulness_feedback(handler)
        return
    if route == "/api/alertmanager-relevance-feedback":
        handle_alertmanager_relevance_feedback(handler)
        return
    if route == "/api/run-batch-next-check-execution":
        handle_run_batch_next_check_execution(handler)
        return
    # Alertmanager source action endpoint: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action
    # Body: { "action": "promote"|"disable", "reason": "..." }
    runs_am_source_match = _RUN_ALERTMANAGER_SOURCE_ACTION.match(route)
    if runs_am_source_match:
        run_id = runs_am_source_match.group(1)
        # Decode URL-encoded source_id before lookup/validation
        # e.g., "crd%3Amonitoring%2Fkube-prometheus-stack-alertmanager" -> "crd:monitoring/kube-prometheus-stack-alertmanager"
        source_id = unquote(runs_am_source_match.group(2))
        handle_alertmanager_source_action(handler, run_id, source_id)
        return

    # NEW: Incident automatic diagnosis loop one-pass
    # POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
    # Wraps collect_automatic_diagnosis_evidence() - uses REAL automatic loop collector
    incident_auto_dl_match = _INCIDENT_AUTOMATIC_DIAGNOSIS_LOOP_PATTERN.match(route)
    if incident_auto_dl_match:
        from .server_incident_automatic_diagnosis_loop import (
            handle_incident_automatic_diagnosis_loop_one_pass_api,
        )

        incident_id = incident_auto_dl_match.group(1)
        handle_incident_automatic_diagnosis_loop_one_pass_api(handler, incident_id)
        return

    handler._status_code = 404
    handler._send_text(404, "Not Found")
