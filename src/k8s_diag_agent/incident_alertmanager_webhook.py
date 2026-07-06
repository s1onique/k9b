"""Alertmanager webhook handler - authentication, validation, processing, auto-promotion."""
from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .incident_alert_signal import AlertSignal
from .incident_alert_signal_normalizer import normalize_alertmanager_payload
from .incident_alert_signal_store import write_alert_signal_artifact, write_raw_payload_artifact
from .incident_alertmanager_webhook_config import AlertmanagerWebhookConfig

if TYPE_CHECKING:
    from .collect.incident_store import IncidentStore

logger = logging.getLogger(__name__)


@dataclass
class WebhookError:
    """Individual error in webhook processing."""
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass
class WebhookPromotionSummary:
    """Summary of promotion attempt - included in response when auto-promotion is enabled."""
    enabled: bool
    scanned_signal_count: int = 0
    firing_signal_count: int = 0
    resolved_signal_count: int = 0
    opened_incident_count: int = 0
    updated_incident_count: int = 0
    skipped_duplicate_count: int = 0
    skipped_resolved_without_open_incident_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        return {
            "enabled": True,
            "scanned_signal_count": self.scanned_signal_count,
            "firing_signal_count": self.firing_signal_count,
            "resolved_signal_count": self.resolved_signal_count,
            "opened_incident_count": self.opened_incident_count,
            "updated_incident_count": self.updated_incident_count,
            "skipped_duplicate_count": self.skipped_duplicate_count,
            "skipped_resolved_without_open_incident_count": self.skipped_resolved_without_open_incident_count,
            "error_count": self.error_count,
        }


@dataclass
class WebhookResponse:
    """Canonical response format for webhook endpoint."""
    accepted: bool
    source_instance: str = ""
    received_alert_count: int = 0
    normalized_signal_count: int = 0
    stored_signal_count: int = 0
    duplicate_signal_count: int = 0
    error_count: int = 0
    errors: list[WebhookError] = field(default_factory=list)
    raw_payload_artifact_id: str | None = None
    promotion: WebhookPromotionSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "accepted": self.accepted,
            "source_instance": self.source_instance,
            "received_alert_count": self.received_alert_count,
            "normalized_signal_count": self.normalized_signal_count,
            "stored_signal_count": self.stored_signal_count,
            "duplicate_signal_count": self.duplicate_signal_count,
            "error_count": len(self.errors) if self.errors else self.error_count,
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
            "raw_payload_artifact_id": self.raw_payload_artifact_id,
        }
        if self.promotion is not None:
            result["promotion"] = self.promotion.to_dict()
        return result

    def to_error_dict(self) -> dict[str, Any]:
        """Convert to error response format."""
        return {
            "accepted": False,
            "error": "invalid_payload" if self.errors else "processing_error",
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
        }


class WebhookAuthError(Exception):
    """Raised when authentication fails."""
    pass


class WebhookPayloadError(Exception):
    """Raised when payload validation fails."""
    pass


class WebhookDisabledError(Exception):
    """Raised when webhook is disabled."""
    pass


def validate_bearer_token(auth_header: str | None, expected_token: str | None) -> bool:
    """Validate Bearer token for webhook authentication."""
    if not expected_token:
        raise WebhookAuthError("No token configured")
    if not auth_header:
        raise WebhookAuthError("Missing Authorization header")
    if not auth_header.startswith("Bearer "):
        raise WebhookAuthError("Invalid Authorization scheme")
    if not hmac.compare_digest(auth_header[7:], expected_token):
        raise WebhookAuthError("Invalid token")
    return True


def validate_payload_size(payload_bytes: int, max_bytes: int) -> None:
    """Validate payload size against limit."""
    if payload_bytes > max_bytes:
        raise WebhookPayloadError(f"Payload too large: {payload_bytes} bytes (max {max_bytes})")


def parse_payload(raw_body: bytes, max_bytes: int) -> dict[str, Any]:
    """Parse and validate JSON payload."""
    if len(raw_body) > max_bytes:
        raise WebhookPayloadError(f"Payload too large: {len(raw_body)} bytes (max {max_bytes})")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise WebhookPayloadError(f"Invalid JSON: {e}")
    if not isinstance(payload, dict):
        raise WebhookPayloadError("Payload must be a JSON object")
    if "alerts" not in payload:
        raise WebhookPayloadError("Missing required 'alerts' field")
    return payload


