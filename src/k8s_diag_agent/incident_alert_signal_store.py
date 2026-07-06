"""Alert signal store for persisting normalized Alertmanager webhook signals.

This module provides functions for:
- Writing raw Alertmanager webhook payloads to bounded artifacts
- Writing normalized alert signals to idempotent artifacts
- Checking for existing signals (idempotency)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .identity.artifact import new_artifact_id
from .incident_alert_signal import AlertCorrelationHints, AlertSignal
from .incident_alert_signal_identity import (
    alert_signal_correlation_hints,
    alert_signal_identity,
)

# =============================================================================
# Constants
# =============================================================================

# Schema version for raw payload artifacts
RAW_PAYLOAD_SCHEMA_VERSION = "k9b.alertmanager.webhook.raw.v1"

# Schema version for alert signal artifacts
ALERT_SIGNAL_SCHEMA_VERSION = "k9b.alert_signal.v1"

# Base subdirectory for external analysis artifacts
EXTERNAL_ANALYSIS_SUBDIR = "external-analysis"

# Subdirectory for alert signals (both signal and raw payload artifacts)
ALERT_SIGNALS_SUBDIR = "alert-signals"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class RawPayloadArtifact:
    """Raw Alertmanager webhook payload artifact.

    This represents the bounded/sanitized raw payload before normalization.
    Authorization headers and other sensitive headers are excluded.
    """
    schema_version: str = RAW_PAYLOAD_SCHEMA_VERSION
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_instance: str = ""
    payload_sha256: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "received_at": self.received_at.isoformat(),
            "source_instance": self.source_instance,
            "payload_sha256": self.payload_sha256,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawPayloadArtifact:
        received_at = datetime.now(UTC)
        if data.get("received_at"):
            try:
                received_at = datetime.fromisoformat(
                    data["received_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        return cls(
            schema_version=data.get("schema_version", RAW_PAYLOAD_SCHEMA_VERSION),
            received_at=received_at,
            source_instance=data.get("source_instance", ""),
            payload_sha256=data.get("payload_sha256", ""),
            payload=data.get("payload", {}),
        )


@dataclass
class AlertSignalArtifact:
    """Normalized alert signal artifact.

    This represents a persisted alert signal with correlation hints
    and reference to the raw payload artifact.
    """
    schema_version: str = ALERT_SIGNAL_SCHEMA_VERSION
    identity: str = ""
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    signal: AlertSignal | None = None
    correlation_hints: AlertCorrelationHints | None = None
    raw_payload_artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity,
            "received_at": self.received_at.isoformat(),
            "signal": self.signal.to_dict() if self.signal else {},
            "correlation_hints": (
                self.correlation_hints.to_dict() if self.correlation_hints else {}
            ),
            "raw_payload_artifact_id": self.raw_payload_artifact_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertSignalArtifact:
        received_at = datetime.now(UTC)
        if data.get("received_at"):
            try:
                received_at = datetime.fromisoformat(
                    data["received_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        signal = None
        if data.get("signal"):
            from .incident_alert_signal import AlertSignal

            signal = AlertSignal.from_dict(data["signal"])

        correlation_hints = None
        if data.get("correlation_hints"):
            from .incident_alert_signal import AlertCorrelationHints

            correlation_hints = AlertCorrelationHints(
                source_instance=data["correlation_hints"].get("source_instance", ""),
                alertname=data["correlation_hints"].get("alertname", ""),
                severity=data["correlation_hints"].get("severity"),
            )

        return cls(
            schema_version=data.get("schema_version", ALERT_SIGNAL_SCHEMA_VERSION),
            identity=data.get("identity", ""),
            received_at=received_at,
            signal=signal,
            correlation_hints=correlation_hints,
            raw_payload_artifact_id=data.get("raw_payload_artifact_id"),
        )


# =============================================================================
# Store Result Types
# =============================================================================


@dataclass
class RawPayloadWriteResult:
    """Result of writing a raw payload artifact."""
    success: bool
    artifact_id: str | None = None
    artifact_path: Path | None = None
    error: str | None = None


@dataclass
class SignalWriteResult:
    """Result of writing an alert signal artifact."""
    success: bool
    identity: str | None = None
    is_duplicate: bool = False
    artifact_id: str | None = None
    artifact_path: Path | None = None
    error: str | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _compute_payload_sha256(payload: dict[str, Any]) -> str:
    """Compute SHA256 hash of payload for integrity checking."""
    # Use stable JSON serialization
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


def _alert_signal_artifact_path(
    root: Path,
    identity: str,
) -> Path:
    """Compute the artifact path for an alert signal.

    Args:
        root: The runs directory root
        identity: The alert signal identity

    Returns:
        Path to the alert signal artifact: runs_dir/external-analysis/alert-signals/alert-signal-{identity}.json
    """
    subdir = root / EXTERNAL_ANALYSIS_SUBDIR / ALERT_SIGNALS_SUBDIR
    return subdir / f"alert-signal-{identity}.json"


def _raw_payload_artifact_path(
    root: Path,
    artifact_id: str,
) -> Path:
    """Compute the artifact path for a raw payload.

    Args:
        root: The runs directory root
        artifact_id: The artifact ID

    Returns:
        Path to the raw payload artifact: runs_dir/external-analysis/alert-signals/alertmanager-raw-{artifact_id}.json
    """
    subdir = root / EXTERNAL_ANALYSIS_SUBDIR / ALERT_SIGNALS_SUBDIR
    return subdir / f"alertmanager-raw-{artifact_id}.json"


# =============================================================================
# Store Functions
# =============================================================================


def write_raw_payload_artifact(
    root: Path,
    payload: dict[str, Any],
    source_instance: str,
    received_at: datetime | None = None,
) -> RawPayloadWriteResult:
    """Write a bounded raw Alertmanager payload artifact.

    This writes the sanitized raw payload before normalization. Authorization
    headers and other sensitive data are excluded from the payload.

    Args:
        root: The runs directory root
        payload: The Alertmanager webhook payload
        source_instance: The source instance identifier
        received_at: When the payload was received (defaults to now)

    Returns:
        RawPayloadWriteResult with success status and artifact info
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    # Compute payload hash
    payload_sha256 = _compute_payload_sha256(payload)

    # Generate artifact ID
    artifact_id = new_artifact_id()

    # Create artifact
    artifact = RawPayloadArtifact(
        schema_version=RAW_PAYLOAD_SCHEMA_VERSION,
        received_at=received_at,
        source_instance=source_instance,
        payload_sha256=payload_sha256,
        payload=payload,
    )

    # Write artifact
    artifact_path = _raw_payload_artifact_path(root, artifact_id)

    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact.to_dict(), indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return RawPayloadWriteResult(
            success=False,
            artifact_id=artifact_id,
            error=f"Failed to write raw payload artifact: {e}",
        )

    return RawPayloadWriteResult(
        success=True,
        artifact_id=artifact_id,
        artifact_path=artifact_path,
    )


