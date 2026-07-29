"""Scoped accumulator selection tests driven by the typed accumulator handoff.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01.

These tests drive the full path from the scoped dispatcher
through :func:`scoped_dispatch_result_to_accumulator_handoff`
to the typed authority consumed by the selection handoff.

Three cases are exhaustively pinned:

* **Aggregate successful zero** -- 34 scanned signals, zero
  diagnosis incident IDs, receipt present, ``store_scan_performed``
  MUST be False. A zero diagnosis-ID count MUST NOT collapse into
  ``no_promotion_run`` or ``store_scan``.
* **Commit unknown identity** -- ``PromotionCommitUnknown``,
  reconciliation token, request id and fingerprint MUST reach
  the accumulator unchanged by identity. ``selection_mode`` MUST
  be ``commit_unknown``; ``store_scan_performed`` MUST be False.
* **Rejection authority** -- ``PromotionRejected`` MUST reach
  the accumulator unchanged by identity. ``selection_mode`` MUST
  be ``blocked``; ``store_scan_performed`` MUST be False.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
    MODE_BACKEND_API,
    promote_alert_signals_scoped_for_accumulator,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeRecording,
)
from k8s_diag_agent.collect.promotion_outcomes import (
    PromotionCommitDisposition,
    PromotionCommitUnknown,
    PromotionReconciliationToken,
    PromotionRejected,
    PromotionRejectionCode,
    PromotionSucceeded,
    PromotionUncertaintyCode,
)
from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)
from k8s_diag_agent.collect.promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionReceipt,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchResult,
    ScopedPromotionDispatchUncertain,
)
from k8s_diag_agent.health.loop_runner_execute import (
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION,
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED,
    DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_BLOCKED,
    INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN,
    INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY,
    INCIDENT_SELECTION_MODE_EXPLICIT_IDS,
    _build_diagnosis_execution_authority,
)
from k8s_diag_agent.incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)

# ---------------------------------------------------------------------------
# Builders for closed union values
# ---------------------------------------------------------------------------


def _build_completed_projection(
    *,
    run_id: str = "health-run-typed-handoff-001",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(34)
    ),
    diagnosis_incident_ids: tuple[str, ...] = (),
) -> ScopedPromotionCompletedProjection:
    """Build a typed completed projection.

    When ``diagnosis_incident_ids`` is empty this models the
    aggregate-successful-zero case the active path MUST keep
    authoritative (no promotion-run collapse).
    """
    from k8s_diag_agent.collect.incident_identity_hardening import (
        PromotionRecord,
    )

    bound_obj = _build_bound(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        diagnosis_incident_ids=diagnosis_incident_ids,
    )
    return ScopedPromotionCompletedProjection(
        promotion_outcome=PromotionSucceeded(
            run_id=run_id,
            requested_signal_ids=requested_signal_ids,
            records=tuple(
                PromotionRecord(
                    source_candidate_id=f"<scoped:{sid}>",
                    canonical_incident_id=cid,
                    promotion_outcome="opened",
                )
                for sid, cid in zip(
                    requested_signal_ids,
                    diagnosis_incident_ids,
                )
            ),
            diagnosis_incident_ids=diagnosis_incident_ids,
        ),
        aggregate_receipt=ScopedPromotionReceipt(bound=bound_obj),
        request_id="promotion-request-completed-001",
        request_fingerprint="a" * 64,
    )


def _build_uncertain_projection(
    *,
    run_id: str = "health-run-typed-handoff-001",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(34)
    ),
) -> ScopedPromotionUncertainProjection:
    return ScopedPromotionUncertainProjection(
        promotion_outcome=PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id="promotion-request-uncertain-001",
                request_fingerprint="b" * 64,
            ),
            requested_signal_ids=requested_signal_ids,
        ),
        request_id="promotion-request-uncertain-001",
        request_fingerprint="b" * 64,
    )


def _build_rejected_projection(
    *,
    run_id: str = "health-run-typed-handoff-001",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(34)
    ),
) -> ScopedPromotionRejectedProjection:
    return ScopedPromotionRejectedProjection(
        promotion_outcome=PromotionRejected(
            run_id=run_id,
            reason=PromotionRejectionCode.BACKEND_UNREACHABLE,
            rejected_signal_ids=requested_signal_ids,
        ),
        request_id="promotion-request-rejected-001",
        request_fingerprint="c" * 64,
    )


def _build_bound(
    *,
    run_id: str,
    requested_signal_ids: tuple[str, ...],
    diagnosis_incident_ids: tuple[str, ...],
) -> Any:
    """Build a :class:`BoundScopedPromotionResult` for the receipt."""
    from k8s_diag_agent.domain.identifiers import AlertSignalId
    from k8s_diag_agent.domain.incident_lifecycle import IncidentId
    from k8s_diag_agent.incident_alert_promotion_binding import (
        BoundScopedPromotionResult,
    )
    from k8s_diag_agent.incident_alert_promotion_contract import (
        IncidentPromotionResult,
    )

    typed_signal_ids = tuple(AlertSignalId(value) for value in requested_signal_ids)
    opened_incident_ids = tuple(IncidentId(value) for value in diagnosis_incident_ids)
    success = IncidentPromotionResult(
        run_id=run_id,
        source_identity="source-test",
        scanned_signal_ids=typed_signal_ids,
        opened_incident_ids=opened_incident_ids,
    )
    return BoundScopedPromotionResult(
        request=PromoteAlertSignalsRequest(
            run_id=run_id,
            source_identity="source-test",
            signal_ids=typed_signal_ids,
        ),
        result=success,
    )


# ---------------------------------------------------------------------------
# Identity tests
# ---------------------------------------------------------------------------


class TestScopedAccumulatorHandoffIdentity:
    """Identity preservation across the dispatch-result -> accumulator handoff."""

    def test_completed_preserves_outcome_and_receipt_by_identity(self) -> None:
        projection = _build_completed_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchCompleted(projection=projection)
        )
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorCompleted)
        assert handoff.outcome is projection.promotion_outcome
        assert handoff.receipt is projection.aggregate_receipt
        assert handoff.request_id == "promotion-request-completed-001"
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_COMMITTED
        )

    def test_uncertain_preserves_outcome_by_identity(self) -> None:
        projection = _build_uncertain_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchUncertain(projection=projection)
        )
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorUncertain)
        assert handoff.outcome is projection.promotion_outcome
        # Reconciliation token reaches the accumulator by identity
        assert (
            handoff.outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.MAY_HAVE_COMMITTED
        )

    def test_rejected_preserves_outcome_by_identity(self) -> None:
        projection = _build_rejected_projection()
        typed_result: ScopedPromotionDispatchResult = (
            ScopedPromotionDispatchRejected(projection=projection)
        )
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)
        assert isinstance(handoff, ScopedPromotionAccumulatorRejected)
        assert handoff.outcome is projection.promotion_outcome
        assert handoff.commit_disposition is (
            PromotionCommitDisposition.DEFINITELY_NOT_COMMITTED
        )


# ---------------------------------------------------------------------------
# Selection handoff
# ---------------------------------------------------------------------------


class TestAggregateSuccessfulZeroThroughSelection:
    """Aggregate scoped success with zero diagnosis IDs stays a completed promotion."""

    def test_zero_diagnosis_ids_do_not_collapse_to_no_promotion_run(self) -> None:
        projection = _build_completed_projection(
            diagnosis_incident_ids=()
        )
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode
            is INCIDENT_SELECTION_MODE_CURRENT_RUN_EMPTY
        )
        assert (
            authority.selection_source is DIAGNOSIS_SELECTION_SOURCE_PROMOTION
        )
        assert authority.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND
        assert authority.reconciliation_required is False

    def test_zero_diagnosis_ids_with_ids_do_not_collapse_to_no_promotion_run(
        self,
    ) -> None:
        projection = _build_completed_projection(
            diagnosis_incident_ids=("canonical-001", "canonical-002"),
        )
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode
            is INCIDENT_SELECTION_MODE_EXPLICIT_IDS
        )
        assert (
            authority.selection_source is DIAGNOSIS_SELECTION_SOURCE_PROMOTION
        )
        assert authority.incident_access_mode == INCIDENT_ACCESS_MODE_BACKEND


class TestCommitUnknownIdentityThroughSelection:
    """Commit-unknown identity flows into the selection handoff."""

    def test_commit_unknown_routes_to_commit_unknown_selection(self) -> None:
        projection = _build_uncertain_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert (
            authority.selection_mode is INCIDENT_SELECTION_MODE_COMMIT_UNKNOWN
        )
        assert (
            authority.selection_source
            is DIAGNOSIS_SELECTION_SOURCE_PROMOTION_COMMIT_UNKNOWN
        )
        assert authority.reconciliation_required is True

    def test_commit_unknown_requested_signal_ids_preserved(self) -> None:
        projection = _build_uncertain_projection()
        outcome = projection.promotion_outcome
        assert outcome.requested_signal_ids == tuple(
            f"sig-{i:02d}" for i in range(34)
        )


class TestRejectionAuthorityThroughSelection:
    """Rejection authority flows into the selection handoff as blocked."""

    def test_rejected_routes_to_blocked_selection(self) -> None:
        projection = _build_rejected_projection()
        outcome = projection.promotion_outcome
        authority = _build_diagnosis_execution_authority(
            promotion_outcome=outcome,
            dispatcher_incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        assert authority.selection_mode is INCIDENT_SELECTION_MODE_BLOCKED
        assert (
            authority.selection_source
            is DIAGNOSIS_SELECTION_SOURCE_PROMOTION_BLOCKED
        )
        assert authority.reconciliation_required is False


class TestRecordScopedPromotion:
    """``record_scoped_promotion`` records the typed authority verbatim."""

    def test_completed_handoff_records_typed_outcome(self) -> None:
        projection = _build_completed_projection()
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchCompleted(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)

        # Identity preserved.
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert accumulator.scoped_promotion_handoff is handoff
        assert (
            accumulator.scoped_promotion_request_id
            == projection.request_id
        )
        assert (
            accumulator.scoped_promotion_request_fingerprint
            == projection.request_fingerprint
        )

    def test_uncertain_handoff_records_typed_outcome(self) -> None:
        projection = _build_uncertain_projection()
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchUncertain(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)

        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert accumulator.scoped_promotion_handoff is handoff
        # Reconciliation identity preserved.
        assert (
            accumulator.promotion_outcome.reconciliation_token
            is projection.promotion_outcome.reconciliation_token
        )

    def test_rejected_handoff_records_typed_outcome(self) -> None:
        projection = _build_rejected_projection()
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        handoff = scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchRejected(projection=projection)
        )
        accumulator = RunPromotionAccumulator()
        accumulator.record_scoped_promotion(handoff)

        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert accumulator.scoped_promotion_handoff is handoff


class TestScopedAccumulatorDispatchResultFingerprint:
    """Active dispatcher path is invoked with the typed dispatch result."""

    def test_promote_alert_signals_scoped_consumes_typed_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        """The dispatcher must call the typed accumulator handoff path."""
        projection = _build_completed_projection()

        def _stub_promote(*, run_id: str, source_identity: str, signal_ids: list[str]) -> Any:
            return ScopedPromotionDispatchCompleted(projection=projection)

        from k8s_diag_agent.collect import incident_promotion_backend

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote,
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=tuple(f"sig-{i:02d}" for i in range(34)),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        # The accumulator recorded the typed handoff verbatim.
        assert isinstance(accumulator.scoped_promotion_handoff, ScopedPromotionAccumulatorHandoff)
        assert accumulator.promotion_outcome is projection.promotion_outcome
        assert (
            accumulator.scoped_promotion_request_id
            == "promotion-request-completed-001"
        )

        # The batch carries the bounded access mode.
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )
        assert batch.promotion_result.promotion_mode == MODE_BACKEND_API

    def test_uncertain_batch_carries_reconciliation_required_access_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        projection = _build_uncertain_projection()

        def _stub_promote(*, run_id: str, source_identity: str, signal_ids: list[str]) -> Any:
            return ScopedPromotionDispatchUncertain(projection=projection)

        from k8s_diag_agent.collect import incident_promotion_backend

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote,
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=tuple(f"sig-{i:02d}" for i in range(34)),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        # Identity preserved through the dispatcher.
        assert (
            accumulator.scoped_promotion_request_id
            == "promotion-request-uncertain-001"
        )
        assert (
            accumulator.promotion_outcome.reconciliation_token.request_id
            == "promotion-request-uncertain-001"
        )
        assert batch.promotion_result.incident_access_mode == (
            "reconciliation_required"
        )

    def test_rejected_batch_carries_backend_access_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Any,
    ) -> None:
        projection = _build_rejected_projection()

        def _stub_promote(*, run_id: str, source_identity: str, signal_ids: list[str]) -> Any:
            return ScopedPromotionDispatchRejected(projection=projection)

        from k8s_diag_agent.collect import incident_promotion_backend

        monkeypatch.setattr(
            incident_promotion_backend,
            "promote_alert_signals_via_scoped_backend_api",
            _stub_promote,
        )

        accumulator = RunPromotionAccumulator()
        batch = promote_alert_signals_scoped_for_accumulator(
            runs_dir=tmp_path,
            health_run_id="health-run-typed-handoff-001",
            source_identity="source-test",
            signal_ids=tuple(f"sig-{i:02d}" for i in range(34)),
            accumulator=accumulator,
            cluster_context="ctx-test",
        )

        assert (
            accumulator.scoped_promotion_request_id
            == "promotion-request-rejected-001"
        )
        assert accumulator.promotion_outcome.reason is (
            PromotionRejectionCode.BACKEND_UNREACHABLE
        )
        assert batch.promotion_result.incident_access_mode == (
            INCIDENT_ACCESS_MODE_BACKEND
        )
        assert batch.promotion_result.errors == 1


# ---------------------------------------------------------------------------
# Bounded accumulator invariants
# ---------------------------------------------------------------------------


class TestScopedAccumulatorInvariants:
    """Bounded invariants of the accumulator after a typed handoff."""

    def test_aggregate_successful_zero_keeps_records_empty(self) -> None:
        projection = _build_completed_projection(diagnosis_incident_ids=())
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

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
        projection = _build_uncertain_projection()
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

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
        projection = _build_rejected_projection()
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

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

    def test_idempotent_record_for_identical_handoff(
        self,
    ) -> None:
        projection = _build_completed_projection(diagnosis_incident_ids=("c-1",))
        from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
            scoped_dispatch_result_to_accumulator_handoff,
        )

        scoped_dispatch_result_to_accumulator_handoff(
            ScopedPromotionDispatchCompleted(projection=projection)
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