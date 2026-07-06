"""Server route handler for Alertmanager webhook endpoint.

This module handles the POST /api/integrations/alertmanager/webhook endpoint.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..collect.incident_store_provider import get_incident_store
from ..incident_alertmanager_webhook import (
    WebhookAuthError,
    WebhookDisabledError,
    WebhookPayloadError,
    handle_alertmanager_webhook,
)
from ..incident_alertmanager_webhook_config import get_alertmanager_webhook_config

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


logger = logging.getLogger(__name__)

# Route constant
ALERTMANAGER_WEBHOOK_ROUTE = "/api/integrations/alertmanager/webhook"


def handle_alertmanager_webhook_api(handler: HealthUIRequestHandler) -> None:
    """Handle POST /api/integrations/alertmanager/webhook.

    This endpoint accepts Alertmanager webhook payloads, normalizes them
    into AlertSignal objects, and persists them as artifacts.

    Authentication:
        Bearer token required if configured via K9B_ALERTMANAGER_WEBHOOK_TOKEN
        or K9B_ALERTMANAGER_WEBHOOK_TOKEN_FILE.

    Responses:
        200: Webhook accepted and processed
        400: Invalid payload or normalization error
        401: Authentication failed
        403: Webhook disabled or forbidden
        413: Payload too large
        500: Internal server error

    Args:
        handler: The HTTP request handler instance
    """
    from .server_response import send_json_response

    # Get configuration
    config = get_alertmanager_webhook_config()

    # Get runs_dir from handler
    root = handler.runs_dir

    # Get Authorization header (for logging purposes only - never log token value)
    auth_header = handler.headers.get("Authorization")

    # Determine content length and validate against max before reading body
    content_length_str = handler.headers.get("Content-Length", "")
    try:
        content_length = int(content_length_str) if content_length_str else 0
    except ValueError:
        content_length = -1  # Invalid Content-Length

    # Pre-read size guard: reject oversized payloads before reading full body
    if content_length > config.max_payload_bytes:
        send_json_response(
            handler,
            {
                "accepted": False,
                "error": "payload_too_large",
                "errors": [
                    {
                        "field": "content-length",
                        "message": f"Content-Length {content_length} exceeds maximum {config.max_payload_bytes}",
                    }
                ],
            },
            413,
        )
        return

    # Invalid Content-Length is handled by parse_payload as fail-closed
    # Read request body
    raw_body = b""
    if content_length > 0:
        raw_body = handler.rfile.read(content_length)

    # Get incident store for auto-promotion (if enabled)
    incident_store = None
    if config.auto_promote:
        incident_store = get_incident_store()

    # Handle the webhook request
    try:
        response, status_code = handle_alertmanager_webhook(
            auth_header=auth_header,
            raw_body=raw_body,
            config=config,
            root=root,
            incident_store=incident_store,
        )

        if status_code == 200:
            send_json_response(handler, response.to_dict(), status_code)
        else:
            # Return error format for non-200 responses
            send_json_response(handler, response.to_error_dict(), status_code)

    except WebhookDisabledError:
        # When disabled, return 403 Forbidden (fail-closed)
        send_json_response(
            handler,
            {
                "accepted": False,
                "error": "webhook_disabled",
                "errors": [{"field": "webhook", "message": "Webhook endpoint is disabled"}],
            },
            403,
        )

    except WebhookAuthError as e:
        # Authentication failed
        # NOTE: We don't log the actual error message as it may contain
        # sensitive information about the auth failure type
        logger.debug("Alertmanager webhook auth failed", extra={"reason": str(e)})
        send_json_response(
            handler,
            {
                "accepted": False,
                "error": "authentication_failed",
                "errors": [{"field": "auth", "message": "Invalid or missing authorization"}],
            },
            401,
        )

    except WebhookPayloadError as e:
        # Payload validation failed
        error_message = str(e)

        if "too large" in error_message.lower():
            send_json_response(
                handler,
                {
                    "accepted": False,
                    "error": "payload_too_large",
                    "errors": [{"field": "body", "message": error_message}],
                },
                413,
            )
        elif "json" in error_message.lower():
            send_json_response(
                handler,
                {
                    "accepted": False,
                    "error": "invalid_json",
                    "errors": [{"field": "body", "message": "Request body must be valid JSON"}],
                },
                400,
            )
        elif "alerts" in error_message.lower():
            send_json_response(
                handler,
                {
                    "accepted": False,
                    "error": "invalid_payload",
                    "errors": [{"field": "alerts", "message": "Missing required 'alerts' field"}],
                },
                400,
            )
        else:
            send_json_response(
                handler,
                {
                    "accepted": False,
                    "error": "invalid_payload",
                    "errors": [{"field": "body", "message": error_message}],
                },
                400,
            )

    except Exception:
        # Unexpected error - log and return 500
        logger.exception("Unexpected error in Alertmanager webhook handler")
        send_json_response(
            handler,
            {
                "accepted": False,
                "error": "internal_error",
                "errors": [{"field": "server", "message": "Internal server error"}],
            },
            500,
        )


__all__ = [
    "handle_alertmanager_webhook_api",
    "ALERTMANAGER_WEBHOOK_ROUTE",
]
