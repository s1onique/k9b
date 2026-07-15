"""Domain contracts for Alertmanager signal snapshot adaptation."""

from __future__ import annotations

from dataclasses import dataclass

from .collect.signal_persistence_outcomes import (
    SignalIdentityConflict,
    SignalIdentityMatched,
    SignalInserted,
    SignalPersistenceOutcome,
    SignalPersistenceSummary,
)
from .collect.signal_persistence_outcomes import (
    is_promotable as _is_promotable_outcome,
)
from .incident_alert_signal import AlertSignal


@dataclass(frozen=True)
class AlertSignalAdapterResult:
    """Result of adapting and persisting Alertmanager snapshot signals.

    ``persistence_outcomes`` is authoritative. The legacy counters and
    ``promotable_signal_ids`` are deterministic projections of that sequence.
    """

    total_alerts: int = 0
    firing_signals_count: int = 0
    resolved_signals_count: int = 0
    skipped_count: int = 0
    signals_written: int = 0
    signals_skipped_duplicates: int = 0
    signals_failed: int = 0
    persistence_outcomes: tuple[SignalPersistenceOutcome, ...] = ()
    promotable_signal_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @classmethod
    def from_outcomes(
        cls,
        *,
        total_alerts: int,
        firing_signals_count: int,
        resolved_signals_count: int,
        skipped_count: int,
        outcomes: tuple[SignalPersistenceOutcome, ...],
        errors: tuple[str, ...] = (),
    ) -> AlertSignalAdapterResult:
        """Build a result with every projection derived from outcomes."""
        summary = SignalPersistenceSummary(outcomes=outcomes)
        promotable_ids: list[str] = []
        for outcome in outcomes:
            if isinstance(outcome, SignalInserted):
                promotable_ids.append(outcome.signal_id)
            elif isinstance(outcome, SignalIdentityMatched):
                promotable_ids.append(outcome.signal_id)
        return cls(
            total_alerts=total_alerts,
            firing_signals_count=firing_signals_count,
            resolved_signals_count=resolved_signals_count,
            skipped_count=skipped_count,
            signals_written=summary.inserted_count,
            signals_skipped_duplicates=summary.identity_matched_count,
            signals_failed=summary.persistence_failure_count,
            persistence_outcomes=outcomes,
            promotable_signal_ids=tuple(promotable_ids),
            errors=errors,
        )

    @property
    def has_signals(self) -> bool:
        """Return whether any signals are promotable."""
        if self.promotable_signal_ids:
            return True
        return (self.signals_written + self.signals_skipped_duplicates) > 0

    @property
    def has_errors(self) -> bool:
        """Return whether any errors occurred."""
        return len(self.errors) > 0

    @property
    def is_workset_populated(self) -> bool:
        """Return the strict typed-outcome workset membership projection."""
        return bool(self.promotable_signal_ids)

    @property
    def promotable_outcomes(self) -> tuple[SignalPersistenceOutcome, ...]:
        """Return the authoritative promotable outcomes."""
        return tuple(
            outcome
            for outcome in self.persistence_outcomes
            if _is_promotable_outcome(outcome)
        )

    @property
    def identity_conflict_count(self) -> int:
        """Count identity-conflicting outcomes excluded from the workset."""
        return sum(
            1
            for outcome in self.persistence_outcomes
            if isinstance(outcome, SignalIdentityConflict)
        )


@dataclass(frozen=True, slots=True)
class PersistedAlertSignal:
    """Persisted signal paired with its deterministic artifact identity."""

    signal: AlertSignal
    artifact_identity: str
    newly_written: bool


__all__ = [
    "AlertSignalAdapterResult",
    "PersistedAlertSignal",
]
