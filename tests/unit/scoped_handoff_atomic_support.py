"""Shared builders for the scoped handoff atomic-recording test matrix.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

The fixtures keep every scoped aggregate result free of fabricated
``PromotionRecord`` entries. The diagnosis IDs / receipt aggregates
already carry the authoritative aggregate result; the supporting
projections below pass ``records=()`` even when ``diagnosis_incident_ids``
are non-empty, so the
:data:`SCOPED_RECORD_FABRICATION` invariant remains ``false``.

The compatibility batch builder delegates to the production
projection module, :func:`build_compatibility_batch_from_handoff`,
so every test exercises the same accounting projection the
dispatcher would build.
"""

from __future__ import annotations

from typing import Any

from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_scoped_atomic_projection import (  # noqa: E501
    build_compatibility_batch_from_handoff,
)
from k8s_diag_agent.collect.promotion_outcomes import (
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

# Constant fingerprints for tests; never mixed.
_FP_COMPLETED = "a" * 64
_FP_UNCERTAIN = "b" * 64
_FP_REJECTED = "c" * 64


def make_completed_projection(
    *,
    run_id: str = "run-correction03-atomic-completed",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(5)
    ),
    diagnosis_incident_ids: tuple[str, ...] = (),
) -> ScopedPromotionCompletedProjection:
    """Build a completed projection with empty aggregate (records=()).

    The closed :class:`PromotionSucceeded` carries ``records=()`` for
    every aggregate result. Diagnosis IDs live on the outcome's
    ``diagnosis_incident_ids`` field and on the receipt's
    ``opened_incident_ids``; per-signal fabrication is forbidden.
    """

    bound_obj = _make_bound(
        run_id=run_id,
        requested_signal_ids=requested_signal_ids,
        diagnosis_incident_ids=diagnosis_incident_ids,
    )
    return ScopedPromotionCompletedProjection(
        promotion_outcome=PromotionSucceeded(
            run_id=run_id,
            requested_signal_ids=requested_signal_ids,
            records=(),  # SCOPED_RECORD_FABRICATION invariant
            diagnosis_incident_ids=diagnosis_incident_ids,
        ),
        aggregate_receipt=ScopedPromotionReceipt(bound=bound_obj),
        request_id="promotion-request-completed-correction03",
        request_fingerprint=_FP_COMPLETED,
    )


def make_uncertain_projection(
    *,
    run_id: str = "run-correction03-atomic-uncertain",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(5)
    ),
) -> ScopedPromotionUncertainProjection:
    """Build an uncertain projection with empty aggregate (records=())."""
    # Defensive: dump-guard so a future regression that re-introduces
    # per-signal fabrication here is detected loudly.

    return ScopedPromotionUncertainProjection(
        promotion_outcome=PromotionCommitUnknown(
            run_id=run_id,
            reason=PromotionUncertaintyCode.HTTP_RESPONSE_TRUNCATED,
            reconciliation_token=PromotionReconciliationToken(
                request_id="promotion-request-uncertain-correction03",
                request_fingerprint=_FP_UNCERTAIN,
            ),
            requested_signal_ids=requested_signal_ids,
        ),
        request_id="promotion-request-uncertain-correction03",
        request_fingerprint=_FP_UNCERTAIN,
    )


def make_rejected_projection(
    *,
    run_id: str = "run-correction03-atomic-rejected",
    requested_signal_ids: tuple[str, ...] = tuple(
        f"sig-{i:02d}" for i in range(5)
    ),
) -> ScopedPromotionRejectedProjection:
    """Build a rejected projection with empty aggregate (records=())."""
    return ScopedPromotionRejectedProjection(
        promotion_outcome=PromotionRejected(
            run_id=run_id,
            reason=PromotionRejectionCode.BACKEND_UNREACHABLE,
            rejected_signal_ids=requested_signal_ids,
        ),
        request_id="promotion-request-rejected-correction03",
        request_fingerprint=_FP_REJECTED,
    )


