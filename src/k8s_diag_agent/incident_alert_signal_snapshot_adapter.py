"""Adapt Alertmanager snapshots into alert signals.

This facade owns snapshot conversion and preserves the historical import
surface. Contracts live in ``incident_alert_signal_snapshot_contract`` and
artifact persistence lives in ``incident_alert_signal_persistence``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)
from .incident_alert_signal import AlertSignal, AlertSourceType, AlertStatus
from .incident_alert_signal_identity import alert_signal_identity
from .incident_alert_signal_persistence import (
    current_run_persistence_outcomes,
    persist_alert_signals,
)
from .incident_alert_signal_snapshot_contract import (
    AlertSignalAdapterResult,
    PersistedAlertSignal,
)

_logger = logging.getLogger(__name__)


def adapt_snapshot_to_alert_signals(
    snapshot: AlertmanagerSnapshot,
    source_instance: str,
    received_at: datetime | None = None,
    raw_payload_artifact_id: str | None = None,
) -> tuple[tuple[AlertSignal, ...], AlertSignalAdapterResult]:
    """Convert normalized Alertmanager alerts into domain signals."""
    if received_at is None:
        received_at = datetime.now(UTC)

    signals: list[AlertSignal] = []
    errors: list[str] = []
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
            identity = alert_signal_identity(signal)
            if identity in seen_identities:
                _logger.debug(
                    "Skipping duplicate alert in snapshot: alertname=%s "
                    "fingerprint=%s",
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
            signals_written=0,
            signals_skipped_duplicates=0,
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
    """Convert one normalized alert while preserving all evidence fields."""
    state = alert.state.lower() if alert.state else ""
    if state in ("active", "firing"):
        status = AlertStatus.FIRING
    elif state in ("resolved", "complete"):
        status = AlertStatus.RESOLVED
    else:
        status = AlertStatus.FIRING

    starts_at = _parse_datetime(alert.starts_at) if alert.starts_at else None
    ends_at = _parse_datetime(alert.ends_at) if alert.ends_at else None
    severity = alert.severity if alert.severity else None
    labels = alert.labels
    annotations: tuple[tuple[str, str], ...] = ()
    if alert.annotations:
        annotations = alert.annotations
    elif alert.summary:
        annotations = (("summary", alert.summary),)

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
        generator_url=alert.generator_url,
        receiver=alert.receiver,
        raw_payload_artifact_id=raw_payload_artifact_id,
        truncation=None,
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse common Alertmanager timestamp formats."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

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


__all__ = [
    "AlertSignalAdapterResult",
    "PersistedAlertSignal",
    "adapt_snapshot_to_alert_signals",
    "current_run_persistence_outcomes",
    "persist_alert_signals",
]
