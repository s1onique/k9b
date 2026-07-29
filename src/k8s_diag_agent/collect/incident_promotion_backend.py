"""Backend API incident promotion implementation.

This module provides the backend API promotion path for incident candidates,
used when the scheduler runs separately from the incident store (SQLite mode).

The active production dispatcher path is
:func:`promote_alert_signals_via_scoped_backend_api`, which constructs
exactly one canonical :class:`PromoteAlertSignalsRequest`, invokes
:class:`ScopedSchedulerClient`, and routes the typed transport
outcome through
:func:`map_scoped_http_transport_to_promotion_outcome`. The legacy
snake_case dispatch helpers and the
``_coerce_promotion_response`` ambiguity helper are kept for the
legacy endpoints only.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any

from ..domain.identifiers import AlertSignalId, HealthRunId
from ..incident_alert_promotion_contract import (
    IncidentPromotionResult as _TypedPromotionResult,
)
from ..incident_alert_promotion_contract import (
    PromoteAlertSignalsRequest,
)
from ..ui.server_incident_internal_client import SchedulerClient
from ..ui.server_incident_internal_models import PromotionResponse
from ..ui.server_incident_internal_scoped_client import ScopedSchedulerClient
from .incident_candidate_serialization import incident_candidates_to_dict_list
from .incident_candidates import IncidentCandidate
from .promotion_outcomes import (
    PromotionRejectionCode,
)
from .promotion_scoped_http_mapping import (
    ScopedPromotionCompletedProjection,
    ScopedPromotionRejectedProjection,
    ScopedPromotionUncertainProjection,
    ScopedTransportPromotionProjection,
    map_scoped_http_transport_to_promotion_outcome,
)
from .promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
)

_logger = logging.getLogger(__name__)

# Backend API mode
MODE_BACKEND_API = "backend-api"


def _extract_canonical_ids(response: PromotionResponse | object) -> dict[str, Any]:
    """Return canonical IDs / records from a PromotionResponse-like object.

    SchedulerClient promotes return dataclass-based PromotionResponse
    instances. We duck-attach to avoid coupling to internal-field renaming,
    defaulting to empty values when the backend predates the
    canonical-id propagation contract.
    """
    return {
        "opened_incident_ids": list(getattr(response, "opened_incident_ids", []) or []),
        "updated_incident_ids": list(
            getattr(response, "updated_incident_ids", []) or []
        ),
        "promotion_records": [
            dict(record)
            for record in (getattr(response, "promotion_records", []) or [])
        ],
        "unique_candidate_count": int(
            getattr(response, "unique_candidate_count", 0) or 0
        ),
        "promotion_scan_scope": str(
            getattr(response, "promotion_scan_scope", "") or ""
        ),
        "incident_access_mode": str(
            getattr(response, "incident_access_mode", "backend") or "backend"
        ),
    }


def _coerce_promotion_response(value: Any) -> PromotionResponse:
    """Coerce either a dict or a ``PromotionResponse`` to ``PromotionResponse``."""
    if isinstance(value, PromotionResponse):
        return value
    if isinstance(value, dict):
        return PromotionResponse(**value)
    # Fallback: bounded error result so the dispatcher can still
    # project the canonical totals without raising.
    return PromotionResponse(ok=False, errors=1, error_messages=[str(value)])


def _typed_result_to_dispatch_dict(
    typed: _TypedPromotionResult,
) -> dict[str, Any]:
    """Translate the typed wire result into the dispatcher's legacy dict shape.

    The dict still carries the new ``observation_refreshed`` and
    ``unchanged`` categories so the scheduler log line (and the
    accumulator) preserve the typed projection end-to-end.
    """
    canonical_ids = list(typed.actionable_incident_ids)
    opened_ids = list(typed.opened_incident_ids)
    updated_ids = list(typed.materially_changed_incident_ids)
    observation_ids = list(typed.observation_refreshed_incident_ids)
    unchanged_ids = list(typed.unchanged_incident_ids)
    scanned = list(typed.scanned_signal_ids)
    unique = len(scanned)
    promotion_records: list[dict[str, str | None]] = []
    for incident_id in opened_ids:
        promotion_records.append(
            {
                "source_candidate_id": "<scoped>",
                "canonical_incident_id": str(incident_id),
                "promotion_outcome": "opened",
            }
        )
    for incident_id in updated_ids:
        promotion_records.append(
            {
                "source_candidate_id": "<scoped>",
                "canonical_incident_id": str(incident_id),
                "promotion_outcome": "updated",
            }
        )
    for incident_id in observation_ids:
        promotion_records.append(
            {
                "source_candidate_id": "<scoped>",
                "canonical_incident_id": str(incident_id),
                "promotion_outcome": "observation_refreshed",
            }
        )
    for incident_id in unchanged_ids:
        promotion_records.append(
            {
                "source_candidate_id": "<scoped>",
                "canonical_incident_id": str(incident_id),
                "promotion_outcome": "unchanged",
            }
        )
    return {
        "ok": True,
        "scanned": unique,
        "firing": unique,
        "opened_incidents": len(opened_ids),
        "updated_incidents": len(updated_ids),
        "skipped_duplicates": len(typed.skipped_signal_ids),
        "errors": len(typed.failures),
        "error_messages": [
            f"{failure.signal_id}:{failure.reason_code}:{failure.detail or ''}"
            for failure in typed.failures
        ],
        "opened_incident_ids": [str(value) for value in opened_ids],
        "updated_incident_ids": [str(value) for value in updated_ids],
        "observation_refreshed_incident_ids": [
            str(value) for value in observation_ids
        ],
        "unchanged_incident_ids": [str(value) for value in unchanged_ids],
        "canonical_incident_ids": [str(value) for value in canonical_ids],
        "promotion_records": promotion_records,
        "unique_candidate_count": unique,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


def _response_to_promotion_result(response: Any) -> dict[str, Any]:
    """Translate a backend response into a result dict for the dispatcher.

    Accepts:

    * the typed ``IncidentPromotionResult`` instance (camelCase
      projection already decoded by the contract)
    * a raw camelCase ``dict`` from the scoped
      ``/promote-alert-signals`` endpoint (parsed via
      :meth:`IncidentPromotionResult.from_wire_dict`)
    * the legacy ``PromotionResponse`` (returned by
      ``/promote-candidates``) so existing call sites keep working.

    The new typed contract is parsed by
    :meth:`IncidentPromotionResult.from_wire_dict` so a malformed
    payload cannot masquerade as a successful promotion.
    """
    # Typed projection already decoded.
    if isinstance(response, _TypedPromotionResult):
        return _typed_result_to_dispatch_dict(response)

    # Raw camelCase wire payload from the new scoped endpoint.
    if isinstance(response, dict):
        try:
            typed = _TypedPromotionResult.from_wire_dict(response)
        except Exception as exc:
            _logger.warning(
                "Scoped promotion wire payload failed to parse; "
                "failing closed without passing through legacy model",
                extra={
                    "event": "scoped-promotion-wire-parse-failed",
                    "error": str(exc),
                },
            )
            return {
                "ok": False,
                "scanned": len(response) if hasattr(response, "__len__") else 0,
                "firing": 0,
                "opened_incidents": 0,
                "updated_incidents": 0,
                "skipped_duplicates": 0,
                "errors": 1,
                "error_messages": [str(exc)],
                "opened_incident_ids": [],
                "updated_incident_ids": [],
                "observation_refreshed_incident_ids": [],
                "unchanged_incident_ids": [],
                "canonical_incident_ids": [],
                "promotion_records": [],
                "unique_candidate_count": 0,
                "promotion_scan_scope": "internal_api_alert_signals:scoped",
                "incident_access_mode": "backend",
            }
        return _typed_result_to_dispatch_dict(typed)

    # Legacy / typed-result-from-other-paths fallback.
    coerced = _coerce_promotion_response(response)
    canonical = _extract_canonical_ids(coerced)
    return {
        "ok": coerced.ok,
        "scanned": coerced.scanned,
        "firing": coerced.firing,
        "opened_incidents": coerced.opened_incidents,
        "updated_incidents": coerced.updated_incidents,
        "skipped_duplicates": coerced.skipped_duplicates,
        "errors": coerced.errors,
        "error_messages": list(coerced.error_messages),
        "opened_incident_ids": canonical["opened_incident_ids"],
        "updated_incident_ids": canonical["updated_incident_ids"],
        "observation_refreshed_incident_ids": [],
        "unchanged_incident_ids": [],
        "canonical_incident_ids": (
            canonical["opened_incident_ids"] + canonical["updated_incident_ids"]
        ),
        "promotion_records": canonical["promotion_records"],
        "unique_candidate_count": canonical["unique_candidate_count"],
        "promotion_scan_scope": canonical["promotion_scan_scope"],
        "incident_access_mode": canonical["incident_access_mode"],
    }


def promote_via_backend_api(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Promote generic candidates via backend internal API."""
    backend_url = os.environ.get("K9B_BACKEND_INTERNAL_URL")
    internal_api_token = os.environ.get("K9B_INTERNAL_API_TOKEN")

    if not backend_url or not internal_api_token:
        return {
            "ok": False,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [
                "Backend API configuration incomplete: missing backend_url or internal_api_token"
            ],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "",
            "incident_access_mode": "backend",
        }

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    candidate_dicts = incident_candidates_to_dict_list(candidates)

    try:
        response = client.promote_candidates(
            candidates=candidate_dicts,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )
        return _response_to_promotion_result(response)
    except Exception as exc:
        _logger.exception("Backend API promotion failed")
        return {
            "ok": False,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [str(exc)],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "",
            "incident_access_mode": "backend",
        }


