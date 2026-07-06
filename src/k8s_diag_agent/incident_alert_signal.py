"""Normalized alert signal domain model for Alertmanager and vmalert ingestion.

This module provides the internal contract for representing alert signals
as distinct from incidents. Alerts are signals that may open, update,
correlate with, or enrich an incident.

Design principles:
- Alerts are not incidents: they are signals that may influence incidents
- Stable internal representation independent of provider payload shapes
- Bounded fields to prevent unbounded artifact growth
- Pure domain model: no I/O, no external calls

Non-goals for this module:
- Alert-to-incident promotion (handled by future ACT)
- Webhook endpoint implementation (handled by future ACT)
- LLM-based classification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# =============================================================================
# Bounds Constants
# =============================================================================

MAX_LABEL_COUNT = 100
MAX_ANNOTATION_COUNT = 50
MAX_KEY_LENGTH = 128
MAX_VALUE_LENGTH = 512
MAX_TOTAL_LABEL_BYTES = 16 * 1024  # 16 KB
MAX_TOTAL_ANNOTATION_BYTES = 32 * 1024  # 32 KB


# =============================================================================
# Source Types
# =============================================================================

class AlertSourceType(StrEnum):
    """Alert source type enumeration.

    Represents the origin system of the alert signal.
    """
    ALERTMANAGER = "alertmanager"
    VMALERT = "vmalert"


# =============================================================================
# Alert Status
# =============================================================================

class AlertStatus(StrEnum):
    """Alert status from Alertmanager notification.

    Maps directly to Alertmanager's firing/resolved states.
    """
    FIRING = "firing"
    RESOLVED = "resolved"


# =============================================================================
# Truncation Metadata
# =============================================================================

@dataclass(frozen=True)
class TruncationMetadata:
    """Metadata about label/annotation truncation.

    Records what was truncated and by how much to aid debugging.
    """
    truncated_labels: int = 0  # Number of labels dropped
    truncated_annotations: int = 0  # Number of annotations dropped
    label_value_truncated_keys: tuple[str, ...] = field(default_factory=tuple)
    annotation_value_truncated_keys: tuple[str, ...] = field(default_factory=tuple)
    label_bytes_exceeded: bool = False
    annotation_bytes_exceeded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "truncated_labels": self.truncated_labels,
            "truncated_annotations": self.truncated_annotations,
            "label_value_truncated_keys": list(self.label_value_truncated_keys),
            "annotation_value_truncated_keys": list(self.annotation_value_truncated_keys),
            "label_bytes_exceeded": self.label_bytes_exceeded,
            "annotation_bytes_exceeded": self.annotation_bytes_exceeded,
        }


# =============================================================================
# Alert Signal Model
# =============================================================================

@dataclass(frozen=True)
class AlertSignal:
    """Normalized alert signal representing an external alert.

    This is the internal contract for Alertmanager and vmalert signals.
    It is distinct from IncidentSignal (kubernetes-derived) and from
    Incident records (the aggregate root for incident management).

    Key invariants:
    - signal_id: stable internal identity (UUID-based)
    - source_type: always "alertmanager" or "vmalert"
    - external_fingerprint: from Alertmanager, may be absent
    - labels/annotations: always bounded per truncation policy
    - No incident promotion in this model
    """
    # Required fields (no defaults)
    signal_id: str  # UUID-based internal identity
    source_type: AlertSourceType  # "alertmanager" or "vmalert"
    source_instance: str  # Identifying instance (e.g., endpoint URL)
    status: AlertStatus  # firing or resolved
    alertname: str  # Derived from labels["alertname"]

    # Optional fields (with defaults)
    external_fingerprint: str | None = None  # From Alertmanager fingerprint field
    group_key: str | None = None  # Alertmanager group key
    receiver: str | None = None  # Alertmanager receiver name
    severity: str | None = None  # Derived from labels["severity"] if present
    labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # Sorted, bounded
    annotations: tuple[tuple[str, str], ...] = field(default_factory=tuple)  # Sorted, bounded
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    generator_url: str | None = None
    external_url: str | None = None
    raw_payload_artifact_id: str | None = None  # Reference to raw payload artifact
    truncation: TruncationMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "signal_id": self.signal_id,
            "source_type": self.source_type.value,
            "source_instance": self.source_instance,
            "external_fingerprint": self.external_fingerprint,
            "group_key": self.group_key,
            "receiver": self.receiver,
            "status": self.status.value,
            "alertname": self.alertname,
            "severity": self.severity,
            "labels": dict(self.labels),
            "annotations": dict(self.annotations),
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "received_at": self.received_at.isoformat(),
            "generator_url": self.generator_url,
            "external_url": self.external_url,
            "raw_payload_artifact_id": self.raw_payload_artifact_id,
        }
        if self.truncation is not None:
            result["truncation"] = self.truncation.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertSignal:
        """Deserialize from dict."""
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

        return cls(
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
# Alert Correlation Hints
# =============================================================================

@dataclass(frozen=True)
class AlertCorrelationHints:
    """Hints for correlating alerts to incidents or other alerts.

    Used by future ACTs for alert-to-incident promotion and alert deduplication.
    """
    # Core correlation fields
    source_instance: str
    alertname: str
    severity: str | None = None

    # Label subset for fuzzy matching
    stable_labels: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    # Time window hint (seconds)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    # External references
    external_fingerprint: str | None = None
    generator_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_instance": self.source_instance,
            "alertname": self.alertname,
            "severity": self.severity,
            "stable_labels": dict(self.stable_labels),
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "external_fingerprint": self.external_fingerprint,
            "generator_url": self.generator_url,
        }


# =============================================================================
# Helper Functions
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


def _generate_signal_id() -> str:
    """Generate a new signal ID (UUIDv7-like)."""
    from .identity.artifact import new_artifact_id
    return str(new_artifact_id())


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
    # Bounds constants
    "MAX_LABEL_COUNT",
    "MAX_ANNOTATION_COUNT",
    "MAX_KEY_LENGTH",
    "MAX_VALUE_LENGTH",
    "MAX_TOTAL_LABEL_BYTES",
    "MAX_TOTAL_ANNOTATION_BYTES",
    # Enums
    "AlertSourceType",
    "AlertStatus",
    # Models
    "AlertSignal",
    "AlertCorrelationHints",
    "TruncationMetadata",
    # Utilities
    "bound_labels",
    "bound_annotations",
]
