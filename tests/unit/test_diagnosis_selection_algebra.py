"""Tests for the diagnosis selection algebra.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage.

The diagnosis collector must consume an explicit
:class:`DiagnosisSelection` variant from the orchestrator. The legacy
truthiness fallback (``if explicit_ids: ... else: scan()``) is
forbidden; the dispatch decision must come from the typed algebra.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.diagnosis_selection import (
    DiagnosisSelection,
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
)


class TestFromPromotion:
    def test_promotes_explicit_ids(self) -> None:
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run-1",
            incident_ids=("inc-1", "inc-2"),
        )
        assert selection.source is DiagnosisSelectionSource.PROMOTION
        assert selection.selected_incident_count == 2

    def test_zero_work_is_authoritative(self) -> None:
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run-1",
            incident_ids=(),
        )
        # Empty IDs is authoritative zero work; the collector MUST
        # NOT trigger a store scan.
        assert not store_scan_performed(selection)
        assert selection.source is DiagnosisSelectionSource.PROMOTION

    def test_run_id_required(self) -> None:
        with pytest.raises(ValueError):
            DiagnosisSelectionFromPromotion(
                promotion_run_id="",
                incident_ids=(),
            )


class TestUnavailable:
    def test_rejection_unavailable(self) -> None:
        outcome = PromotionRejected(
            run_id="run-1",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        assert selection.source is (
            DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_REJECTED_PROMOTION
        )
        assert not store_scan_performed(selection)

    def test_commit_unknown_unavailable(self) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run-1",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=PromotionReconciliationToken(
                request_id="req",
                request_fingerprint="sha256:abc",
            ),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        assert selection.source is (
            DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN
        )
        assert not store_scan_performed(selection)


class TestWithoutPromotion:
    def test_scan_only_run_with_explicit_reason(self) -> None:
        selection = DiagnosisSelectionWithoutPromotion(
            reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
        )
        assert selection.source is (
            DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
        )
        assert store_scan_performed(selection)


class TestDispatchSemantics:
    @pytest.fixture
    def variants(self) -> list[DiagnosisSelection]:
        return [
            DiagnosisSelectionFromPromotion(
                promotion_run_id="run",
                incident_ids=("inc-1",),
            ),
            DiagnosisSelectionUnavailable(
                outcome=PromotionRejected(
                    run_id="run",
                    reason=PromotionRejectionCode.UNKNOWN,
                    rejected_signal_ids=(),
                ),
            ),
            DiagnosisSelectionWithoutPromotion(
                reason=NoPromotionSelectionReason.SCHEDULED_SCAN_RUN,
            ),
        ]

    def test_non_empty_promoted_ids_use_promotion_selection(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        # FromPromotion variant always selects via promotion.
        from_promo = variants[0]
        assert isinstance(from_promo, DiagnosisSelectionFromPromotion)
        assert selection_source(from_promo) is (
            DiagnosisSelectionSource.PROMOTION
        )

    def test_empty_promoted_ids_complete_with_zero(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        zero = DiagnosisSelectionFromPromotion(
            promotion_run_id="run",
            incident_ids=(),
        )
        # Zero incidents are authoritative, NOT a store-scan trigger.
        assert zero.source is DiagnosisSelectionSource.PROMOTION
        assert not store_scan_performed(zero)

    def test_empty_promoted_ids_do_not_store_scan(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        zero = DiagnosisSelectionFromPromotion(
            promotion_run_id="run",
            incident_ids=(),
        )
        assert not store_scan_performed(zero)

    def test_rejected_does_not_store_scan(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        rejected = variants[1]
        assert isinstance(rejected, DiagnosisSelectionUnavailable)
        assert not store_scan_performed(rejected)

    def test_commit_unknown_records_reconciliation_required(
        self,
    ) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run",
            reason=PromotionUncertaintyCode.TRANSPORT_REFUSED,
            reconciliation_token=PromotionReconciliationToken(
                request_id="req",
                request_fingerprint="sha256:abc",
            ),
        )
        selection = DiagnosisSelectionUnavailable(outcome=outcome)
        assert selection.source is (
            DiagnosisSelectionSource.UNAVAILABLE_DUE_TO_COMMIT_UNKNOWN
        )

    def test_explicit_scheduled_diagnosis_still_follows_named_policy(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        explicit = variants[2]
        assert isinstance(explicit, DiagnosisSelectionWithoutPromotion)
        assert selection_source(explicit) is (
            DiagnosisSelectionSource.EXPLICIT_NON_PROMOTION
        )

    def test_store_scan_only_via_explicit_path(
        self,
        variants: list[DiagnosisSelection],
    ) -> None:
        # Only the ``DiagnosisSelectionWithoutPromotion`` variant
        # permits a store scan.
        for variant in variants:
            is_scan = store_scan_performed(variant)
            if isinstance(variant, DiagnosisSelectionWithoutPromotion):
                assert is_scan
            else:
                assert not is_scan


class TestPromotionOutcomeAlias:
    def test_succeeded_aliases_to_promotion(self) -> None:
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
        assert selection.selected_incident_count == 1
