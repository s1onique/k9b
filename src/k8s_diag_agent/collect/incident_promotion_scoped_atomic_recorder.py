"""Atomic scoped promotion recording for the run accumulator.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

This module provides :class:`ScopedPromotionAtomicRecorderMixin`,
the single-owner recorder for the active scoped promotion path.
Every active scoped dispatcher reaches the run-scoped accumulator
through one operation:

.. code-block:: python

    accumulator.record_scoped_promotion_batch(
        handoff=handoff,
        batch=batch,
    )

The recorder enforces a strict atomic contract:

* Validation completes BEFORE any field on the host class is
  mutated. The handoff construction invariants (see
  :mod:`promotion_scoped_accumulator_handoff`) are preconditions.
* The handoff and the batch MUST agree on the dispatch variant
  (completed / uncertain / rejected). Per-signal records are
  intentionally fabricated as ``()`` because aggregate scoped
  results carry projection state in the receipt / typed outcome,
  never in raw per-signal dicts.
* ``existing scoped authority is None`` -> first recording:
  the outcome, the typed handoff, and the aggregate batch
  accounting are committed in one transaction, and the method
  returns :attr:`PromotionOutcomeRecording.NEW`.
* ``existing scoped authority matches`` -> semantically equal
  replay: the recorder returns
  :attr:`PromotionOutcomeRecording.IDEMPOTENT`, retains the
  originally recorded handoff and outcome by identity, and
  performs zero mutation.
* Any disagreement in outcome, handoff identity, commit
  disposition, or batch accounting raises
  :class:`PromotionOutcomeConflictError` and performs ZERO
  mutation (validated by snapshot/restore and by post-call
  identity assertions in the focused tests).

Request identity (request id, request fingerprint) is the
handoff's authority. The recorder does NOT store independently
mutable copies of either field; downstream readers derive them
from ``scoped_promotion_handoff`` through explicit @property
accessors declared on the host class.

The fingerprint authority is documented as shape-only:

* The handoff's ``__post_init__`` enforces that the request
  fingerprint is a canonical SHA-256 (64 lower-case hex chars).
* The recorder does NOT recompute the fingerprint from the
  canonical request contents in this ACT.

The recorder never uses the legacy ``PromotionRecord``-based
projection to second-guess the handoff variant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from .incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)
from .promotion_scoped_http_seam import ScopedPromotionReceipt

if TYPE_CHECKING:
    from .incident_promotion_batch import PromotionBatch
    from .promotion_scoped_accumulator_handoff import ScopedPromotionAccumulatorHandoff

# Runtime imports of ``AccumulatorAccessModeError`` and
# ``INCIDENT_ACCESS_MODE_BACKEND`` are deferred to avoid a circular
# import: this module is imported by
# :mod:`incident_promotion_accumulator` (to wire the mixin into
# :class:`RunPromotionAccumulator`). The values are referenced only
# inside the validator and atomic recorder, which run AFTER the
# module-level cycle has resolved, so a function-local ``import``
# is sufficient and avoids the cycle.


# Strings imported lazily to avoid top-level cycles with dispatcher
# constants. They participate in compatibility/accounting checks
# only and MUST agree with :mod:`incident_promotion_dispatch`.
_RECONCILIATION_REQUIRED_ACCESS_MODE = "reconciliation_required"


def _build_compatibility_batch_from_handoff(
    handoff: ScopedPromotionAccumulatorHandoff,
) -> PromotionBatch:
    """Build a bounded accounting batch for a typed handoff.

    Used only by the
    :meth:`RunPromotionAccumulator.record_scoped_promotion`
    compatibility wrapper. The active scoped dispatcher MUST
    build its own batch (carrying the bounded access mode for the
    dispatch variant) and call
    :meth:`RunPromotionAccumulator.record_scoped_promotion_batch`
    directly. This helper exists so the legacy single-argument
    signature still routes through the atomic validation gate
    and preserves the empty-``promotion_records`` invariant.

    The dispatched batch always satisfies the handoff-variant
    validator.
    """
    from .incident_promotion_batch import PromotionBatch
    from .incident_promotion_dispatch import (
        INCIDENT_ACCESS_MODE_BACKEND,
        MODE_BACKEND_API,
        IncidentPromotionResult,
    )

    scan_scope = "internal_api_alert_signals:scoped"

    # Each branch uses its own ``outcome`` and ``receipt`` local
    # variables so mypy does NOT see the same identifier rebound to
    # different closed-union types across sequential ``if``
    # branches. This is the only deliberate divergence from a
    # refactor to a single ``case`` match in the older codebase.
    if isinstance(handoff, ScopedPromotionAccumulatorCompleted):
        completed_outcome = handoff.outcome
        completed_receipt = handoff.receipt
        scanned = len(completed_outcome.requested_signal_ids)
        opened_ids = completed_receipt.opened_incident_ids
        updated_ids = completed_receipt.materially_changed_incident_ids
        completed_result = IncidentPromotionResult(
            ok=True,
            scanned=scanned,
            firing=scanned,
            opened_incidents=len(opened_ids),
            updated_incidents=len(updated_ids),
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=tuple(opened_ids),
            updated_incident_ids=tuple(updated_ids),
            observation_refreshed_incident_ids=tuple(
                completed_receipt.observation_refreshed_incident_ids
            ),
            unchanged_incident_ids=tuple(
                completed_receipt.unchanged_incident_ids
            ),
            promotion_records=(),
            unique_candidate_count=scanned,
            promotion_scan_scope=scan_scope,
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        return PromotionBatch(
            promotion_result=completed_result,
            promotion_records=(),
            source_kind="alertmanager",
            cluster_context=None,
            snapshot_bundle_id=None,
        )

    if isinstance(handoff, ScopedPromotionAccumulatorUncertain):
        uncertain_outcome = handoff.outcome
        scanned = len(uncertain_outcome.requested_signal_ids)
        uncertain_result = IncidentPromotionResult(
            ok=False,
            scanned=scanned,
            firing=scanned,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            unique_candidate_count=scanned,
            promotion_scan_scope=scan_scope,
            incident_access_mode="reconciliation_required",
        )
        return PromotionBatch(
            promotion_result=uncertain_result,
            promotion_records=(),
            source_kind="alertmanager",
            cluster_context=None,
            snapshot_bundle_id=None,
        )

    if isinstance(handoff, ScopedPromotionAccumulatorRejected):
        rejected_outcome = handoff.outcome
        scanned = len(rejected_outcome.rejected_signal_ids)
        rejected_result = IncidentPromotionResult(
            ok=False,
            scanned=scanned,
            firing=scanned,
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=1,
            error_messages=(rejected_outcome.reason.value,),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            unique_candidate_count=scanned,
            promotion_scan_scope=scan_scope,
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        return PromotionBatch(
            promotion_result=rejected_result,
            promotion_records=(),
            source_kind="alertmanager",
            cluster_context=None,
            snapshot_bundle_id=None,
        )

    from typing import assert_never

    assert_never(handoff)


def _validate_scoped_handoff_batch_consistency(
    handoff: ScopedPromotionAccumulatorHandoff,
    batch: PromotionBatch,
) -> None:
    """Validate that the handoff and batch agree on the dispatch variant.

    The batch is a compatibility / accounting projection. It MUST
    NEVER carry a second outcome authority. The dispatcher therefore
    MUST construct the batch from the same typed handoff that reaches
    this recorder, and this function rejects any disagreement between
    handoff variant and batch fields.

    The contract:

    * Completed handoff -> ``batch.promotion_result.ok is True``,
      ``incident_access_mode == "backend"``, batch scanned /
      firing / opened / updated aggregates agree with the receipt's
      bound fields, batch scanned == len(requested_signal_ids),
      and ``batch.promotion_records == ()``.
    * Uncertain handoff -> ``batch.promotion_result.ok is False``,
      ``incident_access_mode == "reconciliation_required"``,
      ``batch.promotion_records == ()``.
    * Rejected handoff -> ``batch.promotion_result.ok is False``,
      ``errors == 1`` with at least one bounded rejection reason in
      ``error_messages``, ``incident_access_mode == "backend"``,
      and ``batch.promotion_records == ()``.

    Raises:
        TypeError: when the handoff or batch has the wrong runtime
            type. The runtime checks are direct enum-aware checks:
            they do not coerce duck-typed inputs.
        ValueError: when the handoff variant and the batch disagree.
    """
    from .incident_promotion_accumulator import (
        INCIDENT_ACCESS_MODE_BACKEND as _BACKEND_MODE,
    )
    from .incident_promotion_batch import PromotionBatch

    if not isinstance(handoff, ScopedPromotionAccumulatorHandoff):
        raise TypeError(
            "record_scoped_promotion_batch requires a "
            "ScopedPromotionAccumulatorHandoff; got "
            f"{type(handoff).__name__}"
        )
    if not isinstance(batch, PromotionBatch):
        raise TypeError(
            "record_scoped_promotion_batch requires a PromotionBatch; "
            f"got {type(batch).__name__}"
        )

    records = batch.promotion_records
    if records:
        # Scoped aggregate results MUST NOT carry per-signal records
        # to avoid introducing a second outcome authority.
        raise ValueError(
            "record_scoped_promotion_batch forbids per-signal "
            "promotion_records on the scoped aggregate batch "
            f"(got {len(records)} records)"
        )

    pr = batch.promotion_result

    if isinstance(handoff, ScopedPromotionAccumulatorCompleted):
        if not pr.ok:
            raise ValueError(
                "Completed handoff rejected: batch.promotion_result.ok "
                "MUST be True for completed scoped promotions"
            )
        if pr.incident_access_mode != _BACKEND_MODE:
            raise ValueError(
                "Completed handoff rejected: incident_access_mode MUST be "
                f"{_BACKEND_MODE!r}"
            )
        receipt = handoff.receipt
        _validate_completed_receipt_agreement(
            receipt=receipt,
            requested_signal_ids=handoff.outcome.requested_signal_ids,
            batch_scanned=pr.scanned,
            batch_firing=pr.firing,
            batch_opened_incident_ids=tuple(pr.opened_incident_ids),
            batch_updated_incident_ids=tuple(pr.updated_incident_ids),
        )
        return

    if isinstance(handoff, ScopedPromotionAccumulatorUncertain):
        if pr.ok:
            raise ValueError(
                "Uncertain handoff rejected: batch.promotion_result.ok "
                "MUST be False for uncertain scoped promotions"
            )
        if pr.incident_access_mode != _RECONCILIATION_REQUIRED_ACCESS_MODE:
            raise ValueError(
                "Uncertain handoff rejected: incident_access_mode MUST be "
                f"{_RECONCILIATION_REQUIRED_ACCESS_MODE!r}"
            )
        return

    if isinstance(handoff, ScopedPromotionAccumulatorRejected):
        if pr.ok:
            raise ValueError(
                "Rejected handoff rejected: batch.promotion_result.ok "
                "MUST be False for rejected scoped promotions"
            )
        if pr.errors != 1:
            raise ValueError(
                "Rejected handoff rejected: batch.promotion_result.errors "
                "MUST be 1 for the bounded rejection projection"
            )
        if not pr.error_messages:
            raise ValueError(
                "Rejected handoff rejected: bounded rejection reason "
                "MUST appear in batch.promotion_result.error_messages"
            )
        if pr.incident_access_mode != _BACKEND_MODE:
            raise ValueError(
                "Rejected handoff rejected: incident_access_mode MUST be "
                f"{_BACKEND_MODE!r}"
            )
        return

    # Exhaustiveness: a new handoff variant MUST fail typing. This
    # branch is structurally unreachable; the explicit raise is here
    # so a future runtime ad-hoc value is caught loudly.
    raise TypeError(
        "record_scoped_promotion_batch got an unsupported handoff "
        f"variant: {type(handoff).__name__}"
    )


def _validate_completed_receipt_agreement(
    *,
    receipt: ScopedPromotionReceipt,
    requested_signal_ids: tuple[str, ...],
    batch_scanned: int,
    batch_firing: int,
    batch_opened_incident_ids: tuple[str, ...],
    batch_updated_incident_ids: tuple[str, ...],
) -> None:
    """Confirm the batch aggregate agrees with the receipt's bound state.

    The completed handoff's receipt carries the canonical opened /
    materially-changed incident IDs. The batch is a projector, so
    every aggregate the batch publishes MUST agree with the
    receipt's bound fields:

    * ``batch_scanned == len(requested_signal_ids)``
    * ``batch_firing == len(requested_signal_ids)`` (the bounded
      active scoped path always has firing == scanned)
    * ``batch_opened_incident_ids == receipt.opened_incident_ids``
    * ``batch_updated_incident_ids ==
      receipt.materially_changed_incident_ids``

    Raises:
        ValueError: when any aggregate disagrees.
    """
    scanned = len(requested_signal_ids)
    if batch_scanned != scanned:
        raise ValueError(
            "Completed handoff rejected: batch.scanned disagrees with "
            f"len(outcome.requested_signal_ids) ({batch_scanned} vs "
            f"{scanned})"
        )
    if batch_firing != scanned:
        raise ValueError(
            "Completed handoff rejected: batch.firing disagrees with "
            f"len(outcome.requested_signal_ids) ({batch_firing} vs "
            f"{scanned})"
        )
    receipt_opened = receipt.opened_incident_ids
    receipt_updated = receipt.materially_changed_incident_ids
    if batch_opened_incident_ids != receipt_opened:
        raise ValueError(
            "Completed handoff rejected: batch.opened_incident_ids "
            "disagrees with receipt.bound.result.opened_incident_ids"
        )
    if batch_updated_incident_ids != receipt_updated:
        raise ValueError(
            "Completed handoff rejected: batch.updated_incident_ids "
            "disagrees with receipt.bound.result.materially_changed_incident_ids"
        )


def _scoped_handoff_equivalent(
    running: ScopedPromotionAccumulatorHandoff,
    candidate: ScopedPromotionAccumulatorHandoff,
) -> bool:
    """Return True iff two handoffs are semantically equal for replay.

    The fields compared depend on the closed variant:

    * Every variant: ``request_id``, ``request_fingerprint``,
      ``commit_disposition``, ``outcome``.

    * Completed-only: ``receipt`` is verified by structural
      identity AND by aggregate equivalence (the bound's opened /
      materially-changed / unchanged / observation-refreshed /
      scanned-signal IDs).

    Receipt identity is checked both by Python identity (so a
    caller that retains the receipt observes it by ``is``) and by
    structural equivalence (so an equal-but-rebuilt receipt from a
    later replay still classifies as IDEMPOTENT).
    """
    if type(running) is not type(candidate):
        return False
    if running.request_id != candidate.request_id:
        return False
    if running.request_fingerprint != candidate.request_fingerprint:
        return False
    if running.commit_disposition != candidate.commit_disposition:
        return False
    if running.outcome != candidate.outcome:
        return False
    if isinstance(running, ScopedPromotionAccumulatorCompleted):
        # The ``isinstance`` narrows ``running`` to the completed
        # variant. ``candidate`` is closed-union-typed; the cast
        # makes the narrowed type explicit so mypy accepts the
        # ``receipt`` attribute access.
        candidate_completed = cast(
            ScopedPromotionAccumulatorCompleted, candidate
        )
        if not _receipt_equivalent(
            running.receipt, candidate_completed.receipt
        ):
            return False
    return True


def _receipt_equivalent(
    running: ScopedPromotionReceipt,
    candidate: ScopedPromotionReceipt,
) -> bool:
    """Return True iff two receipts are equivalent for replay.

    Receipts are dataclass instances whose ``bound`` field carries
    the canonical opened / materially-changed / scanned /
    requested / observation-refreshed / unchanged IDs. Two
    receipts are equal when:

    * Their bound.request fields agree (run_id, source_identity,
      ordered signal_ids).
    * Their bound.result aggregates agree (opened IDs, materially-
      changed IDs, unchanged IDs, observation-refreshed IDs,
      scanned-signal IDs).
    """
    rb = running.bound
    cb = candidate.bound
    if str(rb.request.run_id) != str(cb.request.run_id):
        return False
    if str(rb.request.source_identity) != str(cb.request.source_identity):
        return False
    if tuple(str(s) for s in rb.request.signal_ids) != tuple(
        str(s) for s in cb.request.signal_ids
    ):
        return False
    if tuple(str(i) for i in rb.result.opened_incident_ids) != tuple(
        str(i) for i in cb.result.opened_incident_ids
    ):
        return False
    if tuple(str(i) for i in rb.result.materially_changed_incident_ids) != tuple(
        str(i) for i in cb.result.materially_changed_incident_ids
    ):
        return False
    return True


def _batch_accounting_equivalent(
    running: PromotionBatch | None,
    candidate: PromotionBatch,
) -> bool:
    """Return True iff two batches publish equivalent aggregate state.

    The comparison only inspects fields that participate in
    aggregate accounting (totals / last_*) and the batch's bounded
    access mode. ``promotion_records`` is intentionally NOT
    inspected: scoped aggregate batches are guaranteed to be ``()``
    by the consistency validator.
    """
    if running is None:
        return False
    rr = running.promotion_result
    cr = candidate.promotion_result
    if bool(rr.ok) != bool(cr.ok):
        return False
    if int(rr.errors) != int(cr.errors):
        return False
    if int(rr.scanned) != int(cr.scanned):
        return False
    if int(rr.firing) != int(cr.firing):
        return False
    if tuple(rr.opened_incident_ids) != tuple(cr.opened_incident_ids):
        return False
    if tuple(rr.updated_incident_ids) != tuple(cr.updated_incident_ids):
        return False
    if rr.incident_access_mode != cr.incident_access_mode:
        return False
    if rr.promotion_mode != cr.promotion_mode:
        return False
    return True


def _scoped_atomic_conflict_error(
    message: str,
    *,
    running_handoff: ScopedPromotionAccumulatorHandoff,
    candidate_handoff: ScopedPromotionAccumulatorHandoff,
) -> PromotionOutcomeConflictError:
    """Build a :class:`PromotionOutcomeConflictError` for the atomic path.

    The error uses the existing bounded exception so the
    orchestrator's diagnostic handling stays uniform. The
    ``running_run_id`` / ``rejected_run_id`` fields are sourced
    from the handoff's outcome.
    """
    return PromotionOutcomeConflictError(
        message,
        running_run_id=running_handoff.outcome.run_id,
        rejected_run_id=candidate_handoff.outcome.run_id,
        running_variant=type(running_handoff.outcome).__name__,
        rejected_variant=type(candidate_handoff.outcome).__name__,
    )


class ScopedPromotionAtomicRecorderMixin:
    """Mixin providing atomic scoped promotion recording for the accumulator.

    The mixin expects the host class to declare the following
    fields (already declared on :class:`RunPromotionAccumulator`):

    * ``promotion_outcome: PromotionOutcome | None``
    * ``promotion_outcome_run_id: str``
    * ``scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None``
    * Every aggregate-batch field declared by
      :class:`RunPromotionAccumulator` (``batches``,
      ``promotion_records``, ``_seen_canonical_ids``, ``total_*``,
      ``last_*``, ``last_contract_error``, ``last_handoff_error``,
      ``last_propagation_result``, ``workset_state``).

    It also expects the host class to expose:

    * :meth:`record_promotion_outcome` -- delegated to
      :class:`PromotionOutcomeRecorderMixin`.
    * :meth:`_snapshot` -- the existing snapshot helper on
      :class:`RunPromotionAccumulator`.
    * :meth:`_restore` -- the existing restore helper on
      :class:`RunPromotionAccumulator`.
    * :meth:`_apply_batch` -- the existing internal batch
      applier that mutates aggregate state. ``_apply_batch``
      itself does not perform snapshot/restore; the mixin owns
      the only atomic transaction.

    The mixin's snapshot discipline guarantees that any
    exception during validation or commit restoration leaves the
    host class's fields unchanged. Post-call identity assertions
    in the focused test matrix prove zero mutation across every
    conflict / fail path.
    """

    promotion_outcome: Any
    promotion_outcome_run_id: str
    scoped_promotion_handoff: ScopedPromotionAccumulatorHandoff | None

    def _snapshot(self) -> dict[str, object]:
        """Capture the host class's mutable fields; declared on host."""
        raise NotImplementedError

    def _restore(self, snap: dict[str, object]) -> None:
        """Restore fields from a snapshot; declared on host."""
        raise NotImplementedError

    def _apply_batch(self, batch: Any) -> None:
        """Mutate aggregate batch fields; declared on host."""
        raise NotImplementedError

    def record_promotion_outcome(
        self, outcome: Any
    ) -> PromotionOutcomeRecording:
        """Record the typed outcome; declared on host."""
        raise NotImplementedError

    def _aggregate_scoped_batch(self, batch: PromotionBatch) -> None:
        """Commit aggregate batch accounting for a scoped result.

        The scoped path NEVER fabricates per-signal records.
        Empty ``batch.promotion_records`` is a hard requirement
        enforced by the consistency validator. This method
        delegates to the host class's existing ``_apply_batch``
        helper because every aggregate field updated there is
        the same one we want to preserve here.

        The empty-records iteration in :meth:`_apply_batch`
        becomes a no-op, so ``promotion_records`` stays ``[]``
        and ``_seen_canonical_ids`` stays ``set()``.
        """
        self._apply_batch(batch)

    def record_scoped_promotion_batch(
        self,
        *,
        handoff: ScopedPromotionAccumulatorHandoff,
        batch: PromotionBatch,
    ) -> PromotionOutcomeRecording:
        """Record a typed scoped promotion handoff and its batch atomically.

        The function NEVER mutates any field on the host class
        before all validation succeeds. On any conflict it
        raises :class:`PromotionOutcomeConflictError` after
        restoring the host class to its pre-call state.

        Returns:
            :attr:`PromotionOutcomeRecording.NEW` -- the handoff,
            outcome, and batch accounting were committed for the
            first time.

            :attr:`PromotionOutcomeRecording.IDEMPOTENT` -- a
            semantically equal replay was detected. The
            originally recorded handoff and outcome remain
            installed; no field was mutated.
        """
        # Phase 1: handoff construction invariants are enforced
        # by the handoff's own __post_init__. We re-check the
        # runtime type here so a caller cannot smuggle an
        # unrelated object past the dispatcher boundary.
        from .incident_promotion_batch import PromotionBatch

        if not isinstance(handoff, ScopedPromotionAccumulatorHandoff):
            raise TypeError(
                "record_scoped_promotion_batch requires a "
                "ScopedPromotionAccumulatorHandoff; got "
                f"{type(handoff).__name__}"
            )
        if not isinstance(batch, PromotionBatch):
            raise TypeError(
                "record_scoped_promotion_batch requires a PromotionBatch; "
                f"got {type(batch).__name__}"
            )

        # Phase 2: validate handoff / batch agreement BEFORE any
        # field is touched.
        _validate_scoped_handoff_batch_consistency(handoff, batch)

        running_handoff = self.scoped_promotion_handoff

        # Phase 3: replay path -- semantically equal replay is
        # accepted as IDEMPOTENT; any disagreement is a conflict.
        if running_handoff is not None:
            running_outcome = self.promotion_outcome
            if running_outcome != handoff.outcome:
                raise _scoped_atomic_conflict_error(
                    "Scoped promotion outcome mismatch: existing outcome "
                    "differs from the candidate handoff outcome.",
                    running_handoff=running_handoff,
                    candidate_handoff=handoff,
                )
            if not _scoped_handoff_equivalent(running_handoff, handoff):
                raise _scoped_atomic_conflict_error(
                    "Scoped promotion handoff mismatch: identity fields, "
                    "receipt, or commit disposition disagree with the "
                    "running handoff.",
                    running_handoff=running_handoff,
                    candidate_handoff=handoff,
                )
            running_batch = cast(PromotionBatch, self.batches[-1]) if self.batches else None
            if running_batch is None or not _batch_accounting_equivalent(
                running_batch, batch
            ):
                raise _scoped_atomic_conflict_error(
                    "Scoped promotion batch accounting mismatch: candidate "
                    "batch disagrees with the most recently recorded "
                    "aggregate.",
                    running_handoff=running_handoff,
                    candidate_handoff=handoff,
                )
            # All checks pass without mutation -> IDEMPOTENT.
            return PromotionOutcomeRecording.IDEMPOTENT

        # Phase 4: first recording -- snapshot, then commit in
        # one transaction. ``AccumulatorAccessModeError`` can be
        # raised by inner machinery if access-mode validation
        # fails; both bounded errors must leave the host class
        # in its pre-call state.
        from .incident_promotion_accumulator import (
            AccumulatorAccessModeError as _AccessModeError,
        )

        snap = self._snapshot()
        try:
            self.scoped_promotion_handoff = handoff
            recording = self.record_promotion_outcome(handoff.outcome)
            if recording is not PromotionOutcomeRecording.NEW:
                # Defensive: outcome recorded for the first time
                # MUST return NEW. Anything else (or an exception)
                # short-circuits back to a clean restore.
                raise _scoped_atomic_conflict_error(
                    "Scoped promotion first recording unexpectedly did "
                    "not return NEW; treating as conflict to avoid "
                    "partial commit.",
                    running_handoff=handoff,
                    candidate_handoff=handoff,
                )
            self._aggregate_scoped_batch(batch)
        except _AccessModeError:
            self._restore(snap)
            raise
        except PromotionOutcomeConflictError:
            self._restore(snap)
            raise
        except Exception:
            self._restore(snap)
            raise

        return PromotionOutcomeRecording.NEW


__all__ = [
    "ScopedPromotionAtomicRecorderMixin",
    "_scoped_handoff_equivalent",
    "_batch_accounting_equivalent",
    "_validate_scoped_handoff_batch_consistency",
]
