"""Alertmanager webhook handler for ingesting alerts as signals.

This module provides the core business logic for handling Alertmanager
webhook requests:
- Bearer token authentication
- Payload validation and size bounds
- Raw payload artifact persistence
- Signal normalization
- Idempotent signal artifact persistence
"""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .incident_alert_signal import AlertSignal
from .incident_alert_signal_normalizer import (
    normalize_alertmanager_payload,
)
from .incident_alert_signal_store import (
    write_alert_signal_artifact,
    write_raw_payload_artifact,
)
from .incident_alertmanager_webhook_config import (
    AlertmanagerWebhookConfig,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Webhook Response Types
# =============================================================================


@dataclass
class WebhookError:
    """Individual error in webhook processing."""
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass
class WebhookResponse:
    """Response from webhook processing.

    This is the canonical response format for the webhook endpoint.
    """
    accepted: bool
    source_instance: str = ""
    received_alert_count: int = 0
    normalized_signal_count: int = 0
    stored_signal_count: int = 0
    duplicate_signal_count: int = 0
    error_count: int = 0
    errors: list[WebhookError] = field(default_factory=list)
    raw_payload_artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "source_instance": self.source_instance,
            "received_alert_count": self.received_alert_count,
            "normalized_signal_count": self.normalized_signal_count,
            "stored_signal_count": self.stored_signal_count,
            "duplicate_signal_count": self.duplicate_signal_count,
            "error_count": self.error_count,
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
            "raw_payload_artifact_id": self.raw_payload_artifact_id,
        }

    def to_error_dict(self) -> dict[str, Any]:
        """Convert to error response format."""
        return {
            "accepted": False,
            "error": "invalid_payload" if self.errors else "processing_error",
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
        }


# =============================================================================
# Error Classes
# =============================================================================


class WebhookAuthError(Exception):
    """Raised when authentication fails."""
    pass


class WebhookPayloadError(Exception):
    """Raised when payload validation fails."""
    pass


class WebhookDisabledError(Exception):
    """Raised when webhook is disabled."""
    pass


# =============================================================================
# Validation Functions
# =============================================================================


def validate_bearer_token(
    auth_header: str | None,
    expected_token: str | None,
) -> bool:
    """Validate Bearer token for webhook authentication.

    Args:
        auth_header: Authorization header value
        expected_token: Expected bearer token

    Returns:
        True if token is valid

    Raises:
        WebhookAuthError: If authentication fails
    """
    if not expected_token:
        raise WebhookAuthError("No token configured")

    if not auth_header:
        raise WebhookAuthError("Missing Authorization header")

    if not auth_header.startswith("Bearer "):
        raise WebhookAuthError("Invalid Authorization scheme")

    token = auth_header[7:]

    if not hmac.compare_digest(token, expected_token):
        raise WebhookAuthError("Invalid token")

    return True


def validate_payload_size(
    payload_bytes: int,
    max_bytes: int,
) -> None:
    """Validate payload size against limit.

    Args:
        payload_bytes: Size of payload in bytes
        max_bytes: Maximum allowed size

    Raises:
        WebhookPayloadError: If payload is too large
    """
    if payload_bytes > max_bytes:
        raise WebhookPayloadError(
            f"Payload too large: {payload_bytes} bytes (max {max_bytes})"
        )


