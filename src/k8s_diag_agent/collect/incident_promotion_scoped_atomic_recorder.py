"""Atomic scoped promotion recorder for the run accumulator.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION04-REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
CORRECTION05-STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

This module owns a single small mixin,
:class:`ScopedPromotionAtomicRecorderMixin`, that the
:class:`RunPromotionAccumulator` inherits. The mixin implements
the single active-scoped recording operation:

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
  accumulator's mutable fields are snapshotted via the typed
  :class:`AccumulatorSnapshot`. The handoff, outcome, and
  aggregate batch accounting are committed in one transaction.
  If any commit step raises, :meth:`_restore` is called and the
  bounded ``PromotionOutcomeConflictError`` /
  ``AccumulatorAccessModeError`` propagates. Replay of an
  identical handoff + batch takes the IDEMPOTENT shortcut and
  performs zero mutation.

The mixin stays under the hard 500-line limit; the equivalence,
validation, and compatibility-batch projection live in dedicated
modules so this file is the only place that owns the atomic
transaction.

The recorder types the host through
:class:`incident_promotion_scoped_atomic_host_protocol.ScopedPromotionAccumulatorHost`
so the split module is cycle-free: it never imports
:class:`RunPromotionAccumulator` directly. The protocol-driven
design eliminates ``Any`` fields and the legacy untyped dict snapshots
snapshots, restoring strict mypy on this module.

Request identity (request id, request fingerprint) is the
handoff's authority -- the accumulator does NOT store mutable
copies. The fingerprint validation authority is documented as
shape-only (handoff ``__post_init__``); canonical-content fingerprint
recomputation is intentionally deferred to a future ACT.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .incident_promotion_batch import PromotionBatch
from .incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from .incident_promotion_scoped_atomic_equivalence import (
    _batch_accounting_equivalent,
    _receipt_equivalent,
)
from .incident_promotion_scoped_atomic_host_protocol import (
    ScopedPromotionAccumulatorHost,
)
from .incident_promotion_scoped_atomic_validation import (
    validate_scoped_handoff_batch_consistency,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
)

if TYPE_CHECKING:
    from .incident_identity_hardening import PromotionRecord as _RecordType
    from .promotion_outcomes import PromotionOutcome as _OutcomeType
    from .promotion_scoped_accumulator_handoff import (
        ScopedPromotionAccumulatorHandoff as _HandoffType,
    )


class ScopedPromotionAtomicRecorderMixin(ScopedPromotionAccumulatorHost):
    """Mixin providing atomic scoped promotion recording for the accumulator.

    See module docstring for the atomic transaction contract.

    The mixin expects the host class to declare the following
    fields (already declared on :class:`RunPromotionAccumulator`):

    * ``promotion_outcome: PromotionOutcome | None``
    * ``promotion_outcome_run_id: str``
    * ``scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None``

    The ``Protocol`` super-class declares those attributes but
    :mod:`mypy` does not propagate protocol attribute types through
    :class:`typing.Protocol` access; the redundant declarations
    below ensure the recorder's body type checks without
    per-access casts. The concrete
    :class:`RunPromotionAccumulator` provides the implementations
    of :meth:`_snapshot`, :meth:`_restore`, :meth:`_apply_batch`,
    and :meth:`record_promotion_outcome`.

    Failure injection is the responsibility of the test subclass
    (or ``monkeypatch`` of an instance method). The previous
    global-probe design was removed because global mutable
    production state is unsafe under parallel tests or
    concurrent recorder calls; the architecture guard
    :func:`test_atomic_recorder_excludes_global_probes`
    enforces the absence of the removed helpers.
    """

    # Redundant declarations for mypy -- the protocol attributes
    # above are not propagated into method bodies.
    promotion_outcome: _OutcomeType | None
    promotion_outcome_run_id: str
    scoped_promotion_handoff: _HandoffType | None
    promotion_records: list[_RecordType]
    _seen_canonical_ids: set[str]
    batches: list[PromotionBatch]

    def record_scoped_promotion_batch(
        self,
        *,
        handoff: ScopedPromotionAccumulatorHandoff,
        batch: object,  # validated by validate_scoped_handoff_batch_consistency
    ) -> PromotionOutcomeRecording:
        """Record a typed handoff + batch atomically with snapshot/restore.

        The atomic transaction is:

        1. Validate the handoff/batch agreement BEFORE any field is
           touched. Any failure is fail-closed and raises a typed
           ``PromotionOutcomeConflictError`` or ``ValueError``.
        2. For an identical replay, return ``IDEMPOTENT`` without
           mutating anything.
        3. Otherwise, snapshot every mutable field, then commit
           the typed outcome and the batch accounting in one pass.
           Any exception during the commit phase restores the
           accumulator to its pre-call state.
        """
        # Phase 1: handoff/batch consistency. The validator
        # raises ``TypeError`` / ``ValueError`` for any contract
        # violation, and narrows ``batch`` to the typed
        # :class:`PromotionBatch` after the call returns.
        validate_scoped_handoff_batch_consistency(handoff, batch)
        typed_batch = cast(PromotionBatch, batch)

        running_handoff = self.scoped_promotion_handoff
        if running_handoff is not None:
            return self._replay_path(
                running_handoff, handoff, typed_batch
            )

        # Phase 2: first record -- snapshot then commit. The
        # typed snapshot is restored in place (containers retain
        # identity) by ``_restore`` so any external observer
        # holding a reference to the original lists/sets sees the
        # same Python object after a partial-batch rollback.
        snap = self._snapshot()
        try:
            self.scoped_promotion_handoff = handoff
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
            self._apply_batch(typed_batch)
        except Exception:
            # Every exception -- typed ``PromotionOutcomeConflictError``,
            # ``AccumulatorAccessModeError``, ``RuntimeError`` raised
            # by ``_apply_batch``, or any unexpected failure --
            # restores the snapshot and re-raises. The container
            # identity invariant is preserved by the ``_restore``
            # contract on the host.
            self._restore(snap)
            raise

        return PromotionOutcomeRecording.NEW

    def _replay_path(
        self,
        running_handoff: ScopedPromotionAccumulatorHandoff,
        candidate: ScopedPromotionAccumulatorHandoff,
        candidate_batch: object,
    ) -> PromotionOutcomeRecording:
        """Return ``IDEMPOTENT`` only when the replay matches stored authority.

        Fail-closed: if the running accumulator carries a handoff
        but no aggregate batch -- whether caused by old persisted
        state, manual reconstruction, or a future migration defect
        -- the recorder raises a typed
        :class:`PromotionOutcomeConflictError` with a bounded
        inconsistent-state identity instead of leaking the raw
        ``IndexError`` a ``self.batches[-1]`` access would
        produce.
        """
        if not self.batches:
            raise PromotionOutcomeConflictError(
                "Scoped promotion replay encountered an inconsistent "
                "accumulator state: a handoff is recorded but no "
                "aggregate accounting batch exists. This shape should "
                "be impossible after a successful first recording; "
                "manual reconstruction or persisted-state drift is "
                "the most likely cause.",
                running_run_id=running_handoff.outcome.run_id,
                rejected_run_id=candidate.outcome.run_id,
                running_variant=type(running_handoff.outcome).__name__,
                rejected_variant=type(candidate.outcome).__name__,
            )
        running_batch = self.batches[-1]
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
        if not _batch_accounting_equivalent(
            running_batch, cast(PromotionBatch, candidate_batch)
        ):
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


__all__ = [
    "ScopedPromotionAtomicRecorderMixin",
]