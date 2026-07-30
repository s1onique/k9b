"""ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01 accumulator + telemetry tests.

Covers the accumulator recording contract (O11, O13, O14, O18) and
the telemetry projection (R3-2, R3-3, R3-7).

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    PromotionOutcomeConflictError,
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.promotion_dispatch_outcome import (
    promotion_outcome_event_fields,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)

RUN_ID = "run-2026-07-15T0350Z"


def _token(
    request_id: str = "req-abc",
    fingerprint: str = "sha256:abc",
) -> PromotionReconciliationToken:
    return PromotionReconciliationToken(
        request_id=request_id,
        request_fingerprint=fingerprint,
    )


# ---------------------------------------------------------------------------
# Accumulator recording contract
# ---------------------------------------------------------------------------


class TestAccumulatorRecording:
    def test_recorded_outcome_is_authoritative(self) -> None:
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

    def test_idempotent_repeat_does_not_raise(self) -> None:
        from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
            PromotionOutcomeRecording,
        )

        accumulator = RunPromotionAccumulator()
        outcome = PromotionSucceeded(
            run_id=RUN_ID,
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )
        first = accumulator.record_promotion_outcome(outcome)
        second = accumulator.record_promotion_outcome(outcome)
        assert first is PromotionOutcomeRecording.NEW
        assert second is PromotionOutcomeRecording.IDEMPOTENT
        assert accumulator.promotion_outcome is outcome

    def test_commit_unknown_idempotency_uses_full_token(self) -> None:
        """R3-6: two commit-unknown outcomes are equal iff both token fields match."""
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
            reconciliation_token=_token("req-b"),  # different request_id
            requested_signal_ids=("sha256:a",),
        )
        accumulator.record_promotion_outcome(first)
        with pytest.raises(PromotionOutcomeConflictError):
            accumulator.record_promotion_outcome(second)
        assert accumulator.promotion_outcome is first

    def test_cross_run_recording_rejected(self) -> None:
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
                    run_id="different-run",
                    requested_signal_ids=(),
                    records=(),
                    diagnosis_incident_ids=(),
                )
            )
        assert accumulator.promotion_outcome is first

    def test_conflicting_variant_rejected(self) -> None:
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

    def test_record_none_raises(self) -> None:
        accumulator = RunPromotionAccumulator()
        with pytest.raises(ValueError):
            accumulator.record_promotion_outcome(None)

    def test_variant_label_returns_none_for_empty_accumulator(self) -> None:
        accumulator = RunPromotionAccumulator()
        assert accumulator.promotion_outcome_variant_label() == "none"

    def test_variant_label_returns_commit_unknown(self) -> None:
        accumulator = RunPromotionAccumulator()
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
# Accumulator projection derives from typed outcome (O11, O12)
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
        accumulator.total_errors = 99  # legacy state disagrees
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

    def test_diagnosis_handoff_available_derives_from_outcome(self) -> None:
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )
        accumulator = RunPromotionAccumulator()
        accumulator.total_opened_incidents = 0
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=(),
                records=(),
                diagnosis_incident_ids=("inc-1",),
            )
        )
        assert accumulator.diagnosis_handoff_available() is True

    def test_diagnosis_handoff_not_available_for_commit_unknown(self) -> None:
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

    def test_legacy_projection_used_when_no_outcome_recorded(self) -> None:
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        accumulator = RunPromotionAccumulator()
        accumulator.add_record(
            PromotionRecord(
                source_candidate_id="<legacy>",
                canonical_incident_id="inc-1",
                promotion_outcome="opened",
            )
        )
        # No typed outcome yet -> legacy projection.
        assert accumulator.canonical_incident_ids() == ["inc-1"]

    def test_recorded_records_derive_from_succeeded_outcome(self) -> None:
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionSucceeded,
        )
        accumulator = RunPromotionAccumulator()
        authoritative = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="inc-1",
            promotion_outcome="opened",
        )
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                records=(authoritative,),
                diagnosis_incident_ids=("inc-1",),
            )
        )
        assert accumulator.recorded_records() == (authoritative,)


# ---------------------------------------------------------------------------
# Telemetry projection invariants (R3-2, R3-3, R3-7)
# ---------------------------------------------------------------------------


class TestTelemetryProjectionInvariants:
    def test_succeeded_projection(self) -> None:
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PromotionRecord,
        )
        record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="inc-1",
            promotion_outcome="opened",
        )
        outcome = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=("sha256:a", "sha256:b"),
            records=(record,),
            diagnosis_incident_ids=("inc-1",),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "succeeded"
        assert projection["promotion_outcome_reason"] == ""
        assert projection["promotion_may_have_committed"] is True
        assert projection["diagnosis_handoff_available"] is True
        assert projection["diagnosis_handoff_incident_count"] == 1
        assert projection["diagnosis_invoked"] is False
        assert projection["promotion_consistency_error_recorded"] is False
        assert projection["promotion_outcome_available"] is True
        assert projection["reconciliation_required"] is False
        assert projection["requested_signal_count"] == 2
        assert projection["canonical_incident_id_count"] == 1
        assert projection["promotion_record_count"] == 1
        # R3-3: Item 3 does NOT claim diagnosis actually ran.
        assert "promotion_propagated_to_diagnosis" not in projection

    def test_rejected_projection(self) -> None:
        outcome = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
            rejected_signal_ids=("sha256:a",),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "rejected"
        assert projection["promotion_outcome_reason"] == "malformed_signal_ids"
        assert projection["promotion_may_have_committed"] is False
        assert projection["diagnosis_handoff_available"] is False
        assert projection["diagnosis_handoff_incident_count"] == 0
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["reconciliation_required"] is False
        assert projection["canonical_incident_id_count"] == 0

    def test_commit_unknown_projection(self) -> None:
        """R3-2: ``requested_signal_count`` is non-zero when ``PromotionCommitUnknown``
        carries a non-empty ``requested_signal_ids``."""
        outcome = PromotionCommitUnknown(
            run_id="run",
            reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
            reconciliation_token=_token(),
            requested_signal_ids=("sha256:a", "sha256:b", "sha256:c"),
        )
        projection = promotion_outcome_event_fields(outcome)
        assert projection["promotion_outcome"] == "commit_unknown"
        assert projection["promotion_outcome_reason"] == "transport_timeout"
        assert projection["promotion_may_have_committed"] is True
        assert projection["diagnosis_handoff_available"] is False
        assert projection["diagnosis_handoff_incident_count"] == 0
        assert projection["promotion_consistency_error_recorded"] is True
        assert projection["reconciliation_required"] is True
        assert projection["canonical_incident_id_count"] == 0
        assert projection["requested_signal_count"] == 3

    def test_no_contradictory_combinations(self) -> None:
        """Non-success variants MUST NOT claim propagation available."""
        for variant in (
            PromotionRejected(
                run_id="run",
                reason=PromotionRejectionCode.UNKNOWN,
                rejected_signal_ids=(),
            ),
            PromotionCommitUnknown(
                run_id="run",
                reason=PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
                reconciliation_token=_token(),
                requested_signal_ids=(),
            ),
        ):
            projection = promotion_outcome_event_fields(variant)
            assert projection["diagnosis_handoff_available"] is False
            assert projection["promotion_consistency_error_recorded"] is True
            if isinstance(variant, PromotionCommitUnknown):
                assert projection["reconciliation_required"] is True
                assert projection["promotion_may_have_committed"] is True
            else:
                assert projection["reconciliation_required"] is False
                assert projection["promotion_may_have_committed"] is False

    def test_unknown_variant_raises_type_error(self) -> None:
        """R3-7: unsupported variants raise ``TypeError``."""
        with pytest.raises(TypeError):
            promotion_outcome_event_fields("not a PromotionOutcome")


# ---------------------------------------------------------------------------
# has_promotion_activity regression tests
# ACT-K9B-HULK-PROMOTION-LIVE-WIRE-AND-PROJECTION-TRUTH01-CORRECTION01
# ---------------------------------------------------------------------------


class TestHasPromotionActivity:
    """Regression tests for has_promotion_activity invariant.

    Required invariant:
        has_promotion_activity = bool(batches) OR promotion_outcome is not None

    Cases:
        - empty accumulator -> False
        - successful batch -> True
        - rejected outcome without batch -> True
        - commit-unknown outcome without batch -> True
        - dispatch absent -> final no_promotion_run
        - dispatch commit-unknown -> final reconciliation_required
    """

    def test_empty_accumulator_has_no_activity(self) -> None:
        """Empty accumulator with no batches and no outcome -> no activity."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False

    def test_batch_provides_activity(self) -> None:
        """A recorded batch provides promotion activity."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            PROMOTION_OUTCOME_OPENED,
            PromotionRecord,
        )
        from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            IncidentPromotionResult,
        )

        accumulator = RunPromotionAccumulator()
        record = PromotionRecord(
            source_candidate_id="cand-1",
            canonical_incident_id="inc-1",
            promotion_outcome=PROMOTION_OUTCOME_OPENED,
        )
        batch = PromotionBatch(
            promotion_result=IncidentPromotionResult(
                ok=True,
                scanned=1,
                firing=1,
                opened_incidents=1,
                updated_incidents=0,
                skipped_duplicates=0,
                errors=0,
                error_messages=(),
                promotion_mode="backend-api",
                opened_incident_ids=("inc-1",),
                updated_incident_ids=(),
                promotion_records=[record.to_dict()],
                unique_candidate_count=1,
                promotion_scan_scope="test",
                incident_access_mode="backend",
            ),
            promotion_records=(record,),
            source_kind="alertmanager",
            cluster_context="test",
            snapshot_bundle_id=None,
        )
        accumulator.add_batch(batch)
        assert accumulator.has_promotion_activity() is True
        assert len(accumulator.batches) == 1

    def test_rejected_outcome_without_batch_has_activity(self) -> None:
        """Rejection outcome without batch proves dispatch occurred."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionRejected(
                run_id=RUN_ID,
                reason=PromotionRejectionCode.MALFORMED_SIGNAL_IDS,
                rejected_signal_ids=("sha256:a",),
            )
        )
        assert accumulator.has_promotion_activity() is True

    def test_commit_unknown_outcome_without_batch_has_activity(self) -> None:
        """Commit-unknown outcome without batch proves dispatch occurred.

        This is the core regression: a commit-unknown dispatch was previously
        projecting as no_promotion_run because has_promotion_activity only
        checked bool(batches). With the fix, a recorded outcome proves
        promotion activity even without a successful batch append.
        """
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionCommitUnknown(
                run_id=RUN_ID,
                reason=PromotionUncertaintyCode.TRANSPORT_TIMEOUT,
                reconciliation_token=_token(),
                requested_signal_ids=("sha256:a",),
            )
        )
        assert accumulator.has_promotion_activity() is True

    def test_succeeded_outcome_without_batch_has_activity(self) -> None:
        """Success outcome without batch proves dispatch occurred."""
        accumulator = RunPromotionAccumulator()
        assert accumulator.has_promotion_activity() is False  # no outcome yet
        accumulator.record_promotion_outcome(
            PromotionSucceeded(
                run_id=RUN_ID,
                requested_signal_ids=("sha256:a",),
                records=(),
                diagnosis_incident_ids=(),
            )
        )
        assert accumulator.has_promotion_activity() is True