def parse_payload(
    raw_body: bytes,
    max_bytes: int,
) -> dict[str, Any]:
    """Parse and validate JSON payload.

    Args:
        raw_body: Raw request body bytes
        max_bytes: Maximum allowed size

    Returns:
        Parsed JSON payload

    Raises:
        WebhookPayloadError: If parsing fails or payload is invalid
    """
    if len(raw_body) > max_bytes:
        raise WebhookPayloadError(
            f"Payload too large: {len(raw_body)} bytes (max {max_bytes})"
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise WebhookPayloadError(f"Invalid JSON: {e}")

    if not isinstance(payload, dict):
        raise WebhookPayloadError("Payload must be a JSON object")

    if "alerts" not in payload:
        raise WebhookPayloadError("Missing required 'alerts' field")

    return payload


# =============================================================================
# Processing Functions
# =============================================================================


def process_webhook(
    payload: dict[str, Any],
    config: AlertmanagerWebhookConfig,
    root: Path,
    received_at: datetime | None = None,
) -> WebhookResponse:
    """Process an Alertmanager webhook payload.

    This function:
    1. Normalizes the payload into AlertSignal objects
    2. Writes the raw payload artifact
    3. Writes each signal to an idempotent artifact
    4. Returns a summary response

    Args:
        payload: Parsed JSON payload
        config: Webhook configuration
        root: Runs directory root for artifact persistence
        received_at: When the payload was received (defaults to now)

    Returns:
        WebhookResponse with processing summary
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    errors: list[WebhookError] = []
    normalized_signals: list[AlertSignal] = []

    # Step 1: Write raw payload artifact
    raw_result = write_raw_payload_artifact(
        root=root,
        payload=payload,
        source_instance=config.source_instance,
        received_at=received_at,
    )

    raw_payload_artifact_id: str | None = None
    if raw_result.success:
        raw_payload_artifact_id = raw_result.artifact_id
    else:
        errors.append(WebhookError(
            field="raw_payload",
            message=raw_result.error or "Failed to write raw payload",
        ))

    # Step 2: Normalize payload
    normalization_result = normalize_alertmanager_payload(
        payload,
        source_instance=config.source_instance,
        received_at=received_at,
    )

    # Collect normalization errors
    for err in normalization_result.errors:
        errors.append(WebhookError(field=err.field, message=err.message))

    normalized_signals = list(normalization_result.signals)

    # Step 3: Write signals idempotently
    stored_count = 0
    duplicate_count = 0

    for signal in normalized_signals:
        # Update signal with raw payload artifact ID
        signal_with_ref = AlertSignal(
            signal_id=signal.signal_id,
            source_type=signal.source_type,
            source_instance=signal.source_instance,
            status=signal.status,
            alertname=signal.alertname,
            external_fingerprint=signal.external_fingerprint,
            group_key=signal.group_key,
            receiver=signal.receiver,
            severity=signal.severity,
            labels=signal.labels,
            annotations=signal.annotations,
            starts_at=signal.starts_at,
            ends_at=signal.ends_at,
            received_at=signal.received_at,
            generator_url=signal.generator_url,
            external_url=signal.external_url,
            raw_payload_artifact_id=raw_payload_artifact_id,
            truncation=signal.truncation,
        )

        write_result = write_alert_signal_artifact(
            root=root,
            signal=signal_with_ref,
            raw_payload_artifact_id=raw_payload_artifact_id,
            received_at=received_at,
        )

        if write_result.is_duplicate:
            duplicate_count += 1
        elif write_result.success:
            stored_count += 1
        else:
            errors.append(WebhookError(
                field=f"signal:{signal.alertname}",
                message=write_result.error or "Failed to write signal",
            ))

    # Build response
    accepted = len(normalized_signals) > 0 and all(
        e.field == "alerts" for e in errors
    ) or len(normalized_signals) == 0 and len(errors) == 0

    return WebhookResponse(
        accepted=accepted,
        source_instance=config.source_instance,
        received_alert_count=len(payload.get("alerts", [])),
        normalized_signal_count=len(normalized_signals),
        stored_signal_count=stored_count,
        duplicate_signal_count=duplicate_count,
        error_count=len(errors),
        errors=errors,
        raw_payload_artifact_id=raw_payload_artifact_id,
    )


# =============================================================================
# Request Handler
# =============================================================================


def handle_alertmanager_webhook(
    auth_header: str | None,
    raw_body: bytes,
    config: AlertmanagerWebhookConfig,
    root: Path,
) -> tuple[WebhookResponse, int]:
    """Handle an incoming Alertmanager webhook request.

    This is the main entry point for the webhook handler. It:
    1. Validates authentication (if required)
    2. Validates payload size and format
    3. Processes the payload
    4. Returns response and HTTP status code

    Args:
        auth_header: Authorization header value
        raw_body: Raw request body bytes
        config: Webhook configuration
        root: Runs directory root for artifact persistence

    Returns:
        Tuple of (WebhookResponse, HTTP status code)

    Raises:
        WebhookDisabledError: If webhook is disabled
        WebhookAuthError: If authentication fails
        WebhookPayloadError: If payload validation fails
    """
    # Step 1: Check if enabled
    if not config.enabled:
        raise WebhookDisabledError("Webhook endpoint is disabled")

    # Step 2: Validate authentication
    if config.requires_auth():
        validate_bearer_token(auth_header, config.bearer_token)

    # Step 3: Parse and validate payload
    payload = parse_payload(raw_body, config.max_payload_bytes)

    # Step 4: Process webhook
    received_at = datetime.now(UTC)
    response = process_webhook(
        payload=payload,
        config=config,
        root=root,
        received_at=received_at,
    )

    # Determine status code
    if response.normalized_signal_count == 0 and response.error_count > 0:
        status_code = 400  # Bad request - invalid payload
    elif not response.accepted:
        status_code = 400
    else:
        status_code = 200  # Success

    return response, status_code


__all__ = [
    # Response types
    "WebhookError",
    "WebhookResponse",
    # Error types
    "WebhookAuthError",
    "WebhookPayloadError",
    "WebhookDisabledError",
    # Validation functions
    "validate_bearer_token",
    "validate_payload_size",
    "parse_payload",
    # Processing functions
    "process_webhook",
    "handle_alertmanager_webhook",
]