def to_handoff(
    result: ScopedPromotionDispatchResult,
) -> ScopedPromotionAccumulatorHandoff:
    """Convert a typed dispatch result to its accumulator handoff."""
    from k8s_diag_agent.collect.promotion_scoped_accumulator_handoff import (
        scoped_dispatch_result_to_accumulator_handoff,
    )

    return scoped_dispatch_result_to_accumulator_handoff(result)


def completed_handoff(**kwargs: Any) -> ScopedPromotionAccumulatorCompleted:
    """Build a completed handoff variant from the typed dispatch projection."""
    projection = make_completed_projection(**kwargs)
    return to_handoff(
        ScopedPromotionDispatchCompleted(projection=projection)
    )  # type: ignore[return-value]


def uncertain_handoff(**kwargs: Any) -> ScopedPromotionAccumulatorUncertain:
    """Build an uncertain handoff variant from the typed dispatch projection."""
    projection = make_uncertain_projection(**kwargs)
    return to_handoff(
        ScopedPromotionDispatchUncertain(projection=projection)
    )  # type: ignore[return-value]


def rejected_handoff(**kwargs: Any) -> ScopedPromotionAccumulatorRejected:
    """Build a rejected handoff variant from the typed dispatch projection."""
    projection = make_rejected_projection(**kwargs)
    return to_handoff(
        ScopedPromotionDispatchRejected(projection=projection)
    )  # type: ignore[return-value]


def make_completed_batch(
    *, handoff: ScopedPromotionAccumulatorCompleted
) -> Any:
    """Project a typed handoff into the dispatcher's accounting batch.

    Delegates to the production projection module so the tests
    exercise the same accounting projection the dispatcher would
    build.
    """
    return build_compatibility_batch_from_handoff(handoff)


def make_batch_for_handoff(handoff: ScopedPromotionAccumulatorHandoff) -> Any:
    """Return the bounded accounting batch for any handoff variant."""
    return build_compatibility_batch_from_handoff(handoff)


def _make_bound(
    *,
    run_id: str,
    requested_signal_ids: tuple[str, ...],
    diagnosis_incident_ids: tuple[str, ...],
) -> Any:
    from k8s_diag_agent.domain.identifiers import AlertSignalId
    from k8s_diag_agent.domain.incident_lifecycle import IncidentId
    from k8s_diag_agent.incident_alert_promotion_binding import (
        BoundScopedPromotionResult,
    )
    from k8s_diag_agent.incident_alert_promotion_contract import (
        IncidentPromotionResult,
        PromoteAlertSignalsRequest,
    )

    typed_signals = tuple(AlertSignalId(v) for v in requested_signal_ids)
    typed_opened = tuple(IncidentId(v) for v in diagnosis_incident_ids)
    success = IncidentPromotionResult(
        run_id=run_id,
        source_identity="source-correction03-atomic",
        scanned_signal_ids=typed_signals,
        opened_incident_ids=typed_opened,
    )
    return BoundScopedPromotionResult(
        request=PromoteAlertSignalsRequest(
            run_id=run_id,
            source_identity="source-correction03-atomic",
            signal_ids=typed_signals,
        ),
        result=success,
    )


def accumulator_snapshot(acc: RunPromotionAccumulator) -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of every accumulator field."""
    return {
        "promotion_records": list(acc.promotion_records),
        "_seen_canonical_ids": set(acc._seen_canonical_ids),
        "batches": list(acc.batches),
        "total_scanned": acc.total_scanned,
        "total_firing": acc.total_firing,
        "total_opened_incidents": acc.total_opened_incidents,
        "total_updated_incidents": acc.total_updated_incidents,
        "total_skipped_duplicates": acc.total_skipped_duplicates,
        "total_errors": acc.total_errors,
        "total_unique_candidate_count": acc.total_unique_candidate_count,
        "last_promotion_mode": acc.last_promotion_mode,
        "last_incident_access_mode": acc.last_incident_access_mode,
        "last_source_kind": acc.last_source_kind,
        "last_promotion_scan_scope": acc.last_promotion_scan_scope,
        "promotion_outcome": acc.promotion_outcome,
        "promotion_outcome_run_id": acc.promotion_outcome_run_id,
        "scoped_promotion_handoff": acc.scoped_promotion_handoff,
    }
