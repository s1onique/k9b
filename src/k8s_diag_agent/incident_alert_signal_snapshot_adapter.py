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


@dataclass(frozen=True, slots=True)
class PersistedAlertSignal:
    """Persisted alert signal paired with its deterministic artifact identity.

    The scheduler hands the backend ``artifact_identity`` (the SHA256-derived
    identity used in the artifact filename and lookup) rather than the
    in-memory ``signal.signal_id`` UUID. The backend reads the artifact
    via ``read_alert_signal_artifact(root, identity)``; passing the UUID
    would fail closed with ``signal <uuid> is not present in the
    current-run scope`` for every non-empty scoped request.

    ``newly_written=False`` represents an already-existing artifact;
    those duplicates MUST still be included in the current-run scope so
    retry semantics, observation refreshes, and rebuilt incident stores
    continue to work.
    """

    signal: AlertSignal
    artifact_identity: str
    newly_written: bool


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

    Extended in ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1 to preserve:
    - generator_url from NormalizedAlert.generator_url
    - full annotations from NormalizedAlert.annotations
    - ends_at from NormalizedAlert.ends_at
    - receiver from NormalizedAlert.receiver

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

    # Parse timestamps (ACT-R1: also parse ends_at)
    starts_at = _parse_datetime(alert.starts_at) if alert.starts_at else None
    ends_at = _parse_datetime(alert.ends_at) if alert.ends_at else None

    # Extract severity
    severity = alert.severity if alert.severity else None

    # Use labels directly (already sorted in NormalizedAlert)
    labels = alert.labels

    # Build annotations from full NormalizedAlert.annotations (ACT-R1)
    # Use full annotations if present, otherwise fall back to summary
    annotations: tuple[tuple[str, str], ...] = ()
    if alert.annotations:
        annotations = alert.annotations
    elif alert.summary:
        # Legacy fallback: build annotations from summary only
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
        generator_url=alert.generator_url,  # ACT-R1: preserve generator_url
        receiver=alert.receiver,  # ACT-R1: preserve receiver
        raw_payload_artifact_id=raw_payload_artifact_id,
        truncation=None,
    )


def persist_alert_signals(
    signals: tuple[AlertSignal, ...],
    root: Path,
    raw_payload_artifact_id: str | None = None,
) -> tuple[AlertSignalAdapterResult, list[PersistedAlertSignal]]:
    """Persist alert signals to artifacts.

    R1 contract: every successfully observed signal is returned as a
    :class:`PersistedAlertSignal` carrying the **deterministic artifact
    identity** (SHA256-derived, used as the artifact filename). The
    scheduler passes those identities to the backend's scoped promotion
    endpoint so the backend can read the corresponding artifact.

    Both newly-written artifacts and already-existing duplicates are
    included in the returned list. Excluding duplicates would silently
    drop retry/rebuild/observation-refresh semantics from the current-run
    scope.

    Args:
        signals: Alert signals to persist
        root: Root directory for artifacts
        raw_payload_artifact_id: Optional reference to raw snapshot artifact

    Returns:
        Tuple of (AdapterResult, list of :class:`PersistedAlertSignal`)
        in the order the artifacts were processed. The artifact
        identity is the canonical lookup key the backend expects.
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

    persisted_signals: list[PersistedAlertSignal] = []
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
            identity = result.identity
            if identity is None:
                errors.append(
                    f"Successful write without identity for signal {signal.signal_id}"
                )
                write_failures += 1
                continue
            if result.is_duplicate:
                duplicate_count += 1
            persisted_signals.append(
                PersistedAlertSignal(
                    signal=signal,
                    artifact_identity=identity,
                    newly_written=not result.is_duplicate,
                )
            )
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
            signals_written=len(persisted_signals) - duplicate_count,
            signals_skipped_duplicates=duplicate_count,
            signals_failed=write_failures,
            errors=tuple(errors),
        ),
        persisted_signals,
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
    "PersistedAlertSignal",
    "adapt_snapshot_to_alert_signals",
    "persist_alert_signals",
]
