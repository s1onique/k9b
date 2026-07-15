"""Persistence behavior for adapted Alertmanager signal artifacts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .collect.signal_persistence_outcomes import (
    SignalIdentityMatched,
    SignalInserted,
    SignalPersistenceFailed,
    SignalPersistenceFailureCode,
    SignalPersistenceOutcome,
)
from .collect.signal_persistence_outcomes import (
    is_promotable as _is_promotable_outcome,
)
from .incident_alert_signal import AlertSignal, AlertStatus
from .incident_alert_signal_snapshot_contract import (
    AlertSignalAdapterResult,
    PersistedAlertSignal,
)
from .incident_alert_signal_store import write_alert_signal_artifact

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)


_RESULT_FAILURE_REASON_BY_RESULT = {
    "schema": SignalPersistenceFailureCode.SCHEMA_ERROR,
    "transport": SignalPersistenceFailureCode.TRANSPORT_ERROR,
    "io": SignalPersistenceFailureCode.IO_ERROR,
}


def persist_alert_signals(
    signals: tuple[AlertSignal, ...],
    root: Path,
    raw_payload_artifact_id: str | None = None,
) -> tuple[AlertSignalAdapterResult, list[PersistedAlertSignal]]:
    """Persist signals and return typed outcomes plus artifact identities.

    Both newly-written artifacts and identity-matched duplicates remain in the
    returned current-run list. Counters are projected from typed outcomes by
    :class:`AlertSignalAdapterResult`.
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
    outcomes: list[SignalPersistenceOutcome] = []
    firing_count = 0
    resolved_count = 0

    for signal in signals:
        result = write_alert_signal_artifact(
            root=root,
            signal=signal,
            raw_payload_artifact_id=raw_payload_artifact_id,
            received_at=signal.received_at,
        )
        identity = result.identity
        if not result.success:
            error_msg = f"Failed to write signal {signal.signal_id}: {result.error}"
            _logger.warning(error_msg)
            errors.append(error_msg)
            outcomes.append(
                SignalPersistenceFailed(
                    candidate_signal_id=str(signal.signal_id),
                    reason=_RESULT_FAILURE_REASON_BY_RESULT.get(
                        _RESULT_FAILURE_KIND(result),
                        SignalPersistenceFailureCode.UNKNOWN_ERROR,
                    ),
                    detail=(result.error or "")[:256],
                )
            )
            continue

        if identity is None:
            errors.append(
                f"Successful write without identity for signal {signal.signal_id}"
            )
            outcomes.append(
                SignalPersistenceFailed(
                    candidate_signal_id=str(signal.signal_id),
                    reason=SignalPersistenceFailureCode.CONTRACT_VIOLATION,
                    detail="successful write without identity",
                )
            )
            continue

        if result.is_duplicate:
            outcomes.append(SignalIdentityMatched(signal_id=str(identity)))
        else:
            outcomes.append(SignalInserted(signal_id=str(identity)))

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

    return (
        AlertSignalAdapterResult.from_outcomes(
            total_alerts=len(signals),
            firing_signals_count=firing_count,
            resolved_signals_count=resolved_count,
            skipped_count=0,
            outcomes=tuple(outcomes),
            errors=tuple(errors),
        ),
        persisted_signals,
    )


def _RESULT_FAILURE_KIND(result: object) -> str:
    """Classify a write failure into a bounded error family."""
    error = getattr(result, "error", None) or ""
    lowered = str(error).lower()
    if "json" in lowered or "decode" in lowered or "schema" in lowered:
        return "schema"
    if "transport" in lowered or "connection" in lowered or "refused" in lowered:
        return "transport"
    return "io"


def current_run_persistence_outcomes(
    outcomes: tuple[SignalPersistenceOutcome, ...],
) -> tuple[SignalPersistenceOutcome, ...]:
    """Return only the promotable outcomes admitted to the current-run scope."""
    return tuple(
        outcome for outcome in outcomes if _is_promotable_outcome(outcome)
    )


__all__ = [
    "current_run_persistence_outcomes",
    "persist_alert_signals",
]
