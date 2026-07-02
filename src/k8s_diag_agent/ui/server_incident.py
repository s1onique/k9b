"""Incident snapshot capture API handler.

This module handles POST /api/incidents/snapshot requests from the UI.
It captures read-only Kubernetes evidence bundles for LLM review.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ..collect.api_incident import (
    IncidentSnapshotRequest,
    handle_incident_snapshot,
)
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


def handle_incident_snapshot_api(handler: HealthUIRequestHandler) -> None:
    """Handle POST /api/incidents/snapshot.

    Captures a read-only incident evidence bundle for a namespace.

    Request body:
        {
            "namespace": "k9b",
            "since_hours": 2
        }

    Response:
        {
            "bundle_id": "...",
            "captured_at": "...",
            "namespace": "...",
            "summary": {
                "total_pods": 0,
                "failing_pods_count": 0,
                "total_deployments": 0,
                "total_events": 0,
                "symptoms_count": 0
            },
            "bundle": { ... sanitized incident evidence ... }
        }

    Error response:
        {
            "bundle_id": "",
            "captured_at": "...",
            "namespace": "...",
            "summary": {...},
            "error": "sanitized error message"
        }
    """
    # Parse request body
    try:
        content_length = int(handler.headers.get("Content-Length", 0))
        if content_length == 0:
            body = {}
        else:
            body_bytes = handler.rfile.read(content_length)
            body = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse incident snapshot request: %s", exc)
        send_json_response(
            handler,
            {
                "bundle_id": "",
                "captured_at": "",
                "namespace": "",
                "summary": {},
                "error": "Invalid request body",
            },
            code=400,
            request_path=handler._request_path,
        )
        return

    # Extract request parameters
    namespace = body.get("namespace")
    if not namespace or not isinstance(namespace, str):
        send_json_response(
            handler,
            {
                "bundle_id": "",
                "captured_at": "",
                "namespace": "",
                "summary": {},
                "error": "namespace is required",
            },
            code=400,
            request_path=handler._request_path,
        )
        return

    # Accept both snake_case (legacy) and camelCase (OpenAPI spec) field names
    since_hours = body.get("sinceHours") or body.get("since_hours") or 2
    if not isinstance(since_hours, int) or since_hours < 1:
        since_hours = 2

    # Create request object
    request = IncidentSnapshotRequest(
        namespace=namespace,
        since_hours=since_hours,
        context=None,  # Use in-cluster auth
    )

    # Handle the snapshot request
    response = handle_incident_snapshot(request)

    # Determine response code
    code = 200 if response.error is None else 500

    # Send response
    send_json_response(
        handler,
        response.to_dict(),
        code=code,
        request_path=handler._request_path,
    )


__all__ = [
    "handle_incident_snapshot_api",
]