def check_signal_exists(
    root: Path,
    signal: AlertSignal,
) -> bool:
    """Check if an alert signal artifact already exists (idempotency check).

    Uses alert_signal_identity() to compute the stable identity of the signal.

    Args:
        root: The runs directory root
        signal: The alert signal to check

    Returns:
        True if an artifact with this identity already exists
    """
    identity = alert_signal_identity(signal)
    artifact_path = _alert_signal_artifact_path(root, identity)
    return artifact_path.exists()


def write_alert_signal_artifact(
    root: Path,
    signal: AlertSignal,
    raw_payload_artifact_id: str | None = None,
    received_at: datetime | None = None,
) -> SignalWriteResult:
    """Write a normalized alert signal to an idempotent artifact.

    The artifact is keyed by alert_signal_identity(signal), ensuring that
    duplicate webhook deliveries do not create duplicate artifacts.

    Args:
        root: The runs directory root
        signal: The normalized alert signal
        raw_payload_artifact_id: Optional reference to the raw payload artifact
        received_at: When the signal was received (defaults to now)

    Returns:
        SignalWriteResult with success status, identity, and artifact info
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    # Compute identity for idempotency
    identity = alert_signal_identity(signal)

    # Check for existing artifact
    artifact_path = _alert_signal_artifact_path(root, identity)
    if artifact_path.exists():
        return SignalWriteResult(
            success=True,
            identity=identity,
            is_duplicate=True,
            artifact_path=artifact_path,
        )

    # Compute correlation hints
    correlation_hints = alert_signal_correlation_hints(signal)

    # Create artifact
    artifact = AlertSignalArtifact(
        schema_version=ALERT_SIGNAL_SCHEMA_VERSION,
        identity=identity,
        received_at=received_at,
        signal=signal,
        correlation_hints=correlation_hints,
        raw_payload_artifact_id=raw_payload_artifact_id,
    )

    # Write artifact
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact.to_dict(), indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        return SignalWriteResult(
            success=False,
            identity=identity,
            error=f"Failed to write alert signal artifact: {e}",
        )

    return SignalWriteResult(
        success=True,
        identity=identity,
        is_duplicate=False,
        artifact_id=identity,
        artifact_path=artifact_path,
    )


def read_alert_signal_artifact(
    root: Path,
    identity: str,
) -> AlertSignalArtifact | None:
    """Read an alert signal artifact by identity.

    Args:
        root: The runs directory root
        identity: The alert signal identity

    Returns:
        AlertSignalArtifact if found, None otherwise
    """
    artifact_path = _alert_signal_artifact_path(root, identity)
    if not artifact_path.exists():
        return None

    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        return AlertSignalArtifact.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None


__all__ = [
    # Constants
    "RAW_PAYLOAD_SCHEMA_VERSION",
    "ALERT_SIGNAL_SCHEMA_VERSION",
    "EXTERNAL_ANALYSIS_SUBDIR",
    "ALERT_SIGNALS_SUBDIR",
    # Data classes
    "RawPayloadArtifact",
    "AlertSignalArtifact",
    # Result types
    "RawPayloadWriteResult",
    "SignalWriteResult",
    # Functions
    "write_raw_payload_artifact",
    "check_signal_exists",
    "write_alert_signal_artifact",
    "read_alert_signal_artifact",
]
