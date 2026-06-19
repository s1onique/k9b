"""Read-only incident API route handlers.

This module handles GET requests for incident store:
- GET /api/incidents - list all incidents
- GET /api/incidents/{incident_id} - get specific incident
- GET /api/incidents/{incident_id}/automatic-diagnosis-review/handoff - get review handoff

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
from .api_incident_reads_handoff import build_automatic_diagnosis_review_handoff_payload
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for incident detail
_INCIDENT_DETAIL_PATTERN = re.compile(r"^/api/incidents/([^/]+)$")

# Route pattern for automatic diagnosis review handoff
_HANDOFF_PATTERN = re.compile(r"^/api/incidents/([^/]+)/automatic-diagnosis-review/handoff$")


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


def handle_automatic_diagnosis_review_handoff_route(
    handler: HealthUIRequestHandler, path: str
) -> bool:
    """Handle GET /api/incidents/{incident_id}/automatic-diagnosis-review/handoff route.

    Gets a bounded handoff payload for the latest automatic diagnosis review packet.

    This is a read-only endpoint that provides a sanitized markdown handoff
    suitable for human/ChatGPT review. It does not expose raw packet contents,
    absolute paths, secrets, or action controls.

    Response (200):
        { ... handoff payload ... }

    Error (400):
        {"error": "invalid_incident_id"}
    """
    match = _HANDOFF_PATTERN.match(path)
    if not match:
        return False

    incident_id = match.group(1)

    # Validate incident_id for safety
    # incident_id should be alphanumeric with safe characters
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_.-]+$", incident_id):
        send_json_response(handler, {"error": "invalid_incident_id"}, code=400)
        return True

    # Compute external_analysis_dir from handler's health_root
    external_analysis_dir = handler._health_root / "external-analysis"

    try:
        result = build_automatic_diagnosis_review_handoff_payload(
            external_analysis_dir, incident_id
        )
        send_json_response(handler, result, code=200)
        return True
    except Exception as exc:
        # Sanitize exception message to prevent credential/exception leakage
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Failed to get handoff for incident %s: %s",
            incident_id,
            sanitized_message,
        )
        send_json_response(handler, {"error": "Failed to get handoff"}, code=500)
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
    # Handoff route: /api/incidents/{incident_id}/automatic-diagnosis-review/handoff
    # Check this first before detail route to avoid pattern conflicts
    handoff_match = _HANDOFF_PATTERN.match(route)
    if handoff_match:
        return handle_automatic_diagnosis_review_handoff_route(handler, route)

    # List route: /api/incidents
    if route == "/api/incidents":
        return handle_incidents_list_route(handler, query)

    # Detail route: /api/incidents/{incident_id}
    return handle_incident_detail_route(handler, route)


__all__ = [
    "handle_incident_routes",
    "handle_incident_detail_route",
    "handle_incidents_list_route",
    "handle_automatic_diagnosis_review_handoff_route",
]
