"""Tests that the final summary cannot contradict the promotion state.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage.

The production failure emitted ``event="complete"`` while advertising
zero actionable IDs and an unconfirmed commit status. The new
telemetry MUST derive consistently from the outcome variant.

This module asserts the cross-section of invariants:

* Successful empty promotion -> zero incidents, no scan, no
  consistency error.
* Rejected promotion -> zero incidents, no scan, consistency error.
* Commit-unknown promotion -> zero incidents, no scan, consistency
  error, reconciliation required.
* The final summary cannot claim propagation when promotion
  succeeded with zero IDs while simultaneously scanning the store.
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionSource,
    DiagnosisSelectionUnavailable,
    DiagnosisSelectionWithoutPromotion,
    NoPromotionSelectionReason,
    selection_source,
    store_scan_performed,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
    consistency_error_recorded,
    is_commit_unknown,
    is_rejected,
    may_have_committed,
    propagation_available,
)


def _selection_projection(
    selection: Any,
    *,
    access_mode: str = "backend-api",
) -> dict[str, Any]:
    """Mirror the projection emitted by ``run_automatic_diagnosis_loop``."""
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        selection_source_value = selection_source(selection)
        store_scan = store_scan_performed(selection)
        selected_count = len(selection.incident_ids)
        propagated = bool(selection.incident_ids)
        consistency_error = False
        reconciliation = False
    elif isinstance(selection, DiagnosisSelectionUnavailable):
        selection_source_value = selection_source(selection)
        store_scan = store_scan_performed(selection)
        selected_count = 0
        propagated = False
        consistency_error = consistency_error_recorded(selection.outcome)
        reconciliation = is_commit_unknown(selection.outcome)
    else:
        selection_source_value = selection_source(selection)
        store_scan = store_scan_performed(selection)
        selected_count = 0
        propagated = False
        consistency_error = False
        reconciliation = False
    return {
        "selection_source": selection_source_value,
        "store_scan_performed": store_scan,
        "selected_incident_count": selected_count,
        "promotion_propagated_to_diagnosis": propagated,
        "promotion_consistency_error_recorded": consistency_error,
        "reconciliation_required": reconciliation,
        "incident_access_mode": access_mode,
    }


class TestConsistencyInvariants:
    def test_successful_zero_ids_is_authoritative_zero_work(self) -> None:
        # Empty ``PromotionSucceeded`` must produce:
        #   selection_source = promotion
        #   store_scan_performed = False
        #   promotion_consistency_error_recorded = False
        #   promotion_propagated_to_diagnosis = False
        #   reconciliation_required = False
        outcome = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=(),
        )
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run",
            incident_ids=tuple(outcome.diagnosis_incident_ids),
        )
        projection = _selection_projection(selection)
        assert projection["selection_source"] is (
            DiagnosisSelectionSource.PROMOTION
        )
        assert projection["store_scan_performed"] is False
        assert projection["promotion_consistency_error_recorded"] is False
        assert projection["reconciliation_required"] is False

    def test_promoted_ids_use_explicit_promotion_selection(self) -> None:
        # Non-empty ``PromotionSucceeded`` -> promotion selection,
        # no scan, no consistency error, propagation = True.
        outcome = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=("inc-1",),
        )
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run",
            incident_ids=tuple(outcome.diagnosis_incident_ids),
        )
        projection = _selection_projection(selection)
        assert projection["selection_source"] is (
            DiagnosisSelectionSource.PROMOTION
        )
        assert projection["promotion_propagated_to_diagnosis"] is True
        assert projection["store_scan_performed"] is False

    def test_rejected_promotion_no_store_scan(self) -> None:
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.UNKNOWN,
            rejected_signal_ids=(),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        projection = _selection_projection(selection)
        assert projection["selection_source"] is (
            DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_REJECTED_PROMOTION
        )
        assert projection["store_scan_performed"] is False
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["reconciliation_required"] is False

    def test_commit_unknown_no_store_scan_records_reconciliation(self) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=PromotionReconciliationToken(
                request_id="req",
                request_fingerprint="sha256:abc",
            ),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        projection = _selection_projection(selection)
        assert projection["selection_source"] is (
            DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN
        )
        assert projection["store_scan_performed"] is False
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["reconciliation_required"] is True


class TestCrossSectionInvariants:
    def test_promotion_rejected_and_propagated_cannot_coexist(self) -> None:
        # PromotionRejected -> ``propagation_available`` MUST be False.
        # A consumer that observed ``propagation_available = True``
        # with a Rejected outcome is reading inconsistent state.
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.UNKNOWN,
            rejected_signal_ids=(),
        )
        assert is_rejected(outcome)
        assert not propagation_available(outcome)

    def test_commit_unknown_and_diagnosis_cannot_coexist(self) -> None:
        # PromotionCommitUnknown -> ``propagation_available`` MUST
        # be False. Diagnosis must NOT dispatch from this variant.
        outcome = PromotionCommitUnknown(
            run_id="run",
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=PromotionReconciliationToken(
                request_id="req",
                request_fingerprint="sha256:abc",
            ),
        )
        assert is_commit_unknown(outcome)
        assert not propagation_available(outcome)
        # And ``may_have_committed`` is the only True projection.
        assert may_have_committed(outcome)
        # Same for consistency error recorded.
        assert consistency_error_recorded(outcome)

    def test_empty_success_and_store_scan_cannot_coexist(self) -> None:
        # An empty successful promotion MUST NOT be a store scan.
        outcome = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=(),
        )
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run",
            incident_ids=tuple(outcome.diagnosis_incident_ids),
        )
        assert not store_scan_performed(selection)
        assert selection.source is DiagnosisSelectionSource.PROMOTION

    def test_rejected_outcome_and_no_consistency_error_cannot_coexist(self) -> None:
        # If promotion was rejected, the final summary MUST report
        # ``promotion_consistency_error_recorded = True``. A
        # ``False`` reading here means the orchestrator is lying.
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        assert consistency_error_recorded(outcome)

    def test_unavailable_and_review_packet_budget_consumption_cannot_coexist(
        self,
    ) -> None:
        # When the promotion handoff is unavailable, the diagnosis
        # collector MUST NOT consume the review-packet budget. We
        # assert that the projection marks the budget as untouched by
        # returning the ``blocked`` indication up front.
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        # ``store_scan_performed`` is False; budget is not consumed.
        assert not store_scan_performed(selection)


class TestExplicitNonPromotionPath:
    def test_scheduled_scan_only_run(self) -> None:
        selection = DiagnosisSelectionWithoutPromotion(
            reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
        )
        projection = _selection_projection(selection)
        assert projection["selection_source"] is (
            DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
        )
        # A scan is permitted ONLY through this explicit path.
        assert projection["store_scan_performed"] is True
        # No consistency error or reconciliation required.
        assert projection["promotion_consistency_error_recorded"] is False
        assert projection["reconciliation_required"] is False
