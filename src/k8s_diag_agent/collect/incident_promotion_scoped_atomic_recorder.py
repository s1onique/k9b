"""Atomic scoped promotion recorder for the run accumulator.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

This module owns a single small mixin,
:class:`ScopedPromotionAtomicRecorderMixin`, that the
:class:`RunPromotionAccumulator` inherits. The mixin implements the
single active-scoped recording operation:

.. code-block:: python

    accumulator.record_scoped_promotion_batch(
        handoff=handoff,
        batch=batch,
    )

The mixin enforces a strict two-phase atomic transaction:

* **Phase 1 (validate-before-mutate).** The handoff and batch are
  type-checked. The handoff/batch consistency is verified through
  :func:`incident_promotion_scoped_atomic_validation.validate_scoped_handoff_batch_consistency`
  against the canonical contract for that variant. Any conflict
  short-circuits with the bounded
  :class:`PromotionOutcomeConflictError` BEFORE any field is touched.

* **Phase 2 (rollback transaction).** If validation passes, the
  accumulator's mutable fields are snapshotted. The handoff,
  outcome, and aggregate batch accounting are committed in one
  transaction. If any commit step raises, :meth:`_restore` is
  called and the bounded ``PromotionOutcomeConflictError`` /
  ``AccumulatorAccessModeError`` propagates. Replay of an
  identical handoff + batch takes the IDEMPOTENT shortcut and
  performs zero mutation.

The mixin stays under 250 lines; the equivalence, validation,
and compatibility-batch projection live in dedicated modules
so this file is the only place that owns the atomic transaction.

Request identity (request id, request fingerprint) is the
handoff's authority -- the accumulator does NOT store mutable
copies. The fingerprint validation authority is documented as
shape-only (handoff ``__post_init__``); canonical-content fingerprint
recomputation is intentionally deferred to a future ACT.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from .incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from .incident_promotion_scoped_atomic_equivalence import (
    _batch_accounting_equivalent,
    _receipt_equivalent,
)
from .incident_promotion_scoped_atomic_validation import (
    validate_scoped_handoff_batch_consistency,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
)

if TYPE_CHECKING:
    from .incident_promotion_batch import PromotionBatch


# Injectable failure probes used by the rollback tests. The
# transaction calls them at two specific points so the post-mutation
# rollback path can be exercised without monkey-patching
# :meth:`record_promotion_outcome` or :meth:`_apply_batch`. They
# default to no-op so production callers -- and production tests
# that do not opt in -- observe exactly the documented contract.
_OUTCOME_RECORDING_PROBE: Callable[[], None] | None = None
_APPLY_BATCH_PROBE: Callable[[], None] | None = None

_RuntimeErrorSentinel: type[Exception]
try:
    from .incident_promotion_accumulator import AccumulatorAccessModeError
except ImportError:  # pragma: no cover - cycle-safe fallback
    AccumulatorAccessModeError = RuntimeError  # type: ignore[assignment,misc]
_RuntimeErrorSentinel = AccumulatorAccessModeError


class ScopedPromotionAtomicRecorderMixin:
    """Mixin providing atomic scoped promotion recording for the accumulator.

    See module docstring for the atomic transaction contract.

    The mixin expects the host class to declare the following
    fields (already declared on :class:`RunPromotionAccumulator`):

    * ``promotion_outcome: PromotionOutcome | None``
    * ``promotion_outcome_run_id: str``
    * ``scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None``
    * Aggregate-batch fields declared on
      :class:`RunPromotionAccumulator`` (``batches``,
      ``promotion_records``, ``_seen_canonical_ids``, ``total_*``,
      ``last_*``, ``last_contract_error``, ``last_handoff_error``,
      ``last_propagation_result``, ``workset_state``).

    It also expects the host class to expose:

    * :meth:`record_promotion_outcome` -- delegated to
      :class:`PromotionOutcomeRecorderMixin`.
    * :meth:`_snapshot` / :meth:`_restore` -- the existing
      snapshot / restore helpers.
    * :meth:`_apply_batch` -- the internal batch applier.
    """

    promotion_outcome: Any
    promotion_outcome_run_id: str
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None
    batches: list[Any]

    def _snapshot(self) -> dict[str, object]:
        raise NotImplementedError

    def _restore(self, snap: dict[str, object]) -> None:
        raise NotImplementedError

    def _apply_batch(self, batch: Any) -> None:
        raise NotImplementedError

    def record_promotion_outcome(
        self, outcome: Any
    ) -> PromotionOutcomeRecording:
        raise NotImplementedError

    def record_scoped_promotion_batch(
        self,
        *,
        handoff: ScopedPromotionAccumulatorHandoff,
        batch: PromotionBatch,
    ) -> PromotionOutcomeRecording:
        """Record a typed handoff + batch atomically with snapshot/restore.

        The atomic transaction is:

        1. Validate the handoff/batch agreement BEFORE any field is
           touched. Any failure is fail-closed and raises a typed
           ``PromotionOutcomeConflictError``.
        2. For an identical replay, return ``IDEMPOTENT`` without
           mutating anything.
        3. Otherwise, snapshot every mutable field, then commit
           the typed outcome and the batch accounting in one pass.
           Any exception during the commit phase restores the
           accumulator to its pre-call state.
        """
        # Phase 1: handoff/batch consistency.
        validate_scoped_handoff_batch_consistency(handoff, batch)

        running_handoff = self.scoped_promotion_handoff
        if running_handoff is not None:
            return self._replay_path(running_handoff, handoff, batch)

        # Phase 2: first record -- snapshot then commit.
        snap = self._snapshot()
        try:
            self.scoped_promotion_handoff = handoff
            if _OUTCOME_RECORDING_PROBE is not None:
                _OUTCOME_RECORDING_PROBE()
            recording = self.record_promotion_outcome(handoff.outcome)
            if recording is not PromotionOutcomeRecording.NEW:
                raise PromotionOutcomeConflictError(
                    "Scoped promotion first recording unexpectedly did "
                    "not return NEW; treating as conflict to avoid "
                    "partial commit.",
                    running_run_id=handoff.outcome.run_id,
                    rejected_run_id=handoff.outcome.run_id,
                    running_variant=type(handoff).__name__,
                    rejected_variant=type(handoff).__name__,
                )
            if _APPLY_BATCH_PROBE is not None:
                _APPLY_BATCH_PROBE()
            self._apply_batch(batch)
        except _RuntimeErrorSentinel:
            self._restore(snap)
            raise
        except PromotionOutcomeConflictError:
            self._restore(snap)
            raise
        except Exception:
            self._restore(snap)
            raise

        return PromotionOutcomeRecording.NEW

    def _replay_path(
        self,
        running_handoff: ScopedPromotionAccumulatorHandoff,
        candidate: ScopedPromotionAccumulatorHandoff,
        candidate_batch: PromotionBatch,
    ) -> PromotionOutcomeRecording:
        """Return ``IDEMPOTENT`` only when the replay matches stored authority."""
        if self.promotion_outcome != candidate.outcome:
            raise PromotionOutcomeConflictError(
                "Scoped promotion outcome mismatch: existing outcome "
                "differs from the candidate handoff outcome.",
                running_run_id=running_handoff.outcome.run_id,
                rejected_run_id=candidate.outcome.run_id,
                running_variant=type(running_handoff.outcome).__name__,
                rejected_variant=type(candidate.outcome).__name__,
            )
        if not _handoffs_match(running_handoff, candidate):
            raise PromotionOutcomeConflictError(
                "Scoped promotion handoff mismatch: identity fields, "
                "receipt, or commit disposition disagree with the "
                "running handoff.",
                running_run_id=running_handoff.outcome.run_id,
                rejected_run_id=candidate.outcome.run_id,
                running_variant=type(running_handoff.outcome).__name__,
                rejected_variant=type(candidate.outcome).__name__,
            )
        if not _batch_accounting_equivalent(self.batches[-1], candidate_batch):
            raise PromotionOutcomeConflictError(
                "Scoped promotion batch accounting mismatch: candidate "
                "batch disagrees with the most recently recorded "
                "aggregate on every authoritative field.",
                running_run_id=running_handoff.outcome.run_id,
                rejected_run_id=candidate.outcome.run_id,
                running_variant=type(running_handoff.outcome).__name__,
                rejected_variant=type(candidate.outcome).__name__,
            )
        return PromotionOutcomeRecording.IDEMPOTENT


def _handoffs_match(
    running: ScopedPromotionAccumulatorHandoff,
    candidate: ScopedPromotionAccumulatorHandoff,
) -> bool:
    """Return True iff two handoffs are equivalent for replay.

    Dataclass ``__eq__`` on the closed-union variants compares every
    declared field. The completed variant also requires the receipt
    identity via the canonical :class:`BoundScopedPromotionResult`
    equality inside :func:`_receipt_equivalent`.
    """
    if type(running) is not type(candidate):
        return False
    if (running.request_id, running.request_fingerprint,
            running.commit_disposition, running.outcome) != (
                candidate.request_id,
                candidate.request_fingerprint,
                candidate.commit_disposition,
                candidate.outcome,
            ):
        return False
    if isinstance(running, ScopedPromotionAccumulatorCompleted):
        candidate_completed = cast(
            ScopedPromotionAccumulatorCompleted, candidate
        )
        if not _receipt_equivalent(
            running.receipt.bound, candidate_completed.receipt.bound
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# Test-only failure probes. The transaction calls these at well-defined
# points so the post-mutation rollback path can be exercised without
# monkey-patching the host class. NOT part of the public API.
# ---------------------------------------------------------------------------

_FailureProbe = Callable[[], None]


def _set_outcome_recording_probe(probe: Callable[[], None]) -> None:
    """Test-only: install a callable invoked after handoff assignment."""
    global _OUTCOME_RECORDING_PROBE
    _OUTCOME_RECORDING_PROBE = probe


def _set_apply_batch_probe(probe: Callable[[], None]) -> None:
    """Test-only: install a callable invoked inside the commit transaction."""
    global _APPLY_BATCH_PROBE
    _APPLY_BATCH_PROBE = probe


def _clear_probes() -> None:
    """Test-only: clear every installed probe."""
    global _OUTCOME_RECORDING_PROBE, _APPLY_BATCH_PROBE
    _OUTCOME_RECORDING_PROBE = None
    _APPLY_BATCH_PROBE = None


__all__ = [
    "ScopedPromotionAtomicRecorderMixin",
    "_set_outcome_recording_probe",
    "_set_apply_batch_probe",
    "_clear_probes",
]
