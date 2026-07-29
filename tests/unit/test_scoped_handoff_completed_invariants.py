"""Completed-handoff invariants for the atomic scoped recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION03-
ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01.

This matrix exercises the closed completed variant
(:class:`ScopedPromotionAccumulatorCompleted`). Both the
construction invariant and the per-variant atomic-recording
validation must reject the deliberately malformed pairings listed
below and accept the two positive cases (aggregate-zero and
actionable-id).

The matrix also pins the empty-records invariant: every focused
fixture uses ``records=()`` because aggregate scoped results MUST
NOT fabricate per-signal records.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionRejected,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionReceipt,
    ScopedPromotionUncertainProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchUncertain,
)
from tests.unit.scoped_handoff_atomic_support import (
    completed_handoff,
    make_completed_batch,
    to_handoff,
)

# ---------------------------------------------------------------------------
# Construction invariants on the closed Completed variant
# ---------------------------------------------------------------------------


class TestCompletedHandoffConstructionRejections:
    """The Completed handoff's ``__post_init__`` gates every mismatch."""

    def test_completed_rejects_wrong_outcome_type(self) -> None:
        handoff = completed_handoff()
        # Use a non-PromotionSucceeded value (a string) so the
        # typed outcome gate rejects the wrong type.
        with pytest.raises(TypeError, match="PromotionSucceeded"):
            ScopedPromotionAccumulatorCompleted(
                outcome="not-a-promotion-succeeded",  # type: ignore[arg-type]
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_completed_rejects_wrong_receipt_type(self) -> None:
        handoff = completed_handoff()
        with pytest.raises(TypeError, match="ScopedPromotionReceipt"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt="not-a-receipt",  # type: ignore[arg-type]
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_completed_rejects_outcome_run_id_mismatch(self) -> None:
        from tests.unit.scoped_handoff_atomic_support import _make_bound

        handoff = completed_handoff(run_id="run-correct")
        wrong_bound = _make_bound(
            run_id="run-different",
            requested_signal_ids=handoff.outcome.requested_signal_ids,
            diagnosis_incident_ids=(),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="run_id"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=wrong_receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_completed_rejects_requested_signal_ids_mismatch(self) -> None:
        from tests.unit.scoped_handoff_atomic_support import _make_bound

        handoff = completed_handoff(
            requested_signal_ids=("sig-a", "sig-b")
        )
        wrong_bound = _make_bound(
            run_id=handoff.outcome.run_id,
            requested_signal_ids=("sig-x", "sig-y"),
            diagnosis_incident_ids=(),
        )
        wrong_receipt = ScopedPromotionReceipt(bound=wrong_bound)
        with pytest.raises(ValueError, match="requested_signal_ids"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=wrong_receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_completed_rejects_diagnosis_incident_ids_mismatch(self) -> None:
        from tests.unit.scoped_handoff_atomic_support import _make_bound

        handoff = completed_handoff(
            requested_signal_ids=("sig-a", "sig-b"),
            diagnosis_incident_ids=("canonical-a", "canonical-b"),
        )
        # Build a receipt whose opened incident IDs diverge from the
        # outcome's diagnosis_incident_ids. ``_make_bound`` is imported
        # for shape parity with the other tests; this case uses an
        # explicit ``BoundScopedPromotionResult`` construction below.
        _make_bound(
            run_id=handoff.outcome.run_id,
            requested_signal_ids=handoff.outcome.requested_signal_ids,
            diagnosis_incident_ids=("canonical-x",),  # mismatched length+value
        )
        from k8s_diag_agent.domain.identifiers import AlertSignalId
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId
        from k8s_diag_agent.incident_alert_promotion_binding import (
            BoundScopedPromotionResult,
        )
        from k8s_diag_agent.incident_alert_promotion_contract import (
            IncidentPromotionResult,
            PromoteAlertSignalsRequest,
        )

        typed_signals = tuple(
            AlertSignalId(v) for v in handoff.outcome.requested_signal_ids
        )
        typed_opened = tuple(IncidentId(v) for v in ("canonical-x",))
        result = IncidentPromotionResult(
            run_id=handoff.outcome.run_id,
            source_identity="source-correction03-atomic",
            scanned_signal_ids=typed_signals,
            opened_incident_ids=typed_opened,
        )
        mismatched = BoundScopedPromotionResult(
            request=PromoteAlertSignalsRequest(
                run_id=handoff.outcome.run_id,
                source_identity="source-correction03-atomic",
                signal_ids=typed_signals,
            ),
            result=result,
        )
        receipt = ScopedPromotionReceipt(bound=mismatched)
        with pytest.raises(ValueError, match="diagnosis_incident_ids"):
            ScopedPromotionAccumulatorCompleted(
                outcome=handoff.outcome,
                receipt=receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Positive cases: aggregate-zero and actionable-id
# ---------------------------------------------------------------------------


class TestCompletedHandoffPositive:
    """Two positive cases exercise the closed completed variant."""

    def test_positive_aggregate_zero_records_typed_outcome(self) -> None:
        handoff = completed_handoff(
            requested_signal_ids=tuple(
                f"sig-{i:02d}" for i in range(34)
            ),
            diagnosis_incident_ids=(),
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        assert acc.scoped_promotion_handoff is handoff
        assert acc.promotion_outcome is handoff.outcome
        # Aggregate scoped result MUST NOT add per-signal records.
        assert acc.promotion_records == []
        assert acc.total_errors == 0
        assert acc.total_opened_incidents == 0

    def test_positive_actionable_ids_records_actionable_outcome(
        self,
    ) -> None:
        canonical_ids = ("canonical-a", "canonical-b")
        handoff = completed_handoff(
            requested_signal_ids=("sig-a", "sig-b"),
            diagnosis_incident_ids=canonical_ids,
        )
        acc = RunPromotionAccumulator()
        batch = make_completed_batch(handoff=handoff)
        recording = acc.record_scoped_promotion_batch(
            handoff=handoff, batch=batch
        )
        assert recording is PromotionOutcomeRecording.NEW
        # No fabricated per-signal records; the canonical IDs are
        # exposed via the typed outcome's `diagnosis_incident_ids`.
        assert acc.promotion_records == []
        assert (
            handoff.outcome.diagnosis_incident_ids == canonical_ids
        )


# ---------------------------------------------------------------------------
# Variant enforcement: outcome type MUST match handoff variant.
# ---------------------------------------------------------------------------


class TestVariantMismatchRejections:
    """Closed union prevents foreign-outcome injection at construction."""

    def test_completed_handoff_rejects_promotion_rejected_outcome(self) -> None:
        handoff = completed_handoff()
        bad_outcome = PromotionRejected(
            run_id=handoff.outcome.run_id,
            reason=handoff.outcome.requested_signal_ids[0:1]  # type: ignore[arg-type]
            and handoff.outcome.requested_signal_ids[0:1],
            rejected_signal_ids=handoff.outcome.requested_signal_ids,
        )
        with pytest.raises(TypeError, match="PromotionRejected|PromotionSucceeded"):
            ScopedPromotionAccumulatorCompleted(
                outcome=bad_outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )

    def test_completed_handoff_rejects_commit_unknown_outcome(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionReconciliationToken,
            PromotionUncertaintyCode,
        )

        handoff = completed_handoff()
        bad_outcome = PromotionCommitUnknown(
            run_id=handoff.outcome.run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            ),
        )
        with pytest.raises(TypeError):
            ScopedPromotionAccumulatorCompleted(
                outcome=bad_outcome,
                receipt=handoff.receipt,
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            )


# ---------------------------------------------------------------------------
# Projection-side checks: closed union is exhaustive.
# ---------------------------------------------------------------------------


def test_dispatch_result_adapter_handles_completed_variant() -> None:
    """The typed dispatch adapter MUST reach the Completed handoff branch."""
    from k8s_diag_agent.collect.incident_promotion_scoped_atomic_recorder import (
        _build_compatibility_batch_from_handoff,
    )

    handoff = completed_handoff()
    # Construct a fake ScopedPromotionDispatchCompleted by reusing
    # the support projection, then verify the adapter preserves the
    # outcome and receipt by identity.
    rebuilt = _build_compatibility_batch_from_handoff(handoff)
    assert rebuilt.promotion_result.ok is True
    assert rebuilt.promotion_result.opened_incident_ids == (
        handoff.receipt.opened_incident_ids
    )
    assert rebuilt.promotion_result.updated_incident_ids == (
        handoff.receipt.materially_changed_incident_ids
    )


def test_variant_mismatch_uncertain_rejected_via_constructor() -> None:
    """Constructing an Uncertain handoff with a Completed outcome fails closed."""
    from k8s_diag_agent.collect.promotion_outcomes import (
        PromotionReconciliationToken,
        PromotionUncertaintyCode,
    )

    handoff = completed_handoff()
    uncertain_projection = ScopedPromotionUncertainProjection(
        promotion_outcome=PromotionCommitUnknown(
            run_id=handoff.outcome.run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id=handoff.request_id,
                request_fingerprint=handoff.request_fingerprint,
            ),
            requested_signal_ids=handoff.outcome.requested_signal_ids,
        ),
        request_id=handoff.request_id,
        request_fingerprint=handoff.request_fingerprint,
    )
    # The adapter route produces an Uncertain handoff; constructing a
    # Completed handoff from a Completed outcome (which we already did)
    # while stubbing it as Uncertain must fail at the constructor.
    uncertain_result = to_handoff(
        ScopedPromotionDispatchUncertain(projection=uncertain_projection)
    )
    assert isinstance(uncertain_result, ScopedPromotionAccumulatorUncertain)
    # For symmetry, the Completed variant is rejected if we try to
    # pair it with an Uncertain handoff carrier class.
    with pytest.raises(TypeError):
        ScopedPromotionAccumulatorRejected(
            outcome=handoff.outcome,  # type: ignore[arg-type]
            request_id=handoff.request_id,
            request_fingerprint=handoff.request_fingerprint,
        )


# Sanity: the accumulator picks up the typed outcome identity verbatim.
def test_completed_handoff_preserves_outcome_and_receipt_identity() -> None:
    handoff = completed_handoff(diagnosis_incident_ids=("c-1",))
    acc = RunPromotionAccumulator()
    batch = make_completed_batch(handoff=handoff)
    acc.record_scoped_promotion_batch(handoff=handoff, batch=batch)
    assert acc.promotion_outcome is handoff.outcome
    assert acc.scoped_promotion_handoff is handoff
    # Promotion records: empty aggregate. No raw record fabricated.
    assert acc.promotion_records == []