def _promote_signals_to_incidents(incident_store: IncidentStore, runs_dir: Path, now: datetime | None = None) -> WebhookPromotionSummary:
    """Promote signals to incidents using the promotion service."""
    from .incident_alert_promotion import AlertIncidentPromotionResult, promote_alert_signals_to_incidents
    try:
        result: AlertIncidentPromotionResult = promote_alert_signals_to_incidents(
            incident_store=incident_store, runs_dir=runs_dir, now=now)
        return WebhookPromotionSummary(
            enabled=True,
            scanned_signal_count=result.scanned_signal_count,
            firing_signal_count=result.firing_signal_count,
            resolved_signal_count=result.resolved_signal_count,
            opened_incident_count=result.opened_incident_count,
            updated_incident_count=result.updated_incident_count,
            skipped_duplicate_count=result.skipped_duplicate_count,
            skipped_resolved_without_open_incident_count=result.skipped_resolved_without_open_incident_count,
            error_count=result.error_count,
        )
    except Exception:
        logger.exception("Error during signal promotion")
        return WebhookPromotionSummary(enabled=True, error_count=1)


def process_webhook(payload: dict[str, Any], config: AlertmanagerWebhookConfig, root: Path,
                    received_at: datetime | None = None, incident_store: IncidentStore | None = None) -> WebhookResponse:
    """Process an Alertmanager webhook payload: normalize, write artifacts, optionally promote."""
    if received_at is None:
        received_at = datetime.now(UTC)
    errors: list[WebhookError] = []
    normalized_signals: list[AlertSignal] = []

    # Write raw payload artifact
    raw_result = write_raw_payload_artifact(root=root, payload=payload, source_instance=config.source_instance, received_at=received_at)
    raw_payload_artifact_id: str | None = raw_result.artifact_id if raw_result.success else None
    if not raw_result.success:
        errors.append(WebhookError(field="raw_payload", message=raw_result.error or "Failed to write raw payload"))

    # Normalize payload
    normalization_result = normalize_alertmanager_payload(payload, source_instance=config.source_instance, received_at=received_at)
    for err in normalization_result.errors:
        errors.append(WebhookError(field=err.field, message=err.message))
    normalized_signals = list(normalization_result.signals)

    # Write signals idempotently
    stored_count = duplicate_count = 0
    for signal in normalized_signals:
        signal_with_ref = AlertSignal(
            signal_id=signal.signal_id, source_type=signal.source_type, source_instance=signal.source_instance,
            status=signal.status, alertname=signal.alertname, external_fingerprint=signal.external_fingerprint,
            group_key=signal.group_key, receiver=signal.receiver, severity=signal.severity,
            labels=signal.labels, annotations=signal.annotations, starts_at=signal.starts_at, ends_at=signal.ends_at,
            received_at=signal.received_at, generator_url=signal.generator_url, external_url=signal.external_url,
            raw_payload_artifact_id=raw_payload_artifact_id, truncation=signal.truncation,
        )
        write_result = write_alert_signal_artifact(root=root, signal=signal_with_ref, raw_payload_artifact_id=raw_payload_artifact_id, received_at=received_at)
        if write_result.is_duplicate:
            duplicate_count += 1
        elif write_result.success:
            stored_count += 1
        else:
            errors.append(WebhookError(field=f"signal:{signal.alertname}", message=write_result.error or "Failed to write signal"))

    # Auto-promote if enabled
    promotion_summary: WebhookPromotionSummary | None = None
    if config.auto_promote and incident_store is not None and normalized_signals:
        promotion_summary = _promote_signals_to_incidents(incident_store=incident_store, runs_dir=root, now=received_at)

    accepted = bool(normalized_signals) and all(e.field == "alerts" for e in errors) or not normalized_signals and not errors
    return WebhookResponse(
        accepted=accepted, source_instance=config.source_instance,
        received_alert_count=len(payload.get("alerts", [])), normalized_signal_count=len(normalized_signals),
        stored_signal_count=stored_count, duplicate_signal_count=duplicate_count,
        error_count=len(errors), errors=errors, raw_payload_artifact_id=raw_payload_artifact_id,
        promotion=promotion_summary,
    )


def handle_alertmanager_webhook(auth_header: str | None, raw_body: bytes, config: AlertmanagerWebhookConfig,
                                  root: Path, incident_store: IncidentStore | None = None) -> tuple[WebhookResponse, int]:
    """Handle an incoming Alertmanager webhook request."""
    if not config.enabled:
        raise WebhookDisabledError("Webhook endpoint is disabled")
    if config.requires_auth():
        validate_bearer_token(auth_header, config.bearer_token)
    payload = parse_payload(raw_body, config.max_payload_bytes)
    received_at = datetime.now(UTC)
    response = process_webhook(payload=payload, config=config, root=root, received_at=received_at, incident_store=incident_store)
    if response.normalized_signal_count == 0 and response.error_count > 0:
        status_code = 400
    elif not response.accepted:
        status_code = 400
    else:
        status_code = 200
    return response, status_code


__all__ = [
    "WebhookError", "WebhookPromotionSummary", "WebhookResponse",
    "WebhookAuthError", "WebhookPayloadError", "WebhookDisabledError",
    "validate_bearer_token", "validate_payload_size", "parse_payload",
    "process_webhook", "handle_alertmanager_webhook",
]