def promote_alert_signals_via_backend_api(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Promote alert signal candidates via backend internal API (legacy)."""
    backend_url = os.environ.get("K9B_BACKEND_INTERNAL_URL")
    internal_api_token = os.environ.get("K9B_INTERNAL_API_TOKEN")

    if not backend_url or not internal_api_token:
        return {
            "ok": False,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [
                "Backend API configuration incomplete: missing backend_url or internal_api_token"
            ],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "",
            "incident_access_mode": "backend",
        }

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)
    candidate_dicts = incident_candidates_to_dict_list(candidates)

    try:
        response = client.promote_alert_signals(
            candidates=candidate_dicts,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )
        return _response_to_promotion_result(response)
    except Exception as exc:
        _logger.exception("Backend API alert signal promotion failed")
        return {
            "ok": False,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [str(exc)],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "",
            "incident_access_mode": "backend",
        }


def _scoped_typed_failure_dict(
    *,
    signal_ids: list[str],
    exc: BaseException,
) -> dict[str, Any]:
    """Construct a bounded error dict for an unexpected exception
    in the typed scoped path.

    The active scoped path uses the typed client and mapper; an
    unexpected exception here MUST fail closed with a bounded
    error dict so the dispatcher cannot accidentally fall back to
    a global store scan.
    """
    return {
        "ok": False,
        "scanned": len(signal_ids),
        "firing": len(signal_ids),
        "opened_incidents": 0,
        "updated_incidents": 0,
        "skipped_duplicates": 0,
        "errors": 1,
        "error_messages": [str(exc)],
        "opened_incident_ids": [],
        "updated_incident_ids": [],
        "canonical_incident_ids": [],
        "promotion_records": [],
        "unique_candidate_count": 0,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
    }


def _scoped_projection_to_dispatch_dict(
    projection: ScopedTransportPromotionProjection,
    *,
    signal_ids: list[str],
) -> dict[str, Any]:
    """Translate a typed scoped projection into the dispatcher dict.

    The active dispatcher reads a flat dict shape; this helper
    preserves every stable field while ensuring the closed
    projection algebra is the only authority for the values.
    """
    basis = {
        "scanned": len(signal_ids),
        "firing": len(signal_ids),
        "skipped_duplicates": 0,
        "promotion_scan_scope": "internal_api_alert_signals:scoped",
        "incident_access_mode": "backend",
        "promotion_records": [],
        "opened_incident_ids": [],
        "updated_incident_ids": [],
        "observation_refreshed_incident_ids": [],
        "unchanged_incident_ids": [],
        "canonical_incident_ids": [],
        "unique_candidate_count": len(signal_ids),
        "error_messages": [],
        "errors": 0,
    }
    if isinstance(projection, ScopedPromotionCompletedProjection):
        outcome = projection.promotion_outcome
        receipt = projection.aggregate_receipt
        opened = list(receipt.opened_incident_ids)
        updated = list(receipt.materially_changed_incident_ids)
        observation = list(receipt.observation_refreshed_incident_ids)
        unchanged = list(receipt.unchanged_incident_ids)
        canonical = list(outcome.diagnosis_incident_ids)
        promotion_records: list[dict[str, str | None]] = []
        for incident_id in opened:
            promotion_records.append(
                {
                    "source_candidate_id": "<scoped>",
                    "canonical_incident_id": str(incident_id),
                    "promotion_outcome": "opened",
                }
            )
        for incident_id in updated:
            promotion_records.append(
                {
                    "source_candidate_id": "<scoped>",
                    "canonical_incident_id": str(incident_id),
                    "promotion_outcome": "updated",
                }
            )
        for incident_id in observation:
            promotion_records.append(
                {
                    "source_candidate_id": "<scoped>",
                    "canonical_incident_id": str(incident_id),
                    "promotion_outcome": "observation_refreshed",
                }
            )
        for incident_id in unchanged:
            promotion_records.append(
                {
                    "source_candidate_id": "<scoped>",
                    "canonical_incident_id": str(incident_id),
                    "promotion_outcome": "unchanged",
                }
            )
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
            "promotion_records": promotion_records,
        }
    if isinstance(projection, ScopedPromotionRejectedProjection):
        outcome = projection.promotion_outcome
        error_messages = [outcome.reason.value]
        # AUTHENTICATION_REJECTED is a permanent rejection; the
        # dispatcher MUST NOT trigger a global store scan.
        return {
            **basis,
            "ok": False,
            "opened_incidents": 0,
            "updated_incidents": 0,
            "errors": 1,
            "error_messages": error_messages,
            "incident_access_mode": (
                "backend"
                if outcome.reason
                != PromotionRejectionCode.AUTHENTICATION_REJECTED
                else "backend"
            ),
        }
    if isinstance(projection, ScopedPromotionUncertainProjection):
        outcome = projection.promotion_outcome
        return {
            **basis,
            "ok": False,
            "opened_incidents": 0,
            "updated_incidents": 0,
            "errors": 0,
            "error_messages": [outcome.reason.value],
            "incident_access_mode": "reconciliation_required",
        }
    # Exhaustiveness: a new projection variant MUST fail typing.
    from typing import assert_never

    assert_never(projection)


def promote_alert_signals_via_scoped_backend_api(
    *,
    run_id: str,
    source_identity: str,
    signal_ids: list[str],
) -> dict[str, Any]:
    """Promote the explicit current-run alert-signal scope via backend API.

    Active dispatcher path. Constructs exactly one canonical
    :class:`PromoteAlertSignalsRequest`, creates one
    :class:`ScopedPromotionHttpRequestContext`, invokes
    :class:`ScopedSchedulerClient`, and routes the typed
    transport outcome through
    :func:`map_scoped_http_transport_to_promotion_outcome`. The
    returned dict carries the dispatcher's flat shape; the
    underlying authority is the closed projection algebra.

    The function MUST NOT call ``_coerce_promotion_response``, the
    legacy ``SchedulerClient.promote_alert_signals_scoped`` path,
    or any global store scan. Any failure in the typed path fails
    closed with a bounded error dict.
    """
    backend_url = os.environ.get("K9B_BACKEND_INTERNAL_URL")
    internal_api_token = os.environ.get("K9B_INTERNAL_API_TOKEN")

    if not backend_url or not internal_api_token:
        return {
            "ok": False,
            "scanned": len(signal_ids),
            "firing": len(signal_ids),
            "opened_incidents": 0,
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 1,
            "error_messages": [
                "Backend API configuration incomplete: missing backend_url or internal_api_token"
            ],
            "opened_incident_ids": [],
            "updated_incident_ids": [],
            "canonical_incident_ids": [],
            "promotion_records": [],
            "unique_candidate_count": 0,
            "promotion_scan_scope": "internal_api_alert_signals:scoped",
            "incident_access_mode": "backend",
        }

    try:
        request = PromoteAlertSignalsRequest(
            run_id=HealthRunId(run_id),
            source_identity=source_identity,
            signal_ids=tuple(
                AlertSignalId(value) for value in signal_ids
            ),
        )
        request_id = (
            f"promotion-request-{uuid.uuid4().hex}"
        )
        context = ScopedPromotionHttpRequestContext(
            request=request,
            request_id=request_id,
        )
        client = ScopedSchedulerClient(
            base_url=backend_url, token=internal_api_token
        )
        transport = client.promote_alert_signals_scoped(
            context=context,
        )
        projection = map_scoped_http_transport_to_promotion_outcome(
            transport, context=context
        )
        return _scoped_projection_to_dispatch_dict(
            projection, signal_ids=signal_ids
        )
    except Exception as exc:
        _logger.exception(
            "Backend API scoped alert signal promotion failed"
        )
        return _scoped_typed_failure_dict(
            signal_ids=signal_ids, exc=exc
        )


__all__ = [
    "MODE_BACKEND_API",
    "promote_alert_signals_via_backend_api",
    "promote_alert_signals_via_scoped_backend_api",
    "promote_via_backend_api",
]
