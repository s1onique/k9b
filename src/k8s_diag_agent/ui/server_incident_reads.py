"""Read-only incident API route handlers.

This module handles GET requests for incident store:
- GET /api/incidents - list all incidents
- GET /api/incidents/{incident_id} - get specific incident

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ..collect.api_incident_reads import handle_get_incident, handle_list_incidents
from ..security import sanitize_exception_message
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for incident detail
_INCIDENT_DETAIL_PATTERN = re.compile(r"^/api/incidents/([^/]+)$")


def handle_incidents_list_route(handler: HealthUIRequestHandler, query: str) -> bool:
    """Handle GET /api/incidents route.

    Lists all incidents from the in-memory store with optional status filter.

    Query parameters:
        status: Optional status filter (e.g., "open", "collecting_evidence")

    Response:
        {
            "incidents": [...],
            "total": N
        }
    """
    from urllib.parse import parse_qs

    params = parse_qs(query)
    status = params.get("status", [None])[0]

    try:
        result = handle_list_incidents(status=status)
        send_json_response(handler, result, code=200)
        return True
    except Exception as exc:
        # Sanitize exception message to prevent credential/exception leakage
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Failed to list incidents: %s",
            sanitized_message,
        )
        send_json_response(handler, {"error": "Failed to list incidents", "incidents": [], "total": 0}, code=500)
        return True


def handle_incident_detail_route(handler: HealthUIRequestHandler, path: str) -> bool:
    """Handle GET /api/incidents/{incident_id} route.

    Gets a specific incident by ID.

    Response (200):
        { ... incident dict ... }

    Error (404):
        {"error": "Incident not found"}
    """
    match = _INCIDENT_DETAIL_PATTERN.match(path)
    if not match:
        return False

    incident_id = match.group(1)

    # Compute external_analysis_dir from handler's health_root
    external_analysis_dir = handler._health_root / "external-analysis"

    try:
        result = handle_get_incident(incident_id, external_analysis_dir=external_analysis_dir)
        if result is None:
            send_json_response(handler, {"error": "Incident not found"}, code=404)
        else:
            send_json_response(handler, result, code=200)
        return True
    except Exception as exc:
        # Sanitize exception message to prevent credential/exception leakage
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Failed to get incident %s: %s",
            incident_id,
            sanitized_message,
        )
        send_json_response(handler, {"error": "Failed to get incident"}, code=500)
        return True


def handle_incident_routes(handler: HealthUIRequestHandler, route: str, query: str) -> bool:
    """Dispatch incident read routes.

    Args:
        handler: The HTTP request handler instance
        route: The request path
        query: The query string

    Returns:
        True if route was handled, False otherwise
    """
    # List route: /api/incidents
    if route == "/api/incidents":
        return handle_incidents_list_route(handler, query)

    # Detail route: /api/incidents/{incident_id}
    return handle_incident_detail_route(handler, route)


__all__ = [
    "handle_incident_routes",
    "handle_incident_detail_route",
    "handle_incidents_list_route",
]
