"""Replay-conflict field tests -- handoff identity and variant mismatches.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.
ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION05-
STRICT-TYPING-AND-ROLLBACK-CLOSURE01.

Split out of the original
:mod:`test_scoped_accumulator_replay_conflicts` matrix (CORRECTION05
file-size guard).

This module covers three replay-conflict shapes:

* **Request identity conflicts** -- a candidate handoff with a
  different ``request_id`` or ``request_fingerprint``.
* **Receipt conflicts** -- a candidate handoff whose receipt
  does not agree with the original outcome's
  ``diagnosis_incident_ids`` (rejected at construction time by
  :class:`ScopedPromotionAccumulatorCompleted`'s
  ``__post_init__``).
* **Variant-change conflicts** -- a candidate handoff whose
  closed-union variant does not match the running variant
  (completed -> uncertain, completed -> rejected,
  uncertain -> rejected).
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionReceipt,
)
from tests.unit.scoped_handoff_atomic_support import (
    _make_bound,
    completed_handoff,
    make_completed_batch,
    make_completed_projection,
    rejected_handoff,
    uncertain_handoff,
)


def _seed_completed(acc: RunPromotionAccumulator) -> None:
    """Seed the accumulator with a completed handoff/batch."""
    handoff = completed_handoff(
        diagnosis_incident_ids=("canonical-conflict",),
    )
    batch = make_completed_batch(handoff=handoff)
    recording = acc.record_scoped_promotion_batch(
        handoff=handoff, batch=batch
    )
    assert recording is PromotionOutcomeRecording.NEW


class TestHandoffRequestIdentityReplayConflict:
    """Request id / fingerprint mismatches on the candidate handoff."""

    def test_conflicting_request_id_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        base = make_completed_projection(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        new_handoff = ScopedPromotionAccumulatorCompleted(
            outcome=base.promotion_outcome,
            receipt=base.aggregate_receipt,
            request_id="different-request-id-still-canonical",
            request_fingerprint="a" * 64,
        )
        new_batch = make_completed_batch(handoff=new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_conflicting_request_fingerprint_raises_conflict(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        base = make_completed_projection(
            diagnosis_incident_ids=("canonical-conflict",)
        )
        different_fp_handoff = ScopedPromotionAccumulatorCompleted(
            outcome=base.promotion_outcome,
            receipt=base.aggregate_receipt,
            request_id=base.request_id,
            request_fingerprint="e" * 64,
        )
        different_fp_batch = make_completed_batch(
            handoff=different_fp_handoff
        )
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=different_fp_handoff,
                batch=different_fp_batch,
            )


class TestReceiptReplayConflict:
    """Receipt-level conflicts must be caught by ``_receipt_equivalent``.

    The closed-union ``__post_init__`` validator rejects mismatched
    receipt/outcome contracts at construction time (with
    :class:`ValueError`). The recorder is therefore protected
    against receipt conflicts before the equivalence check ever
    runs. The test pins the upstream rejection.
    """

    def test_receipt_opened_ids_mismatch_rejected_at_construction(
        self,
    ) -> None:
        outcome = make_completed_projection(
            diagnosis_incident_ids=("canonical-receipt-x",)
        ).promotion_outcome
        wrong_bound = _make_bound(
            run_id=outcome.run_id,
            requested_signal_ids=outcome.requested_signal_ids,
            diagnosis_incident_ids=("canonical-receipt-y",),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="diagnosis_incident_ids"):
            ScopedPromotionAccumulatorCompleted(
                outcome=outcome,
                receipt=wrong_receipt,
                request_id=outcome.run_id,
                request_fingerprint="a" * 64,
            )


class TestVariantChangeConflict:
    """A replay that switches the closed-union variant is a conflict."""

    def test_completed_to_uncertain_raises(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = uncertain_handoff(
            requested_signal_ids=tuple(
                f"sig-{i:02d}" for i in range(5)
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_completed_to_rejected_raises(self) -> None:
        acc = RunPromotionAccumulator()
        _seed_completed(acc)

        new_handoff = rejected_handoff(
            requested_signal_ids=tuple(
                f"sig-{i:02d}" for i in range(5)
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )

    def test_uncertain_to_rejected_raises(self) -> None:
        acc = RunPromotionAccumulator()
        uncertain = uncertain_handoff()
        acc.record_scoped_promotion_batch(
            handoff=uncertain,
            batch=build_compatibility_batch_from_handoff(uncertain),
        )
        new_handoff = rejected_handoff(
            requested_signal_ids=tuple(
                f"sig-{i:02d}" for i in range(5)
            ),
        )
        new_batch = build_compatibility_batch_from_handoff(new_handoff)
        with pytest.raises(PromotionOutcomeConflictError):
            acc.record_scoped_promotion_batch(
                handoff=new_handoff, batch=new_batch
            )