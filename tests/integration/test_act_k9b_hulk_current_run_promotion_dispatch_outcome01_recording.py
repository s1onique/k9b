"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 recording + accumulator projection tests.

Covers invariants O11, O12, O13, O14, O18.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    PromotionOutcomeConflictError,
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)

from .incident_current_run_promotion_dispatch_outcome01_support import (
    RUN_ID,
)


def _token(request_id: str = "req-abc") -> PromotionReconciliationToken:
    return PromotionReconciliationToken(
        request_id=request_id,
        request_fingerprint="sha256:abc",
    )


# ---------------------------------------------------------------------------
# Recording contract (O13, O14, O18)
# ---------------------------------------------------------------------------


class TestRecordingContract:
    """The recorder enforces the one-owner contract."""

    def test_first_outcome_becomes_authoritative(self) -> None:
        accumulator = RunPromotionAccumulator()
        outcome = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=("inc-1",),
        )
        accumulator.record_promotion_outcome(outcome)
        assert accumulator.promotion_outcome is outcome
        assert accumulator.promotion_outcome_run_id == RUN_ID
        assert accumulator.promotion_outcome_variant_label() == "succeeded"

    def test_identical_repeated_assignment_is_idempotent(self) -> None:
        accumulator = RunPromotionAccumulator()
        outcome = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )
        accumulator.record_promotion_outcome(outcome)
        accumulator.record_promotion_outcome(outcome)
        assert accumulator.promotion_outcome is outcome

    def test_different_run_id_rejected(self) -> None:
        accumulator = RunPromotionAccumulator()
        first = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )
        accumulator.record_promotion_outcome(first)
        with pytest.raises(PromotionOutcomeConflictError):
            accumulator.record_promotion_outcome(
                PromotionSucceeded(
                    run_id="run-other",
                    requested_signal_ids=(),
                    records=(),
                    diagnosis_incident_ids=(),
                )
            )
        assert accumulator.promotion_outcome is first

    def test_conflicting_second_outcome_rejected(self) -> None:
        accumulator = RunPromotionAccumulator()
        first = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=("inc-1",),
        )
        accumulator.record_promotion_outcome(first)
        with pytest.raises(PromotionOutcomeConflictError):
            accumulator.record_promotion_outcome(
                PromotionRejected(
                    run_id=RUN_ID,
                    reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                    rejected_signal_ids=(),
                )
            )
        assert accumulator.promotion_outcome is first

    def test_commit_unknown_idempotency_uses_full_token(self) -> None:
        """Two commit-unknown outcomes are equal iff both token fields match."""
        accumulator = RunPromotionAccumulator()
        first = PromotionCommitUnknown(
            run_id=RUN_ID,
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=_token("req-a"),
            requested_signal_ids=("sha256:a",),
        )
        second = PromotionCommitUnknown(
            run_id=RUN_ID,
            reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=_token("req-b"),
            requested_signal_ids=("sha256:a",),
        )
        accumulator.record_promotion_outcome(first)
        with pytest.raises(PromotionOutcomeConflictError):
            accumulator.record_promotion_outcome(second)

    def test_variant_label_reflects_recorded_outcome(self) -> None:
        accumulator = RunPromotionAccumulator()
        assert accumulator.promotion_outcome_variant_label() == "none"
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_token(),
                requested_signal_ids=("sha256:a",),
            )
        )
        assert accumulator.promotion_outcome_variant_label() == (
            "commit_unknown"
        )


# ---------------------------------------------------------------------------
# Accumulator derives projections from typed outcome (O11, O12)
# ---------------------------------------------------------------------------


