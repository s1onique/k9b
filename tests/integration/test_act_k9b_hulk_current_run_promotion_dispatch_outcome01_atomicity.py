"""Two-real-ingestion atomicity regression for Item-3 closure.

Proves that two calls through _ingest_alert_signals() preserve
accumulator and observable state when the second outcome conflicts.

ACT-K9B-HULK-CURRENT-RUN-PROMOTION-DISPATCH-OUTCOME01-CLOSURE.

Reviewer blocking item: the existing test only proves accumulator.record_promotion_outcome()
raises on conflict, not that the production _ingest_alert_signals() path preserves
state when the second ingestion produces a conflicting outcome.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from k8s_diag_agent.collect.incident_promotion_outcome_recorder import (
    PromotionOutcomeConflictError,
)
from k8s_diag_agent.health.loop_alertmanager_snapshot_signals import (
    AlertSignalPromotionDispatchResult,
    _ingest_alert_signals,
)

from .incident_current_run_promotion_dispatch_outcome01_support import (
    RUN_ID,
    CapturingLog,
    build_alert,
    build_snapshot,
    build_source,
    persist_signals,
)


def _stub_dispatch_with_result(
    monkeypatch: pytest.MonkeyPatch,
    promotion_result: IncidentPromotionResult,
    batch_records: tuple[PromotionRecord, ...] = (),
    opened_incidents: int | None = None,
    updated_incidents: int | None = None,
) -> None:
    """Stub the dispatcher with a controlled result.

    The stub returns a PromotionBatch where counts match the records so
    that _validate_response_contracts passes (backend mode validation).
    """
    from k8s_diag_agent.collect import (
        incident_promotion_batch as batch_module,
    )
    from k8s_diag_agent.collect import (
        incident_promotion_dispatch as dispatch_module,
    )

    # Count canonical IDs from records to set aggregates correctly on result
    opened_count = opened_incidents
    updated_count = updated_incidents
    if opened_count is None:
        opened_count = sum(
            1 for r in batch_records if r.promotion_outcome == PROMOTION_OUTCOME_OPENED
        )
    if updated_count is None:
        updated_count = 0

    # Make a mutable copy of the result with correct counts
    # IncidentPromotionResult is frozen, so we need to create a new one
    result_with_counts = IncidentPromotionResult(
        ok=promotion_result.ok,
        opened_incident_ids=promotion_result.opened_incident_ids,
        updated_incident_ids=promotion_result.updated_incident_ids,
        promotion_mode=promotion_result.promotion_mode,
        promotion_records=batch_records,
        promotion_scan_scope=promotion_result.promotion_scan_scope,
        incident_access_mode=promotion_result.incident_access_mode,
        opened_incidents=opened_count,
        updated_incidents=updated_count,
        scanned=0,
        firing=0,
        skipped_duplicates=0,
        unique_candidate_count=0,
        error_messages=(),
    )

    def dispatch_stub(*_args: Any, **_kwargs: Any) -> Any:
        return batch_module.PromotionBatch(
            promotion_result=result_with_counts,
            promotion_records=batch_records,
            source_kind="alertmanager",
            cluster_context=None,
            snapshot_bundle_id=None,
        )

    monkeypatch.setattr(
        dispatch_module,
        "promote_alert_signals_scoped_for_accumulator",
        dispatch_stub,
    )


class TestTwoRealIngestionAtomicity:
    """The production _ingest_alert_signals() path preserves state on conflict.

    Invariant: the one-dispatch-per-accumulator cardinality invariant
    requires that when the second ingestion produces a conflicting outcome,
    the accumulator state (outcome, records, IDs, counters) remains unchanged.
    """

    def test_second_conflicting_ingestion_preserves_accumulator_state(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two _ingest_alert_signals calls: second produces conflicting outcome.

        First ingestion: succeeds with one canonical ID.
        Second ingestion: produces a REJECTED outcome (different variant).

        The accumulator MUST preserve the first outcome and all its
        derived state; the conflict error is raised but state is unchanged.
        """
        runs_dir = tmp_path / "runs"
        # Persist signals so the second snapshot can reference them
        persist_signals(runs_dir, 5)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        # --- First ingestion: successful outcome ---
        first_records = (
            PromotionRecord(
                source_candidate_id="alert-1",
                canonical_incident_id="inc-first",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
        )
        first_result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("inc-first",),
            updated_incident_ids=(),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=first_records,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        _stub_dispatch_with_result(monkeypatch, first_result, first_records)

        snapshot1 = build_snapshot([build_alert(i) for i in range(5)])
        log1 = CapturingLog()
        _ingest_alert_signals(
            snapshot=snapshot1,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=log1,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )

        # Capture state after first ingestion
        first_outcome = accumulator.promotion_outcome
        first_run_id = accumulator.promotion_outcome_run_id
        first_recorded = accumulator.recorded_records()
        first_ids = accumulator.canonical_incident_ids()
        first_propagated = accumulator.diagnosis_handoff_available()
        first_snap = accumulator._snapshot()

        assert first_outcome is not None
        assert first_run_id == RUN_ID
        assert len(first_recorded) == 1
        assert first_ids == ["inc-first"]
        assert first_propagated is True

        # --- Replace dispatcher stub: second ingestion produces REJECTED outcome ---
        second_result = IncidentPromotionResult(
            ok=False,
            opened_incident_ids=(),
            updated_incident_ids=(),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        _stub_dispatch_with_result(monkeypatch, second_result, ())

        snapshot2 = build_snapshot([build_alert(i) for i in range(5, 10)])
        log2 = CapturingLog()

        # Second ingestion should raise PromotionOutcomeConflictError because
        # the classified outcome is PromotionCommitUnknown (generic ok=False),
        # which conflicts with the first PromotionSucceeded outcome.
        # NOTE: Generic ok=False is now mapped to PromotionCommitUnknown, not
        # PromotionRejected. We use a typed rejection to get a genuinely
        # conflicting variant.
        from k8s_diag_agent.collect.promotion_dispatch_outcome import (
            PromotionRequestValidationError,
        )

        def rejecting_dispatch(*_args: Any, **_kwargs: Any) -> Any:
            raise PromotionRequestValidationError("malformed signal ids")

        from k8s_diag_agent.collect import (
            incident_promotion_batch as batch_module,
        )
        from k8s_diag_agent.collect import (
            incident_promotion_dispatch as dispatch_module,
        )

        def conflicting_dispatch(*_args: Any, **_kwargs: Any) -> Any:
            # Return a batch that will classify as PromotionRejected
            return batch_module.PromotionBatch(
                promotion_result=second_result,
                promotion_records=(),
                source_kind="alertmanager",
                cluster_context=None,
                snapshot_bundle_id=None,
            )

        # Stub the dispatcher to produce a REJECTED outcome
        # by raising a typed pre-commit rejection
        def typed_rejection_dispatch(*_args: Any, **_kwargs: Any) -> Any:
            raise PromotionRequestValidationError("malformed signal ids")

        monkeypatch.setattr(
            dispatch_module,
            "promote_alert_signals_scoped_for_accumulator",
            typed_rejection_dispatch,
        )

        # Second ingestion produces a conflicting outcome (PromotionRejected
        # vs the first PromotionSucceeded). The ONLY acceptable exception is
        # PromotionOutcomeConflictError -- if PromotionRequestValidationError
        # escapes, the classification step was bypassed, which is a wiring
        # failure that the test must detect.
        with pytest.raises(PromotionOutcomeConflictError) as exc_info:
            _ingest_alert_signals(
                snapshot=snapshot2,
                selected_source=build_source(),
                snapshot_path=None,
                directories={"root": runs_dir},
                incident_store=None,
                log_event=log2,
                run_id=RUN_ID,  # same run_id
                run_label="run-2026-07-15T0340Z",
                effective_cluster_context=None,
                promotion_accumulator=accumulator,
            )

        # Assert exact exception type (not a subclass) for strict contract.
        assert exc_info.type is PromotionOutcomeConflictError

        # Assert structured conflict attributes for audit-log routing.
        assert exc_info.value.running_run_id == RUN_ID
        assert exc_info.value.running_variant == "succeeded"
        assert exc_info.value.rejected_variant == "rejected"

        # --- Assert accumulator state is unchanged (individual field comparison) ---
        # These assertions prove that the second conflicting ingestion did NOT
        # modify any accumulator state. The individual field checks are more
        # reliable than _snapshot() comparison since we can't capture the
        # exact pre-rejection snapshot after the fact.
        assert accumulator.promotion_outcome is first_outcome
        assert accumulator.promotion_outcome is not None
        assert accumulator.promotion_outcome_run_id == first_run_id
        assert accumulator.recorded_records() == first_recorded
        assert accumulator.canonical_incident_ids() == first_ids
        assert accumulator.diagnosis_handoff_available() == first_propagated
        assert len(accumulator.batches) == 1  # Only the first batch

        # --- Assert no second handoff-completed event ---
        handoff_events = log2.by_event("promotion-handoff-completed")
        assert len(handoff_events) == 0, "Second ingestion should not emit handoff-completed"

        # --- Assert no dispatch-outcome-classified event after conflict ---
        classified_events = log2.by_event("promotion-dispatch-outcome-classified")
        assert len(classified_events) == 0, (
            "Conflicting authority was not emitted after the recorder rejected it"
        )

        # --- Assert no second promoted event ---
        promoted_events = log2.by_event("alert-signals-promoted")
        promoted_via_backend = log2.by_event("alert-signals-promoted-via-backend")
        assert len(promoted_events) == 0, "Second ingestion should not emit promoted event"
        assert len(promoted_via_backend) == 0, "Second ingestion should not emit promoted-via-backend event"

        # --- Full snapshot comparison: state must be identical after conflict ---
        snap_after_conflict = accumulator._snapshot()
        assert snap_after_conflict == first_snap, (
            "Accumulator snapshot changed after conflicting ingestion; "
            "atomicity invariant violated"
        )

    def test_idempotent_second_ingestion_accepted(
        self,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Identical second ingestion is idempotent and does not repeat handoff.

        The one-dispatch/idempotency invariant requires that:
        1. Identical retry is accepted without raising
        2. Exactly ONE promotion-handoff-completed event is emitted (from the first)
        3. Full accumulator snapshot is identical before and after second ingestion
        """
        runs_dir = tmp_path / "runs"
        persist_signals(runs_dir, 5)
        accumulator = RunPromotionAccumulator()
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "local")

        records = (
            PromotionRecord(
                source_candidate_id="alert-1",
                canonical_incident_id="inc-1",
                promotion_outcome=PROMOTION_OUTCOME_OPENED,
            ),
        )
        result = IncidentPromotionResult(
            ok=True,
            opened_incident_ids=("inc-1",),
            updated_incident_ids=(),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=records,
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="backend",
        )
        _stub_dispatch_with_result(monkeypatch, result, records)

        snapshot = build_snapshot([build_alert(i) for i in range(5)])
        log = CapturingLog()

        # First ingestion
        first = _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=log,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )

        # Capture full state after first ingestion
        first_outcome = accumulator.promotion_outcome
        first_snap = accumulator._snapshot()

        # Second ingestion with IDENTICAL outcome should be idempotent
        second = _ingest_alert_signals(
            snapshot=snapshot,
            selected_source=build_source(),
            snapshot_path=None,
            directories={"root": runs_dir},
            incident_store=None,
            log_event=log,
            run_id=RUN_ID,
            run_label="run-2026-07-15T0340Z",
            effective_cluster_context=None,
            promotion_accumulator=accumulator,
        )

        # Both calls succeed; state is unchanged from first
        assert isinstance(first, AlertSignalPromotionDispatchResult)
        assert isinstance(second, AlertSignalPromotionDispatchResult)
        assert second.outcome == first.outcome
        assert accumulator.promotion_outcome is first_outcome
        assert accumulator.canonical_incident_ids() == ["inc-1"]

        # Full accumulator snapshot must be identical (no duplicated counters,
        # records, propagation metadata, or handoff events).
        snap_after_second = accumulator._snapshot()
        assert snap_after_second == first_snap, (
            "Accumulator snapshot changed after second identical ingestion; "
            "idempotency invariant violated"
        )

        # Exactly ONE handoff-completed event (from the first ingestion).
        # The second identical ingestion must NOT emit another.
        handoff_events = log.by_event("promotion-handoff-completed")
        assert len(handoff_events) == 1, (
            f"Expected exactly 1 promotion-handoff-completed event, "
            f"got {len(handoff_events)}; "
            "idempotent retry must not repeat the compatibility handoff"
        )
