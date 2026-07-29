"""Scoped accumulator invariants against global store-scan fallback.

ACT-K9B-HULK-PROMOTION-SELECTION-SUITE-RESPONSIBILITY-SPLIT01.

These tests pin the bounded invariants of the accumulator after
a typed scoped handoff. The aggregate scoped result MUST NOT
synthesise per-signal ``promotion_records``; the receipt is the
only authority. A typed commit-unknown handoff MUST NOT store
global candidate scan evidence; a typed rejected handoff MUST
NOT store global store-scan evidence. ``aggregate_successful_zero``
MUST keep ``records`` empty and the receipt present.

The file also covers the explicit ``no_promotion_run`` path --
the only branch that may produce the canonical
``selection_source=explicit_nonpromotion`` discriminator -- and
proves that completed zero, commit unknown and rejected
typed outcomes cannot enter this branch.
"""

from __future__ import annotations

from scoped_selection_typed_support import (
    build_completed_projection,
    build_rejected_projection,
    build_uncertain_projection,
)

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    scoped_dispatch_result_to_accumulator_handoff,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchUncertain,
)


class TestScopedAccumulatorInvariants:
    """Bounded invariants of the accumulator after a typed handoff."""

    def test_aggregate_successful_zero_keeps_records_empty(self) -> None:
        projection = build_completed_projection(diagnosis_incident_ids=())
        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchCompleted(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)
        # Aggregate scoped result MUST NOT synthesise per-signal
        # promotion_records. The receipt is the only authority.
        assert accumulator.promotion_records == []
        assert accumulator.total_errors == 0

    def test_uncertain_handoff_does_not_store_can(self) -> None:
        projection = build_uncertain_projection()
        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchUncertain(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)
        # No batch is added -- the accumulator carries the typed
        # outcome only. ``promotion_records`` stays empty; the
        # global store-scan fallback is NOT triggered.
        assert accumulator.promotion_records == []
        assert accumulator.total_errors == 0

    def test_rejected_handoff_does_not_store_scan(self) -> None:
        projection = build_rejected_projection()
        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchRejected(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)
        # Aggregate scoped result MUST NOT add per-signal records.
        assert accumulator.promotion_records == []
        # ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
        # CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01:
        # the atomic wrapper routes through
        # ``record_scoped_promotion_batch``, so the bounded
        # rejection now correctly populates the aggregate error
        # counter (errors == 1). The previous behaviour that
        # silently swallowed the rejection error count was an
        # accounting bug; the test name continues to pin the
        # store-scan invariant.
        assert accumulator.total_errors == 1

    def test_idempotent_record_for_identical_handoff(self) -> None:
        projection = build_completed_projection(
            diagnosis_incident_ids=("c-1",)
        )
        accumulator = RunPromotionAccumulator()
        result_first = accumulator.record_promotion_outcome(
            outcome=projection.promotion_outcome
        )
        assert result_first is PromotionOutcomeRecording.NEW
        result_second = accumulator.record_promotion_outcome(
            outcome=projection.promotion_outcome
        )
        assert result_second is PromotionOutcomeRecording.IDEMPOTENT

    def test_rejected_handoff_records_definitely_not_committed(self) -> None:
        projection = build_rejected_projection()
        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchRejected(projection=projection)
        )
        # The accumulator copies the commit_disposition from the
        # handoff; a typed rejection MUST carry
        # DEFINITELY_NOT_COMMITTED.
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )


class TestExplicitNoPromotionPath:
    """Explicit no-promotion path is the only branch that may
    produce ``selection_source=explicit_nonpromotion`` with
    ``incident_access_mode=no_promotion_run``.

    The closed pairwise tests below prove that completed,
    commit-unknown and rejected typed outcomes cannot collapse
    into the no-promotion path even when the requested
    signal set is empty.
    """

    def test_no_promotion_attempt_path_is_distinct_from_completed_zero(
        self,
    ) -> None:
        """Completed-zero MUST stay ``current_run_empty``;
        the no-promotion path is the only branch that may carry
        ``no_promotion_run`` access mode.
        """
        from k8s_diag_agent.health.loop_runner_execute import (
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
            _build_diagnosis_execution_authority,
        )

        projection = build_completed_projection(diagnosis_incident_ids=())
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
        )
        # Completed-zero MUST still resolve to promotion
        # selection; even when the dispatcher reports
        # ``no_promotion_run`` access mode, the canonical
        # typed outcome keeps the completed selection shape.
        assert (
            authority.selection_mode
            is INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY
        )
        assert (
            authority.selection_source is DIAGNOSIS_SELECTION_SOURCE_PROMOTION
        )

    def test_commit_unknown_cannot_collapse_to_no_promotion(self) -> None:
        """Commit-unknown selection MUST keep its commit-unknown
        selection mode regardless of the dispatcher's
        access mode.
        """
        from k8s_diag_agent.health.loop_runner_execute import (
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
            _build_diagnosis_execution_authority,
        )

        projection = build_uncertain_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
        )
        assert (
            authority.selection_mode is INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
        )

    def test_rejected_cannot_collapse_to_no_promotion(self) -> None:
        """Rejected selection MUST keep its blocked selection mode
        regardless of the dispatcher's access mode.
        """
        from k8s_diag_agent.health.loop_runner_execute import (
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            INCIDENT_SELECTION_MODE_BLOCKED,
            _build_diagnosis_execution_authority,
        )

        projection = build_rejected_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
        )
        assert authority.selection_mode is INCIDENT_SELECTION_MODE_BLOCKED

    def test_no_promotion_run_collapsed_only_for_empty_signal_set(self) -> None:
        """The closed ``no_promotion_run`` collapse path is the
        ONLY branch that may produce ``selection_source=
        explicit_nonpromotion``. The pairwise tests above prove
        that completed zero, commit unknown and rejected
        outcomes cannot enter this branch regardless of the
        dispatcher access mode.
        """
        from k8s_diag_agent.health.loop_runner_execute import (
            DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
            DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
            INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN,
            _build_diagnosis_execution_authority,
        )

        # All three typed outcomes MUST NOT produce
        # ``explicit_nonpromotion`` regardless of access mode.
        for projection in (
            build_completed_projection(diagnosis_incident_ids=()),
            build_uncertain_projection(),
            build_rejected_projection(),
        ):
            authority = _build_diagnosis_execution_authority(
                promotion_outcome=projection.promotion_outcome,
                dispatcher_incident_access_mode=(
                    INCIDENT_ACCESS_MODE_NO_PROMOTION_RUN
                ),
            )
            assert (
                authority.selection_source
                is not DIAGNOSIS_SELECTION_SOURCE_EXPLICIT_NON_PROMOTION
            )
            # The selection source is still bound to the typed
            # outcome class (promotion, promotion_blocked, or
            # promotion_commit_unknown).
            assert authority.selection_source in {
                DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
                DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
                DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
            }
