"""Internal API promotion handlers.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..collect.promotion_scoped_http_seam import (
    MAX_REQUEST_ID_LENGTH as _MAX_REQUEST_ID_LENGTH,
)
from ..incident_alert_promotion_contract import (
    PromotionScopeError,
    parse_promote_alert_signals_request,
)
from ..incident_alert_promotion_scoped import promote_scoped_alert_signals
from .server_incident_internal_models import (
    PromoteCandidatesRequest,
    PromotionResponse,
)
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


def _convert_candidates_to_objects(
    candidates_data: list[dict[str, Any]],
) -> list[Any]:
    from ..collect.incident_candidates import (
        CandidateClass,
        CandidateSignal,
        IncidentCandidate,
        ObjectKind,
        Severity,
    )

    incident_candidates = []
    for cand_data in candidates_data:
        sev_str = cand_data.get("severity", "warning")
        severity = Severity.ERROR if sev_str.lower() == "error" else Severity.WARNING

        kind_str = cand_data.get("object_kind", "Unknown")
        try:
            object_kind = ObjectKind(kind_str)
        except ValueError:
            object_kind = ObjectKind.UNKNOWN

        class_str = cand_data.get("candidate_class", "unknown")
        try:
            candidate_class = CandidateClass(class_str)
        except ValueError:
            candidate_class = CandidateClass.UNKNOWN

        signals = []
        for sig_data in cand_data.get("signals", []):
            signals.append(
                CandidateSignal(
                    source=sig_data.get("source", "detector"),
                    reason=sig_data.get("reason", ""),
                    message=sig_data.get("message", ""),
                    fingerprint=sig_data.get("fingerprint"),
                )
            )

        evidence_needed = tuple(cand_data.get("evidence_needed", []))

        incident_candidates.append(
            IncidentCandidate(
                candidate_id=cand_data.get("candidate_id", ""),
                namespace=cand_data.get("namespace", ""),
                object_kind=object_kind,
                object_name=cand_data.get("object_name", ""),
                candidate_class=candidate_class,
                severity=severity,
                signals=tuple(signals),
                evidence_needed=evidence_needed,
                raw_object_kind=cand_data.get("raw_object_kind"),
            )
        )

    return incident_candidates


def _parse_observed_at(observed_at_str: str) -> datetime | None:
    try:
        observed_at = datetime.fromisoformat(observed_at_str)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        return observed_at
    except ValueError:
        return None


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
        from ..collect.incident_store_provider import get_incident_store

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


def handle_promote_candidates(handler: Any) -> None:
    """Handle POST /api/internal/incidents/promote-candidates (manual/admin)."""
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    try:
        content_length = int(handler.headers.get("Content-Length", 0))
        body = handler.rfile.read(content_length).decode("utf-8")
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid JSON: {e}"},
            400,
        )
        return

    try:
        request = PromoteCandidatesRequest.from_dict(data)
    except Exception as e:
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid request: {e}"},
            400,
        )
        return

    observed_at = _parse_observed_at(request.observed_at)
    if observed_at is None:
        handler._send_json(
            {"error": "Bad Request", "message": "Invalid observed_at format"},
            400,
        )
        return

    try:
        incident_candidates = _convert_candidates_to_objects(request.candidates)
    except Exception as e:
        _logger.exception("Failed to convert candidates")
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid candidate data: {e}"},
            400,
        )
        return

    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()

        outcomes = store.promote_candidates_with_records(
            candidates=incident_candidates,
            observed_at=observed_at,
            snapshot_bundle_id=request.snapshot_bundle_id,
        )

        opened_count = 0
        updated_count = 0
        skipped_duplicate_count = 0
        opened_incident_ids: list[str] = []
        updated_incident_ids: list[str] = []
        promotion_records: list[dict[str, str | None]] = []
        for outcome in outcomes:
            record = outcome.record
            promotion_records.append(record.to_dict())
            if record.canonical_incident_id is None:
                continue
            from ..collect.incident_identity_hardening import (
                PROMOTION_OUTCOME_OPENED,
                PROMOTION_OUTCOME_SKIPPED_DUPLICATE,
                PROMOTION_OUTCOME_UPDATED,
            )
            if record.promotion_outcome == PROMOTION_OUTCOME_OPENED:
                opened_count += 1
                opened_incident_ids.append(record.canonical_incident_id)
            elif record.promotion_outcome == PROMOTION_OUTCOME_UPDATED:
                updated_count += 1
                updated_incident_ids.append(record.canonical_incident_id)
            elif record.promotion_outcome == PROMOTION_OUTCOME_SKIPPED_DUPLICATE:
                skipped_duplicate_count += 1

        unique_candidate_count = len({c.candidate_id for c in incident_candidates})

        response = PromotionResponse(
            ok=True,
            scanned=len(incident_candidates),
            opened_incidents=opened_count,
            updated_incidents=updated_count,
            skipped_duplicates=skipped_duplicate_count,
            errors=0,
            opened_incident_ids=opened_incident_ids,
            updated_incident_ids=updated_incident_ids,
            promotion_records=promotion_records,
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=(
                f"internal_api_candidates:bundle={request.snapshot_bundle_id or 'none'}"
            ),
            incident_access_mode="backend",
        )

        _logger.info(
            "Candidates promoted via internal API",
            extra={
                "event": "incident-promotion-ingested",
                "source": "scheduler",
                "scanned": response.scanned,
                "opened_incidents": response.opened_incidents,
                "updated_incidents": response.updated_incidents,
                "opened_incident_ids": list(response.opened_incident_ids),
                "updated_incident_ids": list(response.updated_incident_ids),
                "unique_candidate_count": response.unique_candidate_count,
                "promotion_scan_scope": response.promotion_scan_scope,
                "incident_access_mode": response.incident_access_mode,
                "store_kind": getattr(store, "store_kind", "unknown"),
            },
        )

        handler._send_json(response.to_dict(), 200)

    except Exception as e:
        _logger.exception("Failed to promote candidates")
        response = PromotionResponse(
            ok=False,
            errors=1,
            error_messages=[str(e)],
        )
        handler._send_json(response.to_dict(), 500)


__all__ = [
    "handle_promote_alert_signals",
    "handle_promote_candidates",
]
