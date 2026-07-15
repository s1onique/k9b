"""Closed union tests for ``promotion_outcomes``.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant coverage.

Promotion is a single authoritative decision with three mutually
exclusive variants. Telemetry must derive consistently from the
outcome variant -- not from independently maintained booleans.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionOutcome,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
    consistency_error_recorded,
    is_commit_unknown,
    is_rejected,
    is_succeeded,
    may_have_committed,
    propagation_available,
)


def _make_token() -> PromotionReconciliationToken:
    return PromotionReconciliationToken(
        request_id="req-123",
        request_fingerprint="sha256:abc",
    )


class TestPromotionSucceeded:
    def test_zero_ids_allowed(self) -> None:
        outcome = PromotionSucceeded(
            run_id="run-1",
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=(),
        )
        assert outcome.diagnosis_incident_ids == ()
        assert outcome.canonical_incident_count == 0

    def test_diagnosis_ids_are_deduped(self) -> None:
        outcome = PromotionSucceeded(
            run_id="run-1",
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=("inc-1", "inc-1", "inc-2"),
        )
        assert outcome.diagnosis_incident_ids == ("inc-1", "inc-2")
        assert outcome.canonical_incident_count == 2

    def test_run_id_required(self) -> None:
        with pytest.raises(ValueError):
            PromotionSucceeded(
                run_id="",
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=(),
            )

    def test_is_succeeded_truthy(self) -> None:
        outcome = PromotionSucceeded(
            run_id="run-1",
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )
        assert is_succeeded(outcome)
        assert not is_rejected(outcome)
        assert not is_commit_unknown(outcome)


class TestPromotionRejected:
    def test_carries_reason_code(self) -> None:
        outcome = PromotionRejected(
            run_id="run-1",
            reason=PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION,
            rejected_signal_ids=("sha256:a",),
        )
        assert outcome.reason is PromotionRejectionCode.CURRENT_RUN_SCOPE_VIOLATION
        assert outcome.rejected_signal_ids == ("sha256:a",)

    def test_run_id_required(self) -> None:
        with pytest.raises(ValueError):
            PromotionRejected(
                run_id="",
                reason=PromotionRejectionCode.UNKNOWN,
                rejected_signal_ids=(),
            )

    def test_cannot_claim_commit(self) -> None:
        outcome = PromotionRejected(
            run_id="run-1",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        assert not may_have_committed(outcome)
        assert not propagation_available(outcome)


class TestPromotionCommitUnknown:
    def test_requires_token(self) -> None:
        with pytest.raises(ValueError):
            PromotionCommitUnknown(
                run_id="run-1",
                reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
                reconciliation_token=None,
            )

    def test_carries_token(self) -> None:
        token = _make_token()
        outcome = PromotionCommitUnknown(
            run_id="run-1",
            reason=PromotionUncertaintyCode.PROTOCOL_ERROR,
            reconciliation_token=token,
        )
        assert outcome.reconciliation_token is token

    def test_uncertainty_carries_propagation_block(self) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run-1",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=_make_token(),
        )
        assert may_have_committed(outcome)
        assert not propagation_available(outcome)


class TestProjections:
    def test_succeeded_is_succeeded(self) -> None:
        outcome = PromotionSucceeded(
            run_id="run-1",
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )
        assert is_succeeded(outcome)
        # ``may_have_committed`` is True for a confirmed success: a
        # successful promotion either committed or completed
        # authoritatively. The earlier test asserted False, which
        # contradicted the field name's plain reading.
        assert may_have_committed(outcome)
        assert propagation_available(outcome)
        assert not consistency_error_recorded(outcome)

    def test_rejected_records_consistency_error(self) -> None:
        outcome = PromotionRejected(
            run_id="run-1",
            reason=PromotionRejectionCode.UNKNOWN,
            rejected_signal_ids=(),
        )
        assert is_rejected(outcome)
        assert not may_have_committed(outcome)
        assert not propagation_available(outcome)
        assert consistency_error_recorded(outcome)

    def test_commit_unknown_records_consistency_error(self) -> None:
        outcome = PromotionCommitUnknown(
            run_id="run-1",
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=_make_token(),
        )
        assert is_commit_unknown(outcome)
        assert may_have_committed(outcome)
        assert not propagation_available(outcome)
        assert consistency_error_recorded(outcome)


class TestMutuallyExclusive:
    def test_no_outcome_is_two_variants(self) -> None:
        # Each ``PromotionOutcome`` is exactly one variant. The
        # ``is_*`` predicates MUST be pairwise exclusive.
        outcomes: list[PromotionOutcome] = [
            PromotionSucceeded(
                run_id="run",
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=("inc-1",),
            ),
            PromotionRejected(
                run_id="run",
                reason=PromotionRejectionCode.UNKNOWN,
                rejected_signal_ids=(),
            ),
            PromotionCommitUnknown(
                run_id="run",
                reason=PromotionUncertaintyCode.TRANSPORT_REFUSED,
                reconciliation_token=_make_token(),
            ),
        ]
        for outcome in outcomes:
            flags = [
                is_succeeded(outcome),
                is_rejected(outcome),
                is_commit_unknown(outcome),
            ]
            assert sum(flags) == 1
