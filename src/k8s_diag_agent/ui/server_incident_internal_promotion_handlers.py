"""Implementation of internal API promotion handlers.

Provides POST handlers for the scheduler-to-backend promotion API endpoints.

The ``/api/internal/incidents/promote-alert-signals`` endpoint consumes the
typed current-run scope contract introduced by
``ACT-K9B-INCIDENT-CURRENT-RUN-PROMOTION-DIAGNOSIS-WORKSET01``: an explicit
``runId`` / ``sourceIdentity`` / ``signalIds`` workset. The backend never
falls back to a global firing-signal scan; a missing, malformed, or
cross-source artifact fails the request closed.

The legacy promote-candidates handler remains available for the manual
``incident_store`` admin path and is unaffected.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..collect.incident_store_provider import get_incident_store
from ..collect.promotion_scoped_http_seam import (
    MAX_REQUEST_ID_LENGTH as _MAX_REQUEST_ID_LENGTH,
)
from ..incident_alert_promotion_contract import (
    PromotionScopeError,
    parse_promote_alert_signals_request,
)
from ..incident_alert_promotion_scoped import promote_scoped_alert_signals
from .server_incident_internal_scoped_client import (
    REQUEST_ID_HEADER as _REQUEST_ID_HEADER,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

MAX_PROMOTION_PAYLOAD_BYTES = 64 * 1024


def _extract_request_id(handler: Any) -> str:
    """Extract and validate the ``X-K9B-Promotion-Request-ID`` header.

    The header is bounded by ``MAX_REQUEST_ID_LENGTH``; a missing or
    over-long header is treated as an empty correlation identity so
    downstream events still emit a stable, bounded marker. The
    handler MUST NEVER raise on a missing header -- the request is
    already authenticated at this point and we keep the contract
    fail-soft for header-shape defects.
    """
    raw = handler.headers.get(_REQUEST_ID_HEADER, "") if handler else ""
    if not raw:
        return ""
    if len(raw) > _MAX_REQUEST_ID_LENGTH:
        return ""
    return str(raw)


def _runs_dir_for_request(handler: Any) -> Path:
    """Return the runs directory used for the current request.

    The handler owns the runs root for artifact scanning. When the
    server has not bound a runs directory we fail closed rather than
    silently scanning the default test tree.
    """
    runs_dir = getattr(handler, "runs_dir", None)
    if runs_dir is None:
        raise PromotionScopeError(
            "server has no runs directory configured for current-run promotion"
        )
    return Path(runs_dir)


def _validate_internal_token(handler: Any) -> bool:
    from .server_incident_internal_auth import _validate_internal_token as auth_validate

    return auth_validate(handler)






def _read_request_body(handler: Any) -> dict[str, Any]:
    try:
        content_length = int(handler.headers.get("Content-Length", 0))
    except ValueError as exc:
        raise PromotionScopeError("invalid Content-Length header") from exc
    if content_length <= 0:
        raise PromotionScopeError("missing request body")
    if content_length > MAX_PROMOTION_PAYLOAD_BYTES:
        raise PromotionScopeError(
            f"payload exceeds maximum of {MAX_PROMOTION_PAYLOAD_BYTES} bytes"
        )
    raw = handler.rfile.read(content_length)
    if not raw:
        raise PromotionScopeError("empty request body")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionScopeError(f"invalid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise PromotionScopeError("request body must be a JSON object")
    return cast("dict[str, Any]", decoded)


def _log_promotion_result(
    *,
    event_name: str,
    run_id: str,
    source_identity: str,
    requested_signal_count: int,
    scanned_signal_count: int,
    opened_count: int,
    materially_changed_count: int,
    observation_refreshed_count: int,
    unchanged_count: int,
    skipped_count: int,
    failure_count: int,
    promotion_scope: str,
    promotion_actionable_count: int,
) -> None:
    """Log a promotion-result audit event with *authoritative* signal cardinalities.

    ``requested_signal_count`` is the number of signal IDs the caller
    asked us to process (``len(request.signal_ids)``). ``scanned_signal_count``
    is the number of signals the dispatcher actually scanned
    (``result.scanned_signal_count``). Both are NOT derived from the
    per-category incident counts because several signals can collapse
    into one incident, and failures / skips would otherwise vanish
    from the audit trail.
    """
    _logger.info(
        event_name,
        extra={
            "event": event_name,
            "run_id": run_id,
            "source_identity": source_identity,
            "promotion_scope": "explicit_current_run_signal_ids",
            "requested_signal_count": requested_signal_count,
            "scanned_signal_count": scanned_signal_count,
            "opened_incident_count": opened_count,
            "materially_changed_incident_count": materially_changed_count,
            "observation_refreshed_incident_count": observation_refreshed_count,
            "unchanged_incident_count": unchanged_count,
            "actionable_incident_count": promotion_actionable_count,
            "skipped_signal_count": skipped_count,
            "failure_count": failure_count,
            "promotion_scope_label": promotion_scope,
        },
    )


def handle_promote_alert_signals(handler: Any) -> None:
    """Handle POST /api/internal/incidents/promote-alert-signals.

    Strict, explicit-scope contract:

    * ``runId``, ``sourceIdentity``, and ``signalIds`` are required.
    * The backend only processes the supplied signal IDs; no global scan
      and no fallback to a previous run's batch.
    * A missing/malformed/cross-source artifact fails the request closed
      with a ``400 Bad Request`` error.
    * The ``X-K9B-Promotion-Request-ID`` correlation header is consumed
      so backend received/response events carry the same identity as
      the scheduler observation.
    """
    request_id = _extract_request_id(handler)

    if not _validate_internal_token(handler):
        _logger.info(
            "alert-signals-promoted-rejected",
            extra={
                "event": "alert-signals-promoted-rejected",
                "request_id": request_id,
                "status_code": 401,
                "reason": "unauthorized",
            },
        )
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    try:
        data = _read_request_body(handler)
        request = parse_promote_alert_signals_request(data)
        runs_dir = _runs_dir_for_request(handler)
    except PromotionScopeError as exc:
        _logger.info(
            "alert-signals-promoted-rejected",
            extra={
                "event": "alert-signals-promoted-rejected",
                "request_id": request_id,
                "status_code": 400,
                "reason": "bad_request",
            },
        )
        handler._send_json(
            {"error": "Bad Request", "message": str(exc)},
            400,
        )
        return

    # Emit the bounded received event with NO request body / token.
    _logger.info(
        "alert-signals-promotion-received",
        extra={
            "event": "alert-signals-promotion-received",
            "request_id": request_id,
            "run_id": str(request.run_id),
            "source_identity": request.source_identity,
            "signal_count": len(request.signal_ids),
        },
    )

    try:
        store = get_incident_store()
        result = promote_scoped_alert_signals(
            request=request,
            incident_store=store,
            runs_dir=runs_dir,
        )
    except PromotionScopeError as exc:
        _logger.info(
            "alert-signals-promoted-rejected",
            extra={
                "event": "alert-signals-promoted-rejected",
                "request_id": request_id,
                "status_code": 400,
                "reason": "scope_error",
            },
        )
        handler._send_json(
            {"error": "Bad Request", "message": str(exc)},
            400,
        )
        return
    except Exception as exc:  # pragma: no cover - defensive
        _logger.exception("Failed to promote scoped alert signals")
        _logger.info(
            "alert-signals-promoted-rejected",
            extra={
                "event": "alert-signals-promoted-rejected",
                "request_id": request_id,
                "status_code": 500,
                "reason": "internal_error",
            },
        )
        handler._send_json(
            {"error": "Internal Server Error", "message": str(exc)},
            500,
        )
        return

    wire = result.to_wire_dict()
    wire_typed = cast("dict[str, Any]", wire)
    response_byte_count = len(json.dumps(wire).encode("utf-8"))
    # Authoritative signal counts come from the request and the
    # dispatcher's ``scanned_signal_count`` view — never from the per-category
    # incident sizes, which would otherwise vanish every failure and skip.
    _log_promotion_result(
        event_name="alert-signals-promoted-via-backend",
        run_id=str(wire_typed["runId"]),
        source_identity=str(wire_typed["sourceIdentity"]),
        requested_signal_count=len(request.signal_ids),
        scanned_signal_count=result.scanned_signal_count,
        opened_count=len(wire_typed["openedIncidentIds"]),
        materially_changed_count=len(wire_typed["materiallyChangedIncidentIds"]),
        observation_refreshed_count=len(wire_typed["observationRefreshedIncidentIds"]),
        unchanged_count=len(wire_typed["unchangedIncidentIds"]),
        skipped_count=len(wire_typed["skippedSignalIds"]),
        failure_count=len(wire_typed["failures"]),
        promotion_scope="explicit_current_run_signal_ids",
        promotion_actionable_count=len(wire_typed["actionableIncidentIds"]),
    )
    # Bounded response event: status + byte count, NO body content.
    _logger.info(
        "alert-signals-promotion-response",
        extra={
            "event": "alert-signals-promotion-response",
            "request_id": request_id,
            "run_id": str(wire_typed["runId"]),
            "source_identity": str(wire_typed["sourceIdentity"]),
            "signal_count": len(request.signal_ids),
            "status_code": 200,
            "response_byte_count": response_byte_count,
        },
    )
    handler._send_json(wire, 200)




__all__ = ["handle_promote_alert_signals"]
