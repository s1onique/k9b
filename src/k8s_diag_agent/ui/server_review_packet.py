"""HTTP handler for incident review packet API.

This module handles POST /api/incidents/review-packet requests from the UI.
It generates self-contained review packets from captured incident bundles.

Hard constraint: End-state must be k9b-only and self-contained.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ..collect.api_incident_review_packet import (
    IncidentReviewPacketRequest,
    handle_incident_review_packet,
)
from .server_shared import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


def handle_incident_review_packet_api(handler: HealthUIRequestHandler) -> None:
    """Handle POST /api/incidents/review-packet.

    Generates a self-contained review packet from a captured incident bundle.

    Request body:
        {
            "bundle": { ... incident evidence bundle ... },
            "format": "markdown"  // optional, default "markdown"
        }

    Response:
        {
            "bundle_id": "bundle-identifier",
            "packet": "# k9b Incident Review Packet\n\n...",
            "format": "markdown"
        }
    """
    try:
        # Parse request body
        content_length = handler.headers.get("Content-Length")
        if not content_length:
            _logger.warning("Missing Content-Length header for review packet request")
            send_json_response(handler, 400, {"error": "Missing Content-Length header"})
            return

        try:
            body = handler.rfile.read(int(content_length))
        except OSError as exc:
            _logger.warning("Failed to read request body: %s", exc)
            send_json_response(handler, 400, {"error": "Failed to read request body"})
            return

        try:
            request_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _logger.warning("Failed to parse review packet request: %s", exc)
            send_json_response(handler, 400, {"error": f"Invalid JSON: {exc}"})
            return

        # Extract bundle from request
        bundle = request_data.get("bundle")
        if not bundle:
            _logger.warning("Review packet request missing bundle field")
            send_json_response(handler, 400, {"error": "Missing required field: bundle"})
            return

        # Extract format (optional, default to markdown)
        format_type = request_data.get("format", "markdown")

        # Validate format
        if format_type not in ("markdown",):
            _logger.warning("Unsupported format type: %s", format_type)
            send_json_response(handler, 400, {"error": "Unsupported format. Only 'markdown' is supported."})
            return

        # Build request object
        request = IncidentReviewPacketRequest(
            bundle=bundle,
            format=format_type,
        )

        # Generate the packet
        response = handle_incident_review_packet(request)

        # Send response
        send_json_response(handler, 200, response.to_dict())

    except (OSError, RuntimeError) as exc:
        # Handle expected I/O and runtime errors
        _logger.error("Error in review packet handler: %s", exc)
        send_json_response(handler, 500, {"error": "Internal server error"})
        return


__all__ = [
    "handle_incident_review_packet_api",
]
