"""Normalizer for Alertmanager webhook payloads into AlertSignal domain model.

This module provides the pure normalization function that maps one or more
Alertmanager webhook-style payloads into normalized AlertSignal objects.

Design principles:
- Pure function: no side effects, deterministic output for same input
- Splits grouped notifications into per-alert signals
- Preserves group-level metadata (groupKey, receiver, externalURL)
- Handles bounds enforcement for labels and annotations
- Returns validation errors for malformed payloads

Non-goals:
- Alert-to-incident promotion
- Webhook endpoint implementation
- LLM-based classification
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .identity.artifact import new_artifact_id
from .incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
    TruncationMetadata,
    bound_annotations,
    bound_labels,
)

# =============================================================================
# Validation Errors
# =============================================================================

@dataclass(frozen=True)
class NormalizationError:
    """Validation error from payload normalization."""
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass
class NormalizationResult:
    """Result of normalizing an Alertmanager payload.

    Contains either signals or validation errors.
    """
    signals: tuple[AlertSignal, ...] = field(default_factory=tuple)
    errors: tuple[NormalizationError, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """Return True if normalization succeeded."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "signals": [s.to_dict() for s in self.signals],
            "errors": [e.to_dict() for e in self.errors],
            "is_valid": self.is_valid,
        }


# =============================================================================
# Constants for Source Type Detection
# =============================================================================

# Label that explicitly indicates vmalert source
VMALERT_SOURCE_LABEL = "k9b.dev/source_type"
VMALERT_SOURCE_VALUE = "vmalert"


# =============================================================================
# Source Type Inference
# =============================================================================

def infer_source_type(labels: Mapping[str, Any]) -> AlertSourceType:
    """Infer alert source type from labels.

    Current inference rules:
    1. Explicit k9b.dev/source_type=vmalert label wins
    2. Otherwise default to alertmanager

    Args:
        labels: Alert labels dict

    Returns:
        AlertSourceType.ALERTMANAGER or AlertSourceType.VMALERT
    """
    source_label = labels.get(VMALERT_SOURCE_LABEL) or labels.get("source_type")
    if isinstance(source_label, str) and source_label.lower() == VMALERT_SOURCE_VALUE.lower():
        return AlertSourceType.VMALERT
    return AlertSourceType.ALERTMANAGER


# =============================================================================
# Datetime Parsing
# =============================================================================

def _parse_rfc3339_datetime(value: str | None) -> datetime | None:
    """Parse RFC3339 datetime string to datetime.

    Handles:
    - ISO8601 with Z suffix
    - ISO8601 with +00:00 offset
    - Various datetime formats from Alertmanager

    Args:
        value: Datetime string or None

    Returns:
        Parsed datetime or None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        return None

    # Handle Z suffix
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    # Try common formats
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


# =============================================================================
# Single Alert Normalization
# =============================================================================

def _normalize_single_alert(
    alert: Mapping[str, Any],
    *,
    source_type: AlertSourceType,
    source_instance: str,
    group_key: str | None,
    receiver: str | None,
    external_url: str | None,
    received_at: datetime,
    raw_payload_artifact_id: str | None,
) -> tuple[AlertSignal, list[NormalizationError]]:
    """Normalize a single alert from Alertmanager payload.

    Args:
        alert: Single alert dict from Alertmanager webhook payload
        source_type: Inferred source type
        source_instance: Source instance identifier
        group_key: Alertmanager group key
        receiver: Alertmanager receiver name
        external_url: Alertmanager external URL
        received_at: When the payload was received
        raw_payload_artifact_id: Optional reference to raw payload

    Returns:
        Tuple of (AlertSignal, list of errors)
    """
    errors: list[NormalizationError] = []

    # Extract labels
    raw_labels: dict[str, Any] = {}
    if isinstance(alert.get("labels"), Mapping):
        raw_labels = dict(alert["labels"])

    # Extract annotations
    raw_annotations: dict[str, Any] = {}
    if isinstance(alert.get("annotations"), Mapping):
        raw_annotations = dict(alert["annotations"])

    # Bound labels and annotations
    bounded_labels, label_truncation = bound_labels(raw_labels)
    bounded_annotations, annotation_truncation = bound_annotations(raw_annotations)

    # Combine truncation metadata
    has_truncation = (
        label_truncation.truncated_labels > 0
        or annotation_truncation.truncated_annotations > 0
        or label_truncation.label_value_truncated_keys
        or annotation_truncation.annotation_value_truncated_keys
        or label_truncation.label_bytes_exceeded
        or annotation_truncation.annotation_bytes_exceeded
    )
    truncation_metadata: TruncationMetadata | None = None
    if has_truncation:
        truncation_metadata = TruncationMetadata(
            truncated_labels=label_truncation.truncated_labels,
            truncated_annotations=annotation_truncation.truncated_annotations,
            label_value_truncated_keys=label_truncation.label_value_truncated_keys,
            annotation_value_truncated_keys=annotation_truncation.annotation_value_truncated_keys,
            label_bytes_exceeded=label_truncation.label_bytes_exceeded,
            annotation_bytes_exceeded=annotation_truncation.annotation_bytes_exceeded,
        )

    # Extract alertname (required)
    alertname = raw_labels.get("alertname")
    if not alertname:
        errors.append(NormalizationError(
            field="alerts[].labels.alertname",
            message="Missing required alertname label",
        ))
        alertname = "unknown"
    alertname = str(alertname)

    # Extract severity (optional)
    severity = raw_labels.get("severity")
    if severity is not None:
        severity = str(severity)

    # Extract status
    status_str = alert.get("status", "firing")
    if status_str not in ("firing", "resolved"):
        errors.append(NormalizationError(
            field="alerts[].status",
            message=f"Invalid status: {status_str}",
        ))
    status = AlertStatus(status_str) if status_str in ("firing", "resolved") else AlertStatus.FIRING

    # Extract fingerprint
    fingerprint = alert.get("fingerprint")
    if fingerprint is not None:
        fingerprint = str(fingerprint)

    # Extract timestamps
    starts_at = _parse_rfc3339_datetime(alert.get("startsAt")) or _parse_rfc3339_datetime(alert.get("starts_at"))
    ends_at = _parse_rfc3339_datetime(alert.get("endsAt")) or _parse_rfc3339_datetime(alert.get("ends_at"))

    # Extract URLs
    generator_url = alert.get("generatorURL") or alert.get("generator_url")
    if generator_url is not None:
        generator_url = str(generator_url)

    # Create signal
    signal = AlertSignal(
        signal_id=new_artifact_id(),
        source_type=source_type,
        source_instance=source_instance,
        external_fingerprint=fingerprint,
        group_key=group_key,
        receiver=receiver,
        status=status,
        alertname=alertname,
        severity=severity,
        labels=tuple(bounded_labels),
        annotations=tuple(bounded_annotations),
        starts_at=starts_at,
        ends_at=ends_at,
        received_at=received_at,
        generator_url=generator_url,
        external_url=external_url,
        raw_payload_artifact_id=raw_payload_artifact_id,
        truncation=truncation_metadata,
    )

    return signal, errors


# =============================================================================
# Main Normalization Function
# =============================================================================

def normalize_alertmanager_payload(
    payload: Mapping[str, object],
    *,
    source_instance: str,
    received_at: datetime | None = None,
) -> NormalizationResult:
    """Normalize an Alertmanager webhook payload into AlertSignal objects.

    This function maps one Alertmanager webhook-style payload into normalized
    alert signal objects. Grouped notifications are split into per-alert signals.

    Expected payload fields:
        - receiver: str (optional)
        - status: str (optional, "firing" or "resolved")
        - groupKey: str (optional)
        - externalURL: str (optional)
        - groupLabels: dict (optional)
        - commonLabels: dict (optional)
        - commonAnnotations: dict (optional)
        - alerts: list[dict] (required)

    Per-alert fields:
        - status: str
        - labels: dict
        - annotations: dict
        - startsAt: str
        - endsAt: str
        - generatorURL: str
        - fingerprint: str

    Args:
        payload: Alertmanager webhook payload dict
        source_instance: Identifying instance (e.g., endpoint URL or name)
        received_at: When the payload was received (defaults to now)

    Returns:
        NormalizationResult with signals and/or errors
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    errors: list[NormalizationError] = []
    signals: list[AlertSignal] = []

    # Extract group-level metadata
    receiver = payload.get("receiver")
    if receiver is not None:
        receiver = str(receiver)

    status_str = payload.get("status")
    if status_str is not None:
        status_str = str(status_str)

    group_key = payload.get("groupKey") or payload.get("group_key")
    if group_key is not None:
        group_key = str(group_key)

    external_url = payload.get("externalURL") or payload.get("external_url")
    if external_url is not None:
        external_url = str(external_url)

    # Extract alerts array
    alerts_raw = payload.get("alerts")
    if alerts_raw is None:
        return NormalizationResult(
            errors=(NormalizationError(
                field="alerts",
                message="Missing required 'alerts' field",
            ),),
        )

    if not isinstance(alerts_raw, Sequence):
        return NormalizationResult(
            errors=(NormalizationError(
                field="alerts",
                message="Alerts field must be an array",
            ),),
        )

    if isinstance(alerts_raw, Mapping):
        return NormalizationResult(
            errors=(NormalizationError(
                field="alerts",
                message="Alerts field must be an array, not an object",
            ),),
        )

    # Process each alert
    for idx, alert in enumerate(alerts_raw):
        if not isinstance(alert, Mapping):
            errors.append(NormalizationError(
                field=f"alerts[{idx}]",
                message=f"Alert at index {idx} must be an object",
            ))
            continue

        # Infer source type from labels
        alert_labels: dict[str, Any] = {}
        if isinstance(alert.get("labels"), Mapping):
            alert_labels = dict(alert["labels"])

        # Also check group labels if present
        group_labels: dict[str, Any] = {}
        group_labels_raw = payload.get("groupLabels")
        if isinstance(group_labels_raw, Mapping):
            group_labels = dict(group_labels_raw)

        # Merge labels for source type inference (alert labels take precedence)
        merged_labels = {**group_labels, **alert_labels}

        source_type = infer_source_type(merged_labels)

        # Normalize single alert
        signal, alert_errors = _normalize_single_alert(
            alert,
            source_type=source_type,
            source_instance=source_instance,
            group_key=group_key,
            receiver=receiver,
            external_url=external_url,
            received_at=received_at,
            raw_payload_artifact_id=None,
        )

        signals.append(signal)

        # Prefix error fields with alert index
        for err in alert_errors:
            errors.append(NormalizationError(
                field=f"alerts[{idx}].{err.field}",
                message=err.message,
            ))

    return NormalizationResult(
        signals=tuple(signals),
        errors=tuple(errors),
    )


# =============================================================================
# Batch Normalization
# =============================================================================

def normalize_alertmanager_payloads(
    payloads: Sequence[Mapping[str, object]],
    *,
    source_instance: str,
    received_at: datetime | None = None,
) -> list[NormalizationResult]:
    """Normalize multiple Alertmanager payloads.

    Args:
        payloads: Sequence of Alertmanager webhook payloads
        source_instance: Identifying instance
        received_at: When the payloads were received (defaults to now)

    Returns:
        List of NormalizationResult, one per payload
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    results: list[NormalizationResult] = []
    for idx, payload in enumerate(payloads):
        if not isinstance(payload, Mapping):
            results.append(NormalizationResult(
                errors=(NormalizationError(
                    field=f"payload[{idx}]",
                    message=f"Payload at index {idx} must be an object",
                ),),
            ))
            continue

        result = normalize_alertmanager_payload(
            payload,
            source_instance=source_instance,
            received_at=received_at,
        )
        results.append(result)

    return results


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "NormalizationError",
    "NormalizationResult",
    "normalize_alertmanager_payload",
    "normalize_alertmanager_payloads",
    "infer_source_type",
    "VMALERT_SOURCE_LABEL",
]
