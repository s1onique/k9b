"""Compatibility-batch projection for the scoped atomic recorder.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION04-
REPLAY-TRUTH-AND-ATOMIC-RECORDER-SPLIT01.

This module owns the single
:func:`build_compatibility_batch_from_handoff` helper used by
:meth:`RunPromotionAccumulator.record_scoped_promotion` (the legacy
single-argument compatibility wrapper). The helper projects the
typed handoff variant into the bounded
:class:`IncidentPromotionResult` / :class:`PromotionBatch` shape
that the dispatch contract documents, so legacy unit tests can
reuse the new atomic path while production dispatchers MUST build
their own batch directly and call
:meth:`record_scoped_promotion_batch`.

The projection encodes every aggregate invariant the validators
in :mod:`incident_promotion_scoped_atomic_validation` enforce.
Changing the projection requires changing the validators in
lock-step. The empty-records invariant
``promotion_records == ()`` is therefore re-asserted explicitly here
so an accidental list literal in the future is detected at the
construction site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND,
    MODE_BACKEND_API,
    IncidentPromotionResult,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
)

if TYPE_CHECKING:
    from .incident_promotion_batch import PromotionBatch


_SCAN_SCOPE = "internal_api_alert_signals:scoped"
_SOURCE_KIND = "alertmanager"
_EMPTY_RECORDS: tuple[object, ...] = ()


def _build_completed_projection(
    handoff: ScopedPromotionAccumulatorCompleted,
) -> IncidentPromotionResult:
    """Build the dispatcher-facing :class:`IncidentPromotionResult` for a completed handoff."""
    outcome = handoff.outcome
    receipt = handoff.receipt
    scanned = len(outcome.requested_signal_ids)
    opened_ids = receipt.opened_incident_ids
    updated_ids = receipt.materially_changed_incident_ids
    return IncidentPromotionResult(
        ok=True,
        scanned=scanned,
        firing=scanned,
        opened_incidents=len(opened_ids),
        updated_incidents=len(updated_ids),
        skipped_duplicates=0,
        errors=0,
        promotion_mode=MODE_BACKEND_API,
        opened_incident_ids=tuple(opened_ids),
        updated_incident_ids=tuple(updated_ids),
        observation_refreshed_incident_ids=tuple(
            receipt.observation_refreshed_incident_ids
        ),
        unchanged_incident_ids=tuple(receipt.unchanged_incident_ids),
        promotion_records=(),
        unique_candidate_count=scanned,
        promotion_scan_scope=_SCAN_SCOPE,
        incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
    )


def _build_uncertain_projection(
    handoff: ScopedPromotionAccumulatorUncertain,
) -> IncidentPromotionResult:
    """Build the dispatcher-facing :class:`IncidentPromotionResult` for an uncertain handoff."""
    outcome = handoff.outcome
    scanned = len(outcome.requested_signal_ids)
    return IncidentPromotionResult(
        ok=False,
        scanned=scanned,
        firing=scanned,
        opened_incidents=0,
        updated_incidents=0,
        skipped_duplicates=0,
        errors=0,
        promotion_mode=MODE_BACKEND_API,
        promotion_records=(),
        unique_candidate_count=scanned,
        promotion_scan_scope=_SCAN_SCOPE,
        incident_access_mode="reconciliation_required",
    )


def _build_rejected_projection(
    handoff: ScopedPromotionAccumulatorRejected,
) -> IncidentPromotionResult:
    """Build the dispatcher-facing :class:`IncidentPromotionResult` for a rejected handoff."""
    outcome = handoff.outcome
    scanned = len(outcome.rejected_signal_ids)
    return IncidentPromotionResult(
        ok=False,
        scanned=scanned,
        firing=scanned,
        opened_incidents=0,
        updated_incidents=0,
        skipped_duplicates=0,
        errors=1,
        error_messages=(outcome.reason.value,),
        promotion_mode=MODE_BACKEND_API,
        promotion_records=(),
        unique_candidate_count=scanned,
        promotion_scan_scope=_SCAN_SCOPE,
        incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
    )


def build_compatibility_batch_from_handoff(
    handoff: ScopedPromotionAccumulatorHandoff,
) -> PromotionBatch:
    """Project a typed handoff variant into the bounded ``PromotionBatch``.

    Used ONLY by the
    :meth:`RunPromotionAccumulator.record_scoped_promotion`
    compatibility wrapper. Production dispatchers MUST build their
    own batch directly from the typed dispatcher result and call
    :meth:`record_scoped_promotion_batch`.

    The three variant branches use distinct local variable names so
    mypy does NOT see the same identifier rebound to different
    closed-union outcome types across sequential ``if`` branches.
    """
    from .incident_promotion_batch import PromotionBatch

    if isinstance(handoff, ScopedPromotionAccumulatorCompleted):
        completed_result = _build_completed_projection(handoff)
        return PromotionBatch(
            promotion_result=completed_result,
            promotion_records=(),
            source_kind=_SOURCE_KIND,
            cluster_context=None,
            snapshot_bundle_id=None,
        )
    if isinstance(handoff, ScopedPromotionAccumulatorUncertain):
        uncertain_result = _build_uncertain_projection(handoff)
        return PromotionBatch(
            promotion_result=uncertain_result,
            promotion_records=(),
            source_kind=_SOURCE_KIND,
            cluster_context=None,
            snapshot_bundle_id=None,
        )
    if isinstance(handoff, ScopedPromotionAccumulatorRejected):
        rejected_result = _build_rejected_projection(handoff)
        return PromotionBatch(
            promotion_result=rejected_result,
            promotion_records=(),
            source_kind=_SOURCE_KIND,
            cluster_context=None,
            snapshot_bundle_id=None,
        )
    from typing import assert_never

    assert_never(handoff)


__all__ = ["build_compatibility_batch_from_handoff"]
