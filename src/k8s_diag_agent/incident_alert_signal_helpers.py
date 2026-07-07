"""Helper functions for alert signal processing.

This module provides pure helper functions for serializing, deserializing,
and bounding alert signals. These are extracted from the original
incident_alert_signal module to reduce line count while maintaining
the public API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from .incident_alert_signal_contract import (
    MAX_ANNOTATION_COUNT,
    MAX_KEY_LENGTH,
    MAX_LABEL_COUNT,
    MAX_TOTAL_ANNOTATION_BYTES,
    MAX_TOTAL_LABEL_BYTES,
    MAX_VALUE_LENGTH,
    AlertSignal,
    AlertSourceType,
    AlertStatus,
    TruncationMetadata,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Serialization Helpers
# =============================================================================

def _enum_value(value: str | Enum) -> str:
    """Coerce an enum member or string to a plain string for serialization.

    This handles the case where the value might already be a plain string
    (e.g., from deserialization or test fixtures) or an enum member that
    requires .value extraction.

    Args:
        value: Either an Enum member or a plain string

    Returns:
        Plain string representation suitable for JSON serialization
    """
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


# =============================================================================
# Datetime Parsing
# =============================================================================

def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse datetime from string or return as-is."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = f"{value[:-1]}+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


# =============================================================================
# Signal ID Generation
# =============================================================================

def _generate_signal_id() -> str:
    """Generate a new signal ID (UUIDv7-like)."""
    from .identity.artifact import new_artifact_id
    return str(new_artifact_id())


# =============================================================================
# AlertSignal Serialization
# =============================================================================

def alert_signal_to_dict(signal: AlertSignal) -> dict[str, Any]:
    """Serialize an AlertSignal to a dict.

    Args:
        signal: The AlertSignal to serialize

    Returns:
        Dict representation suitable for JSON serialization
    """
    result: dict[str, Any] = {
        "signal_id": signal.signal_id,
        "source_type": _enum_value(signal.source_type),
        "source_instance": signal.source_instance,
        "external_fingerprint": signal.external_fingerprint,
        "group_key": signal.group_key,
        "receiver": signal.receiver,
        "status": _enum_value(signal.status),
        "alertname": signal.alertname,
        "severity": signal.severity,
        "labels": dict(signal.labels),
        "annotations": dict(signal.annotations),
        "starts_at": signal.starts_at.isoformat() if signal.starts_at else None,
        "ends_at": signal.ends_at.isoformat() if signal.ends_at else None,
        "received_at": signal.received_at.isoformat(),
        "generator_url": signal.generator_url,
        "external_url": signal.external_url,
        "raw_payload_artifact_id": signal.raw_payload_artifact_id,
    }
    if signal.truncation is not None:
        result["truncation"] = signal.truncation.to_dict()
    return result


def alert_signal_from_dict(data: dict[str, Any]) -> AlertSignal:
    """Deserialize an AlertSignal from a dict.

    Args:
        data: Dict representation of an AlertSignal

    Returns:
        Deserialized AlertSignal instance
    """
    starts_at = None
    if data.get("starts_at"):
        starts_at = _parse_datetime(data["starts_at"])

    ends_at = None
    if data.get("ends_at"):
        ends_at = _parse_datetime(data["ends_at"])

    received_at: datetime | None = datetime.now(UTC)
    if data.get("received_at"):
        received_at = _parse_datetime(data["received_at"])
    if received_at is None:
        received_at = datetime.now(UTC)

    labels_raw = data.get("labels", {})
    if isinstance(labels_raw, dict):
        labels = tuple(sorted((str(k), str(v)) for k, v in labels_raw.items()))
    else:
        labels = tuple(data.get("labels", []))

    annotations_raw = data.get("annotations", {})
    if isinstance(annotations_raw, dict):
        annotations = tuple(sorted((str(k), str(v)) for k, v in annotations_raw.items()))
    else:
        annotations = tuple(data.get("annotations", []))

    truncation = None
    if data.get("truncation"):
        t = data["truncation"]
        truncation = TruncationMetadata(
            truncated_labels=t.get("truncated_labels", 0),
            truncated_annotations=t.get("truncated_annotations", 0),
            label_value_truncated_keys=tuple(t.get("label_value_truncated_keys", [])),
            annotation_value_truncated_keys=tuple(t.get("annotation_value_truncated_keys", [])),
            label_bytes_exceeded=t.get("label_bytes_exceeded", False),
            annotation_bytes_exceeded=t.get("annotation_bytes_exceeded", False),
        )

    return AlertSignal(
        signal_id=str(data["signal_id"]),
        source_type=AlertSourceType(data.get("source_type", "alertmanager")),
        source_instance=str(data["source_instance"]),
        external_fingerprint=data.get("external_fingerprint"),
        group_key=data.get("group_key"),
        receiver=data.get("receiver"),
        status=AlertStatus(data.get("status", "firing")),
        alertname=str(data.get("alertname", "unknown")),
        severity=data.get("severity"),
        labels=labels,
        annotations=annotations,
        starts_at=starts_at,
        ends_at=ends_at,
        received_at=received_at,
        generator_url=data.get("generator_url"),
        external_url=data.get("external_url"),
        raw_payload_artifact_id=data.get("raw_payload_artifact_id"),
        truncation=truncation,
    )


# =============================================================================
# Label/Annotation Bounding Utilities
# =============================================================================

def bound_labels(
    labels: dict[str, Any],
    *,
    max_count: int = MAX_LABEL_COUNT,
    max_key_length: int = MAX_KEY_LENGTH,
    max_value_length: int = MAX_VALUE_LENGTH,
    max_total_bytes: int = MAX_TOTAL_LABEL_BYTES,
) -> tuple[tuple[tuple[str, str], ...], TruncationMetadata]:
    """Bound a labels dict to safe limits.

    Args:
        labels: Raw labels dict from Alertmanager payload
        max_count: Maximum number of labels to retain
        max_key_length: Maximum length for label keys
        max_value_length: Maximum length for label values
        max_total_bytes: Maximum total serialized bytes

    Returns:
        Tuple of (sorted bounded labels, truncation metadata)
    """
    metadata = TruncationMetadata()
    result: list[tuple[str, str]] = []
    total_bytes = 0
    truncated_value_keys: list[str] = []

    # Sort for deterministic ordering
    for key, value in sorted(labels.items()):
        key_str = str(key)
        value_str = str(value)

        # Skip empty keys
        if not key_str:
            continue

        # Truncate key if too long
        if len(key_str) > max_key_length:
            key_str = key_str[:max_key_length - 3] + "..."

        # Truncate value if too long
        value_truncated = False
        if len(value_str) > max_value_length:
            value_str = value_str[:max_value_length - 3] + "..."
            value_truncated = True
            truncated_value_keys.append(key_str)

        # Check total count
        if len(result) >= max_count:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels + 1,
                truncated_annotations=metadata.truncated_annotations,
                label_value_truncated_keys=tuple(metadata.label_value_truncated_keys),
                annotation_value_truncated_keys=metadata.annotation_value_truncated_keys,
                label_bytes_exceeded=metadata.label_bytes_exceeded,
                annotation_bytes_exceeded=metadata.annotation_bytes_exceeded,
            )
            continue

        # Check total bytes
        item_bytes = len(key_str) + len(value_str)
        if total_bytes + item_bytes > max_total_bytes:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels,
                truncated_annotations=metadata.truncated_annotations,
                label_value_truncated_keys=tuple(metadata.label_value_truncated_keys),
                annotation_value_truncated_keys=metadata.annotation_value_truncated_keys,
                label_bytes_exceeded=True,
                annotation_bytes_exceeded=metadata.annotation_bytes_exceeded,
            )
            break

        result.append((key_str, value_str))
        total_bytes += item_bytes

        if value_truncated:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels,
                truncated_annotations=metadata.truncated_annotations,
                label_value_truncated_keys=metadata.label_value_truncated_keys + (key_str,),
                annotation_value_truncated_keys=metadata.annotation_value_truncated_keys,
                label_bytes_exceeded=metadata.label_bytes_exceeded,
                annotation_bytes_exceeded=metadata.annotation_bytes_exceeded,
            )

    return tuple(result), metadata


def bound_annotations(
    annotations: dict[str, Any],
    *,
    max_count: int = MAX_ANNOTATION_COUNT,
    max_key_length: int = MAX_KEY_LENGTH,
    max_value_length: int = MAX_VALUE_LENGTH,
    max_total_bytes: int = MAX_TOTAL_ANNOTATION_BYTES,
) -> tuple[tuple[tuple[str, str], ...], TruncationMetadata]:
    """Bound an annotations dict to safe limits.

    Args:
        annotations: Raw annotations dict from Alertmanager payload
        max_count: Maximum number of annotations to retain
        max_key_length: Maximum length for annotation keys
        max_value_length: Maximum length for annotation values
        max_total_bytes: Maximum total serialized bytes

    Returns:
        Tuple of (sorted bounded annotations, truncation metadata)
    """
    metadata = TruncationMetadata()
    result: list[tuple[str, str]] = []
    total_bytes = 0
    truncated_value_keys: list[str] = []

    # Sort for deterministic ordering
    for key, value in sorted(annotations.items()):
        key_str = str(key)
        value_str = str(value)

        # Skip empty keys
        if not key_str:
            continue

        # Truncate key if too long
        if len(key_str) > max_key_length:
            key_str = key_str[:max_key_length - 3] + "..."

        # Truncate value if too long
        value_truncated = False
        if len(value_str) > max_value_length:
            value_str = value_str[:max_value_length - 3] + "..."
            value_truncated = True
            truncated_value_keys.append(key_str)

        # Check total count
        if len(result) >= max_count:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels,
                truncated_annotations=metadata.truncated_annotations + 1,
                label_value_truncated_keys=metadata.label_value_truncated_keys,
                annotation_value_truncated_keys=tuple(metadata.annotation_value_truncated_keys),
                label_bytes_exceeded=metadata.label_bytes_exceeded,
                annotation_bytes_exceeded=metadata.annotation_bytes_exceeded,
            )
            continue

        # Check total bytes
        item_bytes = len(key_str) + len(value_str)
        if total_bytes + item_bytes > max_total_bytes:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels,
                truncated_annotations=metadata.truncated_annotations,
                label_value_truncated_keys=metadata.label_value_truncated_keys,
                annotation_value_truncated_keys=tuple(metadata.annotation_value_truncated_keys),
                label_bytes_exceeded=metadata.label_bytes_exceeded,
                annotation_bytes_exceeded=True,
            )
            break

        result.append((key_str, value_str))
        total_bytes += item_bytes

        if value_truncated:
            metadata = TruncationMetadata(
                truncated_labels=metadata.truncated_labels,
                truncated_annotations=metadata.truncated_annotations,
                label_value_truncated_keys=metadata.label_value_truncated_keys,
                annotation_value_truncated_keys=metadata.annotation_value_truncated_keys + (key_str,),
                label_bytes_exceeded=metadata.label_bytes_exceeded,
                annotation_bytes_exceeded=metadata.annotation_bytes_exceeded,
            )

    return tuple(result), metadata


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Constants (re-exported from contract for convenience)
    "MAX_LABEL_COUNT",
    "MAX_ANNOTATION_COUNT",
    "MAX_KEY_LENGTH",
    "MAX_VALUE_LENGTH",
    "MAX_TOTAL_LABEL_BYTES",
    "MAX_TOTAL_ANNOTATION_BYTES",
    # Helper functions
    "_enum_value",
    "_parse_datetime",
    "_generate_signal_id",
    # Serialization
    "alert_signal_to_dict",
    "alert_signal_from_dict",
    # Bounding utilities
    "bound_labels",
    "bound_annotations",
]
