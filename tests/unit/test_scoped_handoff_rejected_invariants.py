"""Rejected-handoff invariants for the atomic scoped recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

This matrix exercises the closed rejected variant
(:class:`ScopedPromotionAccumulatorRejected`). The handoff
carries the original ``PromotionRejected`` outcome by identity;
no receipt is structurally possible on this variant.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorRejected,
)
from tests.unit.scoped_handoff_atomic_support import (
    rejected_handoff,
)

# ---------------------------------------------------------------------------
# Construction invariants on the closed Rejected variant
# ---------------------------------------------------------------------------


class TestRejectedHandoffConstructionRejections:
    """Rejected handoffs only accept ``PromotionRejected`` outcomes."""

    def test_rejected_rejects_wrong_outcome_type(self) -> None:
        handoff = rejected_handoff()
        wrong_outcome = PromotionSucceeded(
            run_id=handoff.outcome.run_id,
            requested_signal_ids=handoff.outcome.rejected_signal_ids,
            records=(),
            diagnosis_incident_ids=(),
        )
        with pytest.raises(TypeError):
            ScopedPromotionAccumulatorRejected(
                outcome=wrong_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_rejected_rejects_commit_unknown_outcome(self) -> None:
        handoff = rejected_handoff()
        bad_outcome = PromotionCommitUnknown(
            run_id=handoff.outcome.run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            ),
            requested_signal_ids=handoff.outcome.rejected_signal_ids,
        )
        with pytest.raises(TypeError):
            ScopedPromotionAccumulatorRejected(
                outcome=bad_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Closed union: only ``PromotionRejected`` outcomes survive the gate.
# ---------------------------------------------------------------------------


class TestRejectedOutcomeFamily:
    """``PromotionRejected`` is the sole outcome family accepted on this variant."""

    def test_rejected_with_valid_rejection_reason_is_accepted(self) -> None:
        outcome = PromotionRejected(
            run_id="run-corr03-rejected-valid",
            reason=PromotionRejectionCode.BACKEND_UNREACHABLE,
            rejected_signal_ids=("sig-a", "sig-b"),
        )
        handoff = ScopedPromotionAccumulatorRejected(
            outcome=outcome,
            request_id="promotion-request-rejected-correction03",
            request_fingerprint="c" * 64,
        )
        assert handoff.outcome is outcome

    def test_rejected_zero_length_rejected_signal_ids_accepted(self) -> None:
        """A zero-rejection handoff is structurally valid for the closed variant."""
        outcome = PromotionRejected(
            run_id="run-corr03-rejected-empty",
            reason=PromotionRejectionCode.CONTRACT_VIOLATION,
            rejected_signal_ids=(),
        )
        handoff = ScopedPromotionAccumulatorRejected(
            outcome=outcome,
            request_id="promotion-request-rejected-correction03",
            request_fingerprint="c" * 64,
        )
        assert handoff.outcome.rejected_signal_ids == ()


# ---------------------------------------------------------------------------
# Atomic-recording truth for the rejected variant
# ---------------------------------------------------------------------------


class TestRejectedAtomicRecording:
    """Rejected handoffs commit the typed outcome by identity."""

    def test_rejected_handoff_records_typed_outcome(self) -> None:
        handoff = rejected_handoff()
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert acc.promotion_outcome is handoff.outcome
        assert acc.scoped_promotion_handoff is handoff

    def test_rejected_records_empty_records_tuple(self) -> None:
        """Rejected handoffs MUST NOT fabricate per-signal records."""
        handoff = rejected_handoff()
        acc = RunPromotionAccumulator()
        batch = build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        assert acc.promotion_records == []

    def test_rejected_bounded_error_is_carried(self) -> None:
        handoff = rejected_handoff()
        batch = build_compatibility_batch_from_handoff(handoff)
        assert batch.promotion_result.errors == 1
        assert batch.promotion_result.error_messages == (
            handoff.outcome.reason.value,
        )


# ---------------------------------------------------------------------------
# Documentation correction
# ---------------------------------------------------------------------------


def test_rejected_docs_note_canonical_request_only() -> None:
    """The current rejected handoff validates outcome type and identity.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
    CORRECTION03: the rejected variant does NOT independently
    verify the outcome's run or rejected signal scope unless a
    canonical request is added to the handoff. This test pins the
    current contract: identity + outcome type enforcement only.
    """
    # Concretely: a rejected handoff whose outcome's rejected_signal_ids
    # only partially match a hypothetical canonical request is
    # accepted by the current constructor. The richer invariant
    # belongs to the future canonical-request fingerprint work.
    outcome = PromotionRejected(
        run_id="run-corr03-sparse",
        reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
        rejected_signal_ids=("sig-a",),
    )
    handoff = ScopedPromotionAccumulatorRejected(
        outcome=outcome,
        request_id="promotion-request-rejected-correction03",
        request_fingerprint="c" * 64,
    )
    assert handoff.outcome.rejected_signal_ids == ("sig-a",)
