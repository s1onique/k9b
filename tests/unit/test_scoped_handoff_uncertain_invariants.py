"""Uncertain-handoff invariants for the atomic scoped recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

This matrix exercises the closed uncertain variant
(:class:`ScopedPromotionAccumulatorUncertain`). The handoff
carries the original ``PromotionCommitUnknown`` outcome by
identity; the reconciliation token's ``request_id`` /
``request_fingerprint`` MUST agree with the handoff's. No
receipt is structurally possible on this variant.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (
    _build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionSucceeded,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorUncertain,
)
from tests.unit.scoped_handoff_atomic_support import (
    uncertain_handoff,
)

# ---------------------------------------------------------------------------
# Construction invariants on the closed Uncertain variant
# ---------------------------------------------------------------------------


class TestUncertainHandoffConstructionRejections:
    """Uncertain handoffs MUST preserve the reconciliation token."""

    def test_uncertain_rejects_wrong_outcome_type(self) -> None:
        handoff = uncertain_handoff()
        # Use a non-PromotionCommitUnknown value so the type gate
        # rejects the wrong outcome family.
        with pytest.raises(TypeError, match="PromotionCommitUnknown"):
            ScopedPromotionAccumulatorUncertain(
                outcome="not-a-promotion-commit-unknown",  # type: ignore[arg-type]
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_uncertain_rejects_request_id_token_mismatch(self) -> None:
        handoff = uncertain_handoff()
        wrong_token = PromotionReconciliationToken(
            request_id="different-request-id",
            request_fingerprint=handoff.outcome.reconciliation_token.request_fingerprint,
        )
        bad_outcome = PromotionCommitUnknown(
            run_id=handoff.outcome.run_id,
            reason=handoff.outcome.reason,
            reconciliation_token=wrong_token,
            requested_signal_ids=handoff.outcome.requested_signal_ids,
        )
        with pytest.raises(ValueError, match="request_id"):
            ScopedPromotionAccumulatorUncertain(
                outcome=bad_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_uncertain_rejects_request_fingerprint_token_mismatch(self) -> None:
        handoff = uncertain_handoff()
        wrong_token = PromotionReconciliationToken(
            request_id=handoff.outcome.reconciliation_token.request_id,
            request_fingerprint="9" * 64,
        )
        bad_outcome = PromotionCommitUnknown(
            run_id=handoff.outcome.run_id,
            reason=handoff.outcome.reason,
            reconciliation_token=wrong_token,
            requested_signal_ids=handoff.outcome.requested_signal_ids,
        )
        with pytest.raises(ValueError, match="request_fingerprint"):
            ScopedPromotionAccumulatorUncertain(
                outcome=bad_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Reconciliation token identity preservation
# ---------------------------------------------------------------------------


class TestUncertainReconciliationIdentity:
    """Uncertain recording preserves the original reconciliation token by identity."""

    def test_reconciliation_token_survives_atomic_recording(self) -> None:
        handoff = uncertain_handoff()
        acc = RunPromotionAccumulator()
        batch = _build_compatibility_batch_from_handoff(handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        # Reconciliation identity preserved.
        assert (
            acc.promotion_outcome.reconciliation_token
            is handoff.outcome.reconciliation_token
        )

    def test_uncertain_handoff_records_typed_outcome_by_identity(self) -> None:
        handoff = uncertain_handoff()
        acc = RunPromotionAccumulator()
        batch = _build_compatibility_batch_from_handoff(handoff)
        acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
        assert acc.promotion_outcome is handoff.outcome
        assert acc.scoped_promotion_handoff is handoff


# ---------------------------------------------------------------------------
# Variant enforcement: outcome type MUST match handoff variant.
# ---------------------------------------------------------------------------


class TestUncertainVariantMismatch:
    """Wrong outcome types are caught at the constructor."""

    def test_uncertain_rejects_promotion_succeeded(self) -> None:
        handoff = uncertain_handoff()
        bad_outcome = PromotionSucceeded(
            run_id=handoff.outcome.run_id,
            requested_signal_ids=handoff.outcome.requested_signal_ids,
            records=(),
            diagnosis_incident_ids=(),
        )
        with pytest.raises(TypeError):
            ScopedPromotionAccumulatorUncertain(
                outcome=bad_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_uncertain_rejects_promotion_rejected(self) -> None:
        handoff = uncertain_handoff()
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionRejectionCode,
        )

        bad_outcome = PromotionRejected(
            run_id=handoff.outcome.run_id,
            reason=PromotionRejectionCode.BACKEND_UNREACHABLE,
            rejected_signal_ids=handoff.outcome.requested_signal_ids,
        )
        with pytest.raises(TypeError):
            ScopedPromotionAccumulatorUncertain(
                outcome=bad_outcome,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Aggregate accounting: no records, no opened/updated IDs.
# ---------------------------------------------------------------------------


def test_uncertain_atomic_recording_keeps_accumulator_intact() -> None:
    """Uncertain outcome MUST NOT add per-signal records or opened IDs."""
    handoff = uncertain_handoff()
    acc = RunPromotionAccumulator()
    batch = _build_compatibility_batch_from_handoff(handoff)
    acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
    assert acc.promotion_records == []
    assert acc.total_errors == 0
    assert acc.total_opened_incidents == 0
    assert acc.total_updated_incidents == 0


def test_uncertain_batch_carries_reconciliation_required_access_mode() -> None:
    handoff = uncertain_handoff()
    batch = _build_compatibility_batch_from_handoff(handoff)
    assert batch.promotion_result.incident_access_mode == (
        "reconciliation_required"
    )
    assert batch.promotion_result.promotion_records == ()
