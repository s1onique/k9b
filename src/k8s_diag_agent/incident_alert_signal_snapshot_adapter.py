"""Adapter to convert Alertmanager snapshots into alert signals for incident promotion.

This module bridges the gap between:
- Alertmanager snapshot collection (external_analysis/alertmanager_snapshot.py)
- Alert signal domain model (incident_alert_signal_contract.py)
- Alert signal persistence (incident_alert_signal_store.py)
- Incident promotion (incident_alert_promotion.py)

Design principles:
- Reuse existing NormalizedAlert → AlertSignal mapping
- Use existing alert_signal_identity() for dedupe
- Use existing write functions for artifact persistence
- Non-fatal: failures are logged but do not stop the run
- Labels-based dedupe per Prometheus convention (not annotations)

Non-goals:
- Alert-to-incident promotion (handled by incident_alert_promotion.py)
- Webhook endpoint implementation
- LLM-based classification
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)
from .incident_alert_signal import (
    AlertSignal,
    AlertSourceType,
    AlertStatus,
)
from .incident_alert_signal_identity import alert_signal_identity
from .incident_alert_signal_store import (
    write_alert_signal_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Adapter Result Types
# =============================================================================


@dataclass(frozen=True)
class AlertSignalAdapterResult:
    """Result of adapting Alertmanager snapshot to alert signals."""

    # Counts
    total_alerts: int = 0
    firing_signals_count: int = 0
    resolved_signals_count: int = 0
    skipped_count: int = 0

    # Artifact results
    signals_written: int = 0
    signals_skipped_duplicates: int = 0
    signals_failed: int = 0

    # Errors
    errors: tuple[str, ...] = ()

    @property
    def has_signals(self) -> bool:
        """Return True if any signals were written."""
        return self.signals_written > 0

    @property
    def has_errors(self) -> bool:
        """Return True if any errors occurred."""
        return len(self.errors) > 0


# =============================================================================
# Adapter Functions
# =============================================================================


def adapt_snapshot_to_alert_signals(
    snapshot: AlertmanagerSnapshot,
    source_instance: str,
    received_at: datetime | None = None,
    raw_payload_artifact_id: str | None = None,
) -> tuple[tuple[AlertSignal, ...], AlertSignalAdapterResult]:
    """Adapt an Alertmanager snapshot into AlertSignal objects.

    This function converts NormalizedAlert objects from the Alertmanager snapshot
    into the internal AlertSignal domain model, ready for persistence and promotion.

    Alert state mapping:
    - Alertmanager "active" state → AlertStatus.FIRING
    - Alertmanager "suppressed" state → skipped (silenced/inhibited already filtered)
    - Alertmanager "unprocessed" state → skipped
    - All other states → FIRING (conservative)

    Args:
        snapshot: The Alertmanager snapshot with normalized alerts
        source_instance: Canonical Alertmanager source ID (not alias URL)
        received_at: When the snapshot was captured (defaults to now)
        raw_payload_artifact_id: Optional reference to raw snapshot artifact

    Returns:
        Tuple of (AlertSignal tuple, AdapterResult)
    """
    if received_at is None:
        received_at = datetime.now(UTC)

    signals: list[AlertSignal] = []
    errors: list[str] = []

    # Check if snapshot has alerts
    if snapshot.status == AlertmanagerStatus.EMPTY:
        return (
            tuple(signals),
            AlertSignalAdapterResult(
                total_alerts=0,
                firing_signals_count=0,
                resolved_signals_count=0,
                skipped_count=0,
                signals_written=0,
                signals_skipped_duplicates=0,
                signals_failed=0,
                errors=(),
            ),
        )

    # Check for error status
    if snapshot.status not in (AlertmanagerStatus.OK, AlertmanagerStatus.EMPTY):
        error_msg = f"Snapshot has error status: {snapshot.status.value}"
        if snapshot.errors:
            error_msg = f"{error_msg}: {'; '.join(snapshot.errors)}"
        return (
            tuple(signals),
            AlertSignalAdapterResult(
                total_alerts=snapshot.alert_count,
                errors=(error_msg,),
            ),
        )

    # Track seen identities for dedupe within this snapshot
    seen_identities: set[str] = set()
    firing_count = 0
    resolved_count = 0
    skipped_count = 0

    for alert in snapshot.alerts:
        try:
            signal = _convert_normalized_alert(
                alert,
                source_instance=source_instance,
                received_at=received_at,
                raw_payload_artifact_id=raw_payload_artifact_id,
            )

            # Compute identity for dedupe
            identity = alert_signal_identity(signal)

            # Skip if already seen in this snapshot (dedupe within batch)
            if identity in seen_identities:
                _logger.debug(
                    "Skipping duplicate alert in snapshot: alertname=%s fingerprint=%s",
                    signal.alertname,
                    signal.external_fingerprint,
                )
                skipped_count += 1
                continue

            seen_identities.add(identity)
            signals.append(signal)

            if signal.status == AlertStatus.FIRING:
                firing_count += 1
            else:
                resolved_count += 1

        except Exception as exc:
            error_msg = f"Failed to convert alert {alert.fingerprint}: {exc}"
            _logger.warning(error_msg)
            errors.append(error_msg)

    return (
        tuple(signals),
        AlertSignalAdapterResult(
            total_alerts=snapshot.alert_count,
            firing_signals_count=firing_count,
            resolved_signals_count=resolved_count,
            skipped_count=skipped_count,
            signals_written=0,  # Set by caller after writing
            signals_skipped_duplicates=0,  # Set by caller
            signals_failed=len(errors),
            errors=tuple(errors),
        ),
    )


def _convert_normalized_alert(
    alert: NormalizedAlert,
    source_instance: str,
    received_at: datetime,
    raw_payload_artifact_id: str | None = None,
) -> AlertSignal:
    """Convert a NormalizedAlert to an AlertSignal.

    Args:
        alert: The normalized alert from Alertmanager snapshot
        source_instance: Canonical Alertmanager source ID
        received_at: When the snapshot was captured
        raw_payload_artifact_id: Optional reference to raw snapshot artifact

    Returns:
        AlertSignal ready for persistence
    """
    # Map Alertmanager state to AlertStatus
    # "active" → FIRING, anything else → FIRING (conservative)
    # Silenced/inhibited alerts should already be filtered by the fetch
    state = alert.state.lower() if alert.state else ""
    if state in ("active", "firing"):
        status = AlertStatus.FIRING
    elif state in ("resolved", "complete"):
        status = AlertStatus.RESOLVED
    else:
        # Unknown state - default to FIRING (conservative)
        status = AlertStatus.FIRING

    # Parse timestamps
    starts_at = _parse_datetime(alert.starts_at) if alert.starts_at else None
    ends_at = None  # NormalizedAlert doesn't have ends_at

    # Extract severity
    severity = alert.severity if alert.severity else None

    # Use labels directly (already sorted in NormalizedAlert)
    labels = alert.labels

    # Build annotations from summary if present
    annotations: tuple[tuple[str, str], ...] = ()
    if alert.summary:
        annotations = (("summary", alert.summary),)

    # Generate signal_id (UUID-based)
    from .identity.artifact import new_artifact_id
    signal_id = new_artifact_id()

    return AlertSignal(
        signal_id=signal_id,
        source_type=AlertSourceType.ALERTMANAGER,
        source_instance=source_instance,
        external_fingerprint=alert.fingerprint if alert.fingerprint else None,
        status=status,
        alertname=alert.alertname,
        severity=severity,
        labels=labels,
        annotations=annotations,
        starts_at=starts_at,
        ends_at=ends_at,
        received_at=received_at,
        generator_url=None,  # NormalizedAlert doesn't have generatorURL
        raw_payload_artifact_id=raw_payload_artifact_id,
        truncation=None,
    )


def persist_alert_signals(
    signals: tuple[AlertSignal, ...],
    root: Path,
    raw_payload_artifact_id: str | None = None,
) -> tuple[AlertSignalAdapterResult, list[AlertSignal]]:
    """Persist alert signals to artifacts.

    Args:
        signals: Alert signals to persist
        root: Root directory for artifacts
        raw_payload_artifact_id: Optional reference to raw snapshot artifact

    Returns:
        Tuple of (AdapterResult, list of successfully written signals)
    """
    if not signals:
        return (
            AlertSignalAdapterResult(
                total_alerts=0,
                firing_signals_count=0,
                resolved_signals_count=0,
            ),
            [],
        )

    written_signals: list[AlertSignal] = []
    errors: list[str] = []
    duplicate_count = 0
    write_failures = 0

    firing_count = 0
    resolved_count = 0

    for signal in signals:
        result = write_alert_signal_artifact(
            root=root,
            signal=signal,
            raw_payload_artifact_id=raw_payload_artifact_id,
            received_at=signal.received_at,
        )

        if result.success:
            if result.is_duplicate:
                duplicate_count += 1
            else:
                written_signals.append(signal)
            if signal.status == AlertStatus.FIRING:
                firing_count += 1
            else:
                resolved_count += 1
        else:
            error_msg = f"Failed to write signal {signal.signal_id}: {result.error}"
            _logger.warning(error_msg)
            errors.append(error_msg)
            write_failures += 1

    return (
        AlertSignalAdapterResult(
            total_alerts=len(signals),
            firing_signals_count=firing_count,
            resolved_signals_count=resolved_count,
            skipped_count=0,
            signals_written=len(written_signals),
            signals_skipped_duplicates=duplicate_count,
            signals_failed=write_failures,
            errors=tuple(errors),
        ),
        written_signals,
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse datetime string to datetime.

    Handles various formats from Alertmanager.
    """
    if not value:
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
# Module Exports
# =============================================================================

__all__ = [
    "AlertSignalAdapterResult",
    "adapt_snapshot_to_alert_signals",
    "persist_alert_signals",
]
