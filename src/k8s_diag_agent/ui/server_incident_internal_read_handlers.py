"""Internal API read handlers for incident listing.

This module provides GET handlers for the scheduler-to-backend incident
read API endpoints (listing and fetching incidents).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .api_incident_internal_reads import (
    build_incident_internal_detail_payload,
    build_incident_internal_list_item_payload,
)
from .server_incident_internal_auth import _validate_internal_token

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


def handle_get_incident(handler: HealthUIRequestHandler, incident_id: str) -> None:
    """Handle GET /api/internal/incidents/{incident_id}.

    This endpoint fetches a single incident from the backend SQLite store
    for processing by the automatic diagnosis loop when running in backend-api mode.

    Response:
        Full incident dict if found, or error response
    """
    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Fetch incident from store
    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()
        incident = store.get_incident(incident_id)

        if incident is None:
            handler._send_json(
                {"error": "Not Found", "message": f"Incident {incident_id} not found"},
                404,
            )
            return

        # Haskellized: use total projection function for serialization
        # instead of ad-hoc field access scattered in handler
        handler._send_json(
            build_incident_internal_detail_payload(incident),
            200,
        )

    except Exception as e:
        _logger.exception("Failed to get incident %s", incident_id)
        handler._send_json({
            "error": "Internal Error",
            "message": str(e),
        }, 500)


def handle_list_incidents(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/internal/incidents/list.

    This endpoint lists incidents from the backend SQLite store for the
    automatic diagnosis loop when running in backend-api mode.

    Query parameters:
        status: Optional status filter (e.g., "open", "collecting_evidence")
        limit: Optional maximum number of incidents to return

    Response:
        {
            "incidents": [...],
            "total": N
        }
    """
    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Parse query parameters
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(handler.path)
    query_params = parse_qs(parsed.query)

    status: str | None = None
    status_values = query_params.get("status", [])
    if status_values:
        status = status_values[0]

    limit: int | None = None
    limit_values = query_params.get("limit", [])
    if limit_values:
        try:
            limit = int(limit_values[0])
        except ValueError:
            pass

    # List incidents from store
    try:
        from ..collect.incident_lifecycle import IncidentStatus
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()

        # Parse status filter if provided
        status_filter: IncidentStatus | None = None
        if status is not None:
            try:
                status_filter = IncidentStatus(status)
            except ValueError:
                handler._send_json(
                    {"error": "Bad Request", "message": f"Invalid status: {status}"},
                    400,
                )
                return

        # Get incidents from store
        incidents = store.list_incidents(status=status_filter)

        # Apply limit if specified
        if limit is not None and limit > 0:
            incidents = incidents[:limit]

        # Haskellized: use total projection function for serialization
        # instead of ad-hoc field access scattered in handler
        incident_summaries = [
            build_incident_internal_list_item_payload(inc)
            for inc in incidents
        ]

        handler._send_json({
            "incidents": incident_summaries,
            "total": len(incident_summaries),
        }, 200)

    except Exception as e:
        _logger.exception("Failed to list incidents")
        # Projection failure is an internal error - return 500, not 200
        handler._send_json({
            "error": "Internal Error",
            "message": str(e),
        }, 500)
