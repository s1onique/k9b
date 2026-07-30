"""Active typed scoped dispatcher.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE active typed scoped dispatcher.  The
production scoped path:

::

    one PromoteAlertSignalsRequest
    → ScopedSchedulerClient
    → typed scoped transport mapper
    → ScopedPromotionDispatchResult
    → ScopedPromotionAccumulatorHandoff
    → record_scoped_promotion_batch()

It MUST NOT call:

* legacy dict adapters (``_result_from_dict``)
* ``record_promotion_outcome`` separately
* ``add_batch`` separately
* ``record_scoped_promotion`` compatibility wrapper
* global incident-store scan after a typed scoped outcome

The original :class:`PromotionOutcome`, request ID, request
fingerprint, receipt and reconciliation token MUST remain
preserved by identity.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from .incident_promotion_accumulator import RunPromotionAccumulator
from .incident_promotion_batch import PromotionBatch
from .incident_promotion_dispatch_constants import (
    INCIDENT_ACCESS_MODE_BACKEND,
    MODE_BACKEND_API,
)
from .incident_promotion_result_contract import (
    SCAN_SCOPE_INTERNAL_API_ALERT_SIGNALS_SCOPED,
    IncidentPromotionResult,
)
from .promotion_scoped_accumulator_handoff import (
    ScopedPromotionAccumulatorCompleted,
    ScopedPromotionAccumulatorHandoff,
    ScopedPromotionAccumulatorRejected,
    ScopedPromotionAccumulatorUncertain,
    scoped_dispatch_result_to_accumulator_handoff,
)


def promote_alert_signals_scoped_for_accumulator(
    *,
    runs_dir: Path,
    health_run_id: str,
    source_identity: str,
    signal_ids: tuple[str, ...],
    accumulator: RunPromotionAccumulator | None = None,
    cluster_context: str | None = None,
) -> PromotionBatch:
    """Current-run scoped promotion that NEVER scans the whole tree.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01:
    The active scoped dispatcher consumes the typed
    :class:`ScopedPromotionDispatchResult` directly, converts it
    through :func:`scoped_dispatch_result_to_accumulator_handoff`,
    and forwards the closed handoff to
    :meth:`RunPromotionAccumulator.record_scoped_promotion`. The
    function MUST NOT call
    :func:`scoped_dispatch_result_to_promotion_result_dict`,
    :func:`_result_from_dict`, or any of the legacy dispatch
    helpers. The active scoped path returns a typed
    ``PromotionBatch`` whose ``promotion_result`` carries the
    bounded access mode (``backend`` for completed/uncertain and
    ``reconciliation_required`` for uncertain), with
    ``promotion_records`` deliberately empty for aggregate
    results.
    """
    from .incident_promotion_backend import (
        promote_alert_signals_via_scoped_backend_api,
    )

    if not signal_ids:
        return _build_empty_scoped_batch(
            accumulator=accumulator,
            runs_dir=runs_dir,
            cluster_context=cluster_context,
        )

    # Active scoped path: typed dispatch result is the only
    # authority. The dispatcher does NOT call any legacy
    # ``_result_from_dict``-based shim. The accumulator handoff
    # preserves the original ``PromotionOutcome`` by identity.
    typed_result = promote_alert_signals_via_scoped_backend_api(
        run_id=health_run_id,
        source_identity=source_identity,
        signal_ids=list(signal_ids),
    )

    handoff = scoped_dispatch_result_to_accumulator_handoff(typed_result)

    # Forward the typed handoff to the accumulator. The batch's
    # ``promotion_result`` is derived from the typed outcome so
    # downstream projections stay consistent with the handoff.
    promotion_result = _scoped_promotion_result_from_handoff(
        handoff=handoff,
        signal_ids=signal_ids,
    )
    batch = PromotionBatch(
        promotion_result=promotion_result,
        promotion_records=(),  # aggregate scoped results have no per-signal records
        source_kind="alertmanager",
        cluster_context=cluster_context,
        snapshot_bundle_id=None,
    )
    if accumulator is not None:
        # ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
        # CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01: the
        # active scoped dispatcher makes ONE atomic accumulator
        # mutation call. The legacy ``record_scoped_promotion``,
        # ``add_batch``, and ``record_promotion_outcome`` paths
        # MUST NOT be invoked from this function -- atomic
        # recording, accounting, and outcome-forwarding all
        # happen inside ``record_scoped_promotion_batch``.
        accumulator.record_scoped_promotion_batch(
            handoff=handoff,
            batch=batch,
        )
    return batch


def _scoped_promotion_result_from_handoff(
    *,
    handoff: ScopedPromotionAccumulatorHandoff,
    signal_ids: tuple[str, ...],
) -> IncidentPromotionResult:
    """Project the closed handoff into a typed ``IncidentPromotionResult``.

    The projection is the only authority. Legacy fields
    (``ok``/``errors``/``promotion_records``) are populated
    conservatively so they never contradict the handoff variant.
    """
    if isinstance(handoff, ScopedPromotionAccumulatorCompleted):
        receipt = handoff.receipt
        opened: list[str] = [
            str(value) for value in receipt.opened_incident_ids
        ]
        updated: list[str] = [
            str(value) for value in receipt.materially_changed_incident_ids
        ]
        return IncidentPromotionResult(
            ok=True,
            scanned=len(signal_ids),
            firing=len(signal_ids),
            opened_incidents=len(opened),
            updated_incidents=len(updated),
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=tuple(opened),
            updated_incident_ids=tuple(updated),
            observation_refreshed_incident_ids=tuple(
                str(value) for value in receipt.observation_refreshed_incident_ids
            ),
            unchanged_incident_ids=tuple(
                str(value) for value in receipt.unchanged_incident_ids
            ),
            promotion_records=(),  # never synthesised for the active scoped path
            unique_candidate_count=len(signal_ids),
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
    if isinstance(handoff, ScopedPromotionAccumulatorUncertain):
        return IncidentPromotionResult(
            ok=False,
            scanned=len(signal_ids),
            firing=len(signal_ids),
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            unique_candidate_count=len(signal_ids),
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode="reconciliation_required",
        )
    if isinstance(handoff, ScopedPromotionAccumulatorRejected):
        return IncidentPromotionResult(
            ok=False,
            scanned=len(signal_ids),
            firing=len(signal_ids),
            opened_incidents=0,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=1,
            error_messages=(handoff.outcome.reason.value,),
            promotion_mode=MODE_BACKEND_API,
            promotion_records=(),
            unique_candidate_count=len(signal_ids),
            promotion_scan_scope="internal_api_alert_signals:scoped",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
    # Exhaustiveness: a new handoff variant MUST fail typing.
    assert_never(handoff)


def _build_empty_scoped_batch(
    *,
    accumulator: RunPromotionAccumulator | None,
    runs_dir: Path,
    cluster_context: str | None,
) -> PromotionBatch:
    """Build a backend-scoped empty batch for zero-signal runs.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-
    CORRECTION03-ATOMIC-RECORDING-AND-ACCOUNTING-TRUTH01: the active
    scoped dispatcher MUST NOT mutate the accumulator outside the
    atomic ``record_scoped_promotion_batch`` call.  The empty-batch
    projection is returned for callers without a real handoff; the
    accumulator's legacy ``add_batch`` path is intentionally not used
    here.
    """
    empty_result = IncidentPromotionResult(
        ok=True,
        scanned=0,
        firing=0,
        opened_incidents=0,
        updated_incidents=0,
        skipped_duplicates=0,
        errors=0,
        promotion_mode=MODE_BACKEND_API,
        promotion_scan_scope=SCAN_SCOPE_INTERNAL_API_ALERT_SIGNALS_SCOPED,
        incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
    )
    return PromotionBatch(
        promotion_result=empty_result,
        promotion_records=(),
        source_kind="alertmanager",
        cluster_context=cluster_context,
        snapshot_bundle_id=None,
    )


__all__ = [
    "promote_alert_signals_scoped_for_accumulator",
]