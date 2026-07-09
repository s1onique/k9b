"""Internal API read handlers for incident listing.

This module provides GET handlers for the scheduler-to-backend incident
read API endpoints (listing and fetching incidents).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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

        # Convert to response format
        handler._send_json({
            "incident_id": incident.incident_id,
            "status": incident.status.value,
            "created_at": incident.created_at.isoformat() if incident.created_at else None,
            "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
            "severity": incident.severity.value if incident.severity else None,
            "namespace": incident.namespace,
            "object_name": incident.object_name,
            "object_kind": incident.object_kind.value if incident.object_kind else None,
            "summary": incident.summary,
            "description": incident.description,
            "signals": [
                {
                    "signal_id": sig.signal_id,
                    "source": sig.source,
                    "reason": sig.reason,
                    "message": sig.message,
                    "severity": sig.severity.value if sig.severity else None,
                    "observed_at": sig.observed_at.isoformat() if sig.observed_at else None,
                }
                for sig in incident.signals
            ] if incident.signals else [],
        }, 200)

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

        # Convert to summary format (minimal data for internal API)
        incident_summaries = []
        for inc in incidents:
            incident_summaries.append({
                "incident_id": inc.incident_id,
                "status": inc.status.value,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
                "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
            })

        handler._send_json({
            "incidents": incident_summaries,
            "total": len(incident_summaries),
        }, 200)

    except Exception as e:
        _logger.exception("Failed to list incidents")
        handler._send_json({
            "error": "Internal Error",
            "message": str(e),
            "incidents": [],
            "total": 0,
        }, 500)
