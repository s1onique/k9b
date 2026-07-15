"""Typed promotion-outcome ownership mixin for the run promotion accumulator.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 contract:

* The accumulator is the single owner of the typed
  :class:`PromotionOutcome` for a health run via
  :meth:`record_promotion_outcome`. Recording a second outcome for a
  different ``run_id`` or a materially different variant raises
  :class:`PromotionOutcomeConflictError`; an identical repeated
  assignment is idempotent.
* Idempotency is checked using the dataclass-generated ``__eq__``:
  two outcomes are equal iff they share the same variant, ``run_id``
  and payload (including the complete
  :class:`PromotionReconciliationToken` with both ``request_id`` and
  ``request_fingerprint``).
* Once a typed outcome is recorded, the projection methods
  (``canonical_incident_ids``, ``recorded_records``,
  ``promotion_may_have_committed``,
  ``promotion_consistency_error_recorded``,
  ``diagnosis_handoff_available``) DERIVE from the recorded outcome
  rather than from legacy counter projections. Legacy accumulation is
  the fallback only when no typed outcome is recorded.

The mixin is extracted from :mod:`incident_promotion_accumulator` so
the accumulator file stays under the LLM-friendly 500-line limit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from .incident_identity_hardening import PromotionRecord

if TYPE_CHECKING:
    from .promotion_outcomes import PromotionOutcome


class PromotionOutcomeRecording(StrEnum):
    """Result of :meth:`PromotionOutcomeRecorderMixin.record_promotion_outcome`.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01: the
    caller uses this to gate the compatibility handoff so an identical
    retry does not repeat ``propagate_promotion_result_to_run()``,
    which would duplicate counters, records, and handoff events.
    """

    NEW = "new"
    """A new (non-equal) outcome was recorded and is now authoritative."""

    IDEMPOTENT = "idempotent"
    """The identical outcome was already recorded; no state change occurred."""


class PromotionOutcomeConflictError(ValueError):
    """Raised when recording a typed outcome violates the one-owner contract.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 invariant:
    the accumulator is the single owner of the typed
    :class:`PromotionOutcome` for a health run. Recording a second
    outcome for a different ``run_id`` or a materially different
    variant is a fail-closed condition. An identical repeated
    assignment is accepted as idempotent so retries against the
    same logical dispatch request do not raise.

    Idempotency is checked using the dataclass-generated
    ``__eq__``: two outcomes are equal iff they share the same
    variant, ``run_id`` and payload (including the complete
    :class:`PromotionReconciliationToken` with both ``request_id``
    and ``request_fingerprint``).
    """

    def __init__(
        self,
        message: str,
        *,
        running_run_id: str,
        rejected_run_id: str,
        running_variant: str,
        rejected_variant: str,
    ) -> None:
        super().__init__(message)
        self.running_run_id = running_run_id
        self.rejected_run_id = rejected_run_id
        self.running_variant = running_variant
        self.rejected_variant = rejected_variant


def outcome_variant_label(outcome: object) -> str:
    """Return a stable string label for a :class:`PromotionOutcome` variant.

    Used by :meth:`RunPromotionAccumulator.record_promotion_outcome`
    to construct a deterministic conflict-error diagnostic.
    """
    from .promotion_outcomes import (
        PromotionCommitUnknown,
        PromotionRejected,
        PromotionSucceeded,
    )

    if isinstance(outcome, PromotionSucceeded):
        return "succeeded"
    if isinstance(outcome, PromotionRejected):
        return "rejected"
    if isinstance(outcome, PromotionCommitUnknown):
        return "commit_unknown"
    return type(outcome).__name__


class PromotionOutcomeRecorderMixin:
    """Mixin providing typed-outcome ownership for :class:`RunPromotionAccumulator`.

    The mixin expects the host class to declare:

    * ``promotion_outcome: PromotionOutcome | None``
    * ``promotion_outcome_run_id: str``

    It contributes the recording, conflict-detection, and
    derived-projection methods.
    """

    promotion_outcome: PromotionOutcome | None
    promotion_outcome_run_id: str

    def record_promotion_outcome(
        self,
        outcome: PromotionOutcome,
    ) -> PromotionOutcomeRecording:
        """Record the typed :class:`PromotionOutcome` for the current run.

        ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 contract:

        * The first typed outcome becomes authoritative. The first
          successful recording also sets ``promotion_outcome_run_id``
          to the outcome's ``run_id`` so cross-run laundering is
          fail-closed at the recorder boundary.
        * Recording an outcome for a different ``run_id`` raises
          :class:`PromotionOutcomeConflictError`.
        * Recording a materially different second outcome raises
          :class:`PromotionOutcomeConflictError` so the orchestrator
          cannot silently overwrite the authoritative result.
        * An identical repeated assignment is idempotently accepted
          and returns :attr:`PromotionOutcomeRecording.IDEMPOTENT`
          so the caller can skip the compatibility handoff on retry.

        Returns:
            :attr:`PromotionOutcomeRecording.NEW` when the outcome was
            recorded for the first time; :attr:`PromotionOutcomeRecording.IDEMPOTENT`
            when an identical outcome was already recorded.
        """
        if outcome is None:
            raise ValueError(
                "record_promotion_outcome requires a non-None PromotionOutcome"
            )
        if self.promotion_outcome is None:
            self.promotion_outcome = outcome
            self.promotion_outcome_run_id = outcome.run_id
            return PromotionOutcomeRecording.NEW
        running = self.promotion_outcome
        if running.run_id != outcome.run_id:
            raise PromotionOutcomeConflictError(
                "Cannot record a PromotionOutcome for a different run_id; "
                f"running={running.run_id!r} rejected={outcome.run_id!r}",
                running_run_id=running.run_id,
                rejected_run_id=outcome.run_id,
                running_variant=outcome_variant_label(running),
                rejected_variant=outcome_variant_label(outcome),
            )
        if running == outcome:
            return PromotionOutcomeRecording.IDEMPOTENT
        raise PromotionOutcomeConflictError(
            "PromotionOutcome already recorded; conflicting second "
            "outcome rejected to keep the typed outcome authoritative.",
            running_run_id=running.run_id,
            rejected_run_id=outcome.run_id,
            running_variant=outcome_variant_label(running),
            rejected_variant=outcome_variant_label(outcome),
        )

    def promotion_outcome_variant_label(self) -> str:
        """Return a stable string label for the recorded outcome variant.

        Returns ``"none"`` when no outcome has been recorded yet so
        the field never silently defaults to an empty string.
        """
        if self.promotion_outcome is None:
            return "none"
        return outcome_variant_label(self.promotion_outcome)

    def recorded_records(self) -> tuple[PromotionRecord, ...]:
        """Return the typed outcome's records when available.

        Once a typed outcome exists, legacy records MUST NEVER regain
        authority. ``PromotionSucceeded`` exposes the outcome's
        ``records`` tuple verbatim; ``PromotionRejected`` and
        ``PromotionCommitUnknown`` expose an empty tuple. The legacy
        ``promotion_records`` projection is used only when NO typed
        outcome has been recorded.

        The return type is ``tuple[PromotionRecord, ...]`` -- all
        records are runtime-validated as ``PromotionRecord`` instances
        via ``PromotionSucceeded.__post_init__`` so the domain
        narrowing is complete across the seam.
        """
        from .promotion_outcomes import PromotionSucceeded

        if self.promotion_outcome is not None:
            if isinstance(self.promotion_outcome, PromotionSucceeded):
                return tuple(self.promotion_outcome.records)
            return ()
        return tuple(self.promotion_records)

    def promotion_may_have_committed(self) -> bool:
        """Return the typed-outcome-aware ``promotion_may_have_committed``.

        Once a typed outcome is recorded, this derives from it
        (``may_have_committed(outcome)``). Before recording, the
        legacy counter projection is used.
        """
        from .promotion_outcomes import may_have_committed

        if self.promotion_outcome is not None:
            return bool(may_have_committed(self.promotion_outcome))
        return bool(self.total_opened_incidents > 0 or self.total_updated_incidents > 0)

    def promotion_consistency_error_recorded(self) -> bool:
        """Return the typed-outcome-aware consistency-error projection.

        Once a typed outcome is recorded, this derives from it
        (``consistency_error_recorded(outcome)``). Before recording, the
        legacy counter projection is used.
        """
        from .promotion_outcomes import consistency_error_recorded

        if self.promotion_outcome is not None:
            return bool(consistency_error_recorded(self.promotion_outcome))
        return bool(self.total_errors > 0 or bool(self.last_contract_error))

    def diagnosis_handoff_available(self) -> bool:
        """Return the typed-outcome-aware diagnosis-handoff-availability.

        Only :class:`PromotionSucceeded` makes diagnosis handoff
        available. Rejection and commit-unknown both fail closed.
        """
        from .promotion_outcomes import propagation_available

        if self.promotion_outcome is not None:
            return bool(propagation_available(self.promotion_outcome))
        return bool(self.total_opened_incidents > 0 or self.total_updated_incidents > 0)



    def promotion_outcomes(self) -> tuple[str, ...]:
        """Return the promotion outcomes in input order.

        Once a typed outcome exists, legacy per-record outcomes MUST
        NEVER regain authority. ``PromotionRejected`` exposes its
        bounded reason; ``PromotionSucceeded`` derives from the typed
        outcome's per-record projection; ``PromotionCommitUnknown``
        has no per-record outcomes so returns empty. The legacy
        per-record list is the fallback only when NO typed outcome
        has been recorded.

        The closed union is used directly; unsupported variants raise
        ``TypeError`` rather than silently returning ``()``.
        """
        from .promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionRejected,
            PromotionSucceeded,
        )

        if self.promotion_outcome is not None:
            if isinstance(self.promotion_outcome, PromotionRejected):
                return (self.promotion_outcome.reason.value,)
            if isinstance(self.promotion_outcome, PromotionSucceeded):
                return tuple(
                    record.promotion_outcome
                    for record in self.promotion_outcome.records
                )
            if isinstance(
                self.promotion_outcome, PromotionCommitUnknown
            ):
                return ()
            # Explicit exhaustive check: raise instead of silently returning ()
            raise TypeError(
                f"Unsupported PromotionOutcome variant: "
                f"{type(self.promotion_outcome).__name__!r}"
            )
        return tuple(
            record.promotion_outcome for record in self.promotion_records
        )

    def canonical_incident_ids(
        self,
        *,
        include_skipped: bool = False,
    ) -> list[str]:
        """Return canonical IDs in deterministic first-seen order.

        Once a typed outcome is recorded, the projection derives from
        the recorded outcome:

        * ``PromotionSucceeded`` -> the outcome's
          ``diagnosis_incident_ids`` (authoritative canonical IDs).
        * ``PromotionRejected`` / ``PromotionCommitUnknown`` -> empty
          (no authoritative canonical IDs available).

        When no typed outcome is recorded the legacy
        ``select_canonical_ids_from_promotion`` projection is used.
        """
        if self.promotion_outcome is not None:
            from .promotion_outcomes import PromotionSucceeded

            if isinstance(self.promotion_outcome, PromotionSucceeded):
                return list(self.promotion_outcome.diagnosis_incident_ids)
            return []
        from .incident_identity_hardening import (
            select_canonical_ids_from_promotion,
        )
        return select_canonical_ids_from_promotion(
            self.promotion_records,
            include_skipped=include_skipped,
        )


__all__ = [
    "PromotionOutcomeConflictError",
    "PromotionOutcomeRecording",
    "PromotionOutcomeRecorderMixin",
    "outcome_variant_label",
]