class TestAccumulatorProjectionDerivesFromOutcome:
    """Once a typed outcome is recorded, legacy projections yield to it."""

    def _seed_legacy_then_record_outcome(self) -> RunPromotionAccumulator:
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )

        accumulator = RunPromotionAccumulator()
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="<legacy>",
                canonical_incident_id="inc-legacy",
                promotion_outcome="opened",
            )
        )
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                records=(),
                diagnosis_incident_ids=("inc-typed",),
            )
        )
        return accumulator

    def test_canonical_ids_derive_from_outcome(self) -> None:
        accumulator = self._seed_legacy_then_record_outcome()
        assert accumulator.canonical_incident_ids() == ["inc-typed"]

    def test_may_have_committed_derives_from_outcome(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )
        accumulator = RunPromotionAccumulator()
        accumulator.total_errors = 99
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=(),
            )
        )
        assert accumulator.promotion_may_have_committed() is True

    def test_consistency_error_derives_from_outcome(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionUncertaintyCode,
        )
        accumulator = RunPromotionAccumulator()
        accumulator.total_errors = 0
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_token(),
                requested_signal_ids=(),
            )
        )
        assert accumulator.promotion_consistency_error_recorded() is True

    def test_diagnosis_handoff_blocked_for_commit_unknown(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionUncertaintyCode,
        )
        accumulator = RunPromotionAccumulator()
        accumulator.total_opened_incidents = 5
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_token(),
                requested_signal_ids=(),
            )
        )
        assert accumulator.diagnosis_handoff_available() is False
    def test_recorded_records_empty_for_commit_unknown_with_legacy_records(
        self,
    ) -> None:
        """R3-5 final: non-success typed outcomes expose NO legacy records.

        Seed legacy records, then record a ``PromotionCommitUnknown``;
        the recorded records projection MUST be empty even though the
        legacy projection would otherwise expose the seeded records.
        """
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionUncertaintyCode,
        )

        accumulator = RunPromotionAccumulator()
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="<legacy>",
                canonical_incident_id="inc-legacy",
                promotion_outcome="opened",
            )
        )
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=PromotionReconciliationToken(
                    request_id="req",
                    request_fingerprint="sha256:abc",
                ),
                requested_signal_ids=("sha256:a",),
            )
        )
        # Once the typed outcome is recorded, legacy records MUST NOT
        # regain authority -- the recorded records projection is empty.
        assert accumulator.recorded_records() == ()

    def test_recorded_records_empty_for_rejected_with_legacy_records(
        self,
    ) -> None:
        """R3-5 final: ``PromotionRejected`` exposes NO legacy records."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionRejected,
            PromotionRejectionCode,
        )

        accumulator = RunPromotionAccumulator()
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="<legacy>",
                canonical_incident_id="inc-legacy",
                promotion_outcome="opened",
            )
        )
        accumulator.record_promotion_outcome(
            PromotionRejected(
                run_id=RUN_ID,
                reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                rejected_signal_ids=("sha256:a",),
            )
        )
        assert accumulator.recorded_records() == ()

    def test_promotion_outcomes_empty_for_non_success_with_legacy(
        self,
    ) -> None:
        """R3-5 final: ``promotion_outcomes()`` does NOT fall through to legacy
        per-record outcomes once a non-success typed outcome is recorded.
        """
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionUncertaintyCode,
        )

        accumulator = RunPromotionAccumulator()
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="<legacy>",
                canonical_incident_id="inc-legacy",
                promotion_outcome="opened",
            )
        )
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=PromotionReconciliationToken(
                    request_id="req",
                    request_fingerprint="sha256:abc",
                ),
                requested_signal_ids=("sha256:a",),
            )
        )
        # The legacy per-record outcomes MUST NOT regain authority.
        assert accumulator.promotion_outcomes() == ()


class TestOneDispatchPerAccumulator:
    """One accumulator = exactly one scoped dispatch attempt.

    ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 invariant:
    the run-scoped accumulator is the single owner of the typed
    ``PromotionOutcome`` for the health run. Two materially distinct
    second outcomes MUST raise :class:`PromotionOutcomeConflictError`.
    """

    def test_second_different_outcome_raises_conflict(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )

        accumulator = RunPromotionAccumulator()
        first = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:a",),
            records=(),
            diagnosis_incident_ids=("inc-1",),
        )
        accumulator.record_promotion_outcome(first)
        second = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=("sha256:b",),
            records=(),
            diagnosis_incident_ids=("inc-2",),
        )
        with pytest.raises(PromotionOutcomeConflictError):
            accumulator.record_promotion_outcome(second)
        # First outcome remains authoritative.
        assert accumulator.promotion_outcome is first
