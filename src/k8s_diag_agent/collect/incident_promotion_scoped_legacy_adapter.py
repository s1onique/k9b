"""Legacy dict-shaped compatibility adapter for the scoped promotion path.

ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01.

This module holds the legacy flat-dict compatibility surface for the
scoped promotion path. The active dispatcher path MUST NOT import
this module. The legacy surface is intentionally isolated here so
the active path's typed authority can never be re-derived from a
free-form dict.

The module exposes:

* :func:`scoped_dispatch_result_to_promotion_result_dict` -- a
  conversion from the typed
  :class:`ScopedPromotionDispatchResult` to the legacy dispatcher
  flat-dict shape. The conversion is the only place that knows the
  legacy shape.
* :func:`promote_alert_signals_via_scoped_backend_api_as_dict` --
  a single-call wrapper that returns the legacy flat-dict shape for
  legacy callers that still consume the dispatcher dict.

The module is intentionally not exported from the active scoped
backend façade. Importing it from
:mod:`k8s_diag_agent.collect.incident_promotion_dispatch`,
:mod:`k8s_diag_agent.health.loop_runner*`, the automatic-diagnosis
modules, or :mod:`k8s_diag_agent.collect.promotion_scoped_accumulator_handoff`
is a contract violation.
"""

from __future__ import annotations

import os
from typing import Any

from ..domain.identifiers import AlertSignalId, HealthRunId
from ..incident_alert_promotion_contract import PromoteAlertSignalsRequest
from ..ui.server_incident_internal_scoped_client import ScopedSchedulerClient
from .promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
    ScopedTransportPromotionProjection,
    map_scoped_http_transport_to_promotion_outcome,
)
from .promotion_scoped_http_seam import (
    ScopedPromotionDispatchCompleted,
    ScopedPromotionDispatchRejected,
    ScopedPromotionDispatchResult,
    ScopedPromotionDispatchUncertain,
    ScopedPromotionHttpRequestContext,
)


def _projection_to_dispatch_result(
    projection: ScopedTransportPromotionProjection,
) -> ScopedPromotionDispatchResult:
    """Convert a closed projection into the typed dispatch result.

    The dispatch result is a closed union whose variants carry
    the closed projection algebra; downstream consumers MUST
    narrow on the concrete variant.
    """
    if isinstance(projection, ScopedPromotionCompletedProjection):
        return ScopedPromotionDispatchCompleted(projection=projection)
    if isinstance(projection, ScopedPromotionUncertainProjection):
        return ScopedPromotionDispatchUncertain(projection=projection)
    if isinstance(projection, ScopedPromotionRejectedProjection):
        return ScopedPromotionDispatchRejected(projection=projection)
    # Exhaustiveness: a new projection variant MUST fail typing.
    from typing import assert_never

    assert_never(projection)


def _legacy_promote_alert_signals_via_scoped_backend_api(
    *,
    run_id: str,
    source_identity: str,
    signal_ids: list[str],
) -> ScopedPromotionDispatchResult:
    """Internal helper that wraps the typed dispatcher result.

    The legacy adapter keeps the wiring local so the active path
    remains free of any flat-dict derivation logic.
    """
    backend_url = os.environ.get("K9B_BACKEND_INTERNAL_URL")
    internal_api_token = os.environ.get("K9B_INTERNAL_API_TOKEN")
    request = PromoteAlertSignalsRequest(
        run_id=HealthRunId(run_id),
        source_identity=source_identity,
        signal_ids=tuple(AlertSignalId(value) for value in signal_ids),
    )
    import uuid

    context = ScopedPromotionHttpRequestContext(
        request=request,
        request_id=f"promotion-request-{uuid.uuid4().hex}",
    )
    client = ScopedSchedulerClient(
        base_url=backend_url or "",
        token=internal_api_token,
    )
    transport = client.promote_alert_signals_scoped(context=context)
    projection = map_scoped_http_transport_to_promotion_outcome(
        transport, context=context
    )
    return _projection_to_dispatch_result(projection)


def scoped_dispatch_result_to_promotion_result_dict(
    result: ScopedPromotionDispatchResult,
    *,
    signal_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Convert a typed :class:`ScopedPromotionDispatchResult` to the
    dispatcher dict shape.

    Legacy compatibility only. The active dispatcher path MUST NOT
    consume this helper. The helper is intentionally confined to
    this legacy adapter so a future audit can detect any drift
    between the typed authority and the legacy shape.
    """
    basis = {
        "scanned": len(signal_ids),
        "firing": len(signal_ids),
        "skipped_duplicates": 0,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
        "unique_candidate_count": len(signal_ids),
        "promotion_records": [],
        "opened_incident_ids": [],
        "updated_incident_ids": [],
        "observation_refreshed_incident_ids": [],
        "unchanged_incident_ids": [],
        "canonical_incident_ids": [],
        "errors": 0,
        "error_messages": [],
    }
    if isinstance(result, ScopedPromotionDispatchCompleted):
        projection = result.projection
        outcome = projection.promotion_outcome
        receipt = projection.aggregate_receipt
        opened = list(receipt.opened_incident_ids)
        updated = list(receipt.materially_changed_incident_ids)
        observation = list(receipt.observation_refreshed_incident_ids)
        unchanged = list(receipt.unchanged_incident_ids)
        canonical = list(outcome.diagnosis_incident_ids)
        return {
            **basis,
            "ok": True,
            "opened_incidents": len(opened),
            "updated_incidents": len(updated),
            "opened_incident_ids": [str(value) for value in opened],
            "updated_incident_ids": [str(value) for value in updated],
            "observation_refreshed_incident_ids": [
                str(value) for value in observation
            ],
            "unchanged_incident_ids": [str(value) for value in unchanged],
            "canonical_incident_ids": [str(value) for value in canonical],
        }
    if isinstance(result, ScopedPromotionDispatchRejected):
        rejected_projection = result.projection
        outcome = rejected_projection.promotion_outcome
        return {
            **basis,
            "ok": False,
            "opened_incidents": 0,
            "updated_incidents": 0,
            "errors": 1,
            "error_messages": [outcome.reason.value],
            "incident_access_mode": "backend",
        }
    if isinstance(result, ScopedPromotionDispatchUncertain):
        uncertain_projection = result.projection
        outcome = uncertain_projection.promotion_outcome
        return {
            **basis,
            "ok": False,
            "opened_incidents": 0,
            "updated_incidents": 0,
            "errors": 0,
            "error_messages": [outcome.reason.value],
            "incident_access_mode": "reconciliation_required",
        }
    from typing import assert_never

    assert_never(result)


def promote_alert_signals_via_scoped_backend_api_as_dict(
    *,
    run_id: str,
    source_identity: str,
    signal_ids: list[str],
) -> dict[str, Any]:
    """Return the legacy dispatcher dict shape for the typed scoped promotion.

    Legacy compatibility only. The active dispatcher path MUST NOT
    consume this helper. New callers consume the typed dispatch
    result and forward it through
    :func:`scoped_dispatch_result_to_accumulator_handoff`.
    """
    result = _legacy_promote_alert_signals_via_scoped_backend_api(
        run_id=run_id,
        source_identity=source_identity,
        signal_ids=signal_ids,
    )
    return scoped_dispatch_result_to_promotion_result_dict(
        result, signal_ids=tuple(signal_ids)
    )


__all__ = [
    "promote_alert_signals_via_scoped_backend_api_as_dict",
    "scoped_dispatch_result_to_promotion_result_dict",
]