"""Internal API promotion handlers.

Provides POST handlers for the scheduler-to-backend promotion API endpoints.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .server_incident_internal_models import (
    PromoteAlertSignalsRequest,
    PromoteCandidatesRequest,
    PromotionResponse,
)

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


def _convert_candidates_to_objects(
    candidates_data: list[dict[str, Any]],
) -> list[Any]:
    """Convert raw candidate dicts to IncidentCandidate objects.

    Args:
        candidates_data: List of candidate dictionaries

    Returns:
        List of IncidentCandidate objects
    """
    from ..collect.incident_candidates import (
        CandidateClass,
        CandidateSignal,
        IncidentCandidate,
        ObjectKind,
        Severity,
    )

    incident_candidates = []
    for cand_data in candidates_data:
        # Map severity
        sev_str = cand_data.get("severity", "warning")
        severity = Severity.ERROR if sev_str.lower() == "error" else Severity.WARNING

        # Map object kind
        kind_str = cand_data.get("object_kind", "Unknown")
        try:
            object_kind = ObjectKind(kind_str)
        except ValueError:
            object_kind = ObjectKind.UNKNOWN

        # Map candidate class
        class_str = cand_data.get("candidate_class", "unknown")
        try:
            candidate_class = CandidateClass(class_str)
        except ValueError:
            candidate_class = CandidateClass.UNKNOWN

        # Build signals
        signals = []
        for sig_data in cand_data.get("signals", []):
            signals.append(CandidateSignal(
                source=sig_data.get("source", "detector"),
                reason=sig_data.get("reason", ""),
                message=sig_data.get("message", ""),
            ))

        # Build evidence needed
        evidence_needed = tuple(cand_data.get("evidence_needed", []))

        incident_candidates.append(IncidentCandidate(
            candidate_id=cand_data.get("candidate_id", ""),
            namespace=cand_data.get("namespace", ""),
            object_kind=object_kind,
            object_name=cand_data.get("object_name", ""),
            candidate_class=candidate_class,
            severity=severity,
            signals=tuple(signals),
            evidence_needed=evidence_needed,
            raw_object_kind=cand_data.get("raw_object_kind"),
        ))

    return incident_candidates


def _parse_observed_at(observed_at_str: str) -> datetime | None:
    """Parse observed_at string to datetime.

    Args:
        observed_at_str: ISO format datetime string

    Returns:
        Parsed datetime with UTC timezone, or None if invalid
    """
    try:
        observed_at = datetime.fromisoformat(observed_at_str)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        return observed_at
    except ValueError:
        return None


def _validate_internal_token(handler: Any) -> bool:
    """Validate the internal API token from request headers.

    Args:
        handler: The request handler

    Returns:
        True if token is valid, False otherwise
    """
    from .server_incident_internal_auth import _validate_internal_token as auth_validate
    return auth_validate(handler)
def handle_promote_alert_signals(handler: HealthUIRequestHandler) -> None:
    """Handle POST /api/internal/incidents/promote-alert-signals.

    This endpoint receives alert signal promotions from the scheduler
    and appends them to the backend SQLite store.

    Request body:
        {
            "candidates": [...],
            "observed_at": "2024-01-01T00:00:00Z",
            "snapshot_bundle_id": "bundle-123" (optional)
        }

    Response:
        {
            "ok": true,
            "scanned": N,
            "firing": N,
            "opened_incidents": N,
            "updated_incidents": N,
            "skipped_duplicates": N,
            "errors": N,
            "error_messages": [...]
        }
    """
    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Parse request body
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
        request = PromoteAlertSignalsRequest.from_dict(data)
    except Exception as e:
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid request: {e}"},
            400,
        )
        return

    # Parse observed_at
    observed_at = _parse_observed_at(request.observed_at)
    if observed_at is None:
        handler._send_json(
            {"error": "Bad Request", "message": "Invalid observed_at format"},
            400,
        )
        return

    # Convert candidates to IncidentCandidate objects
    try:
        incident_candidates = _convert_candidates_to_objects(request.candidates)
    except Exception as e:
        _logger.exception("Failed to convert candidates")
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid candidate data: {e}"},
            400,
        )
        return

    # Promote candidates
    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()

        # Use the typed store-owned promotion boundary. This avoids
        # ``zip(candidates, promoted, strict=False)`` reconstruction and
        # returns ``PromotionRecord`` values directly from the same
        # transaction that performs the promotion. Each outcome carries
        # both the ``PromotionRecord`` (with the authoritative
        # canonical ``incident_id``) and the resulting ``Incident``
        # snapshot, so the per-candidate mapping is preserved.
        outcomes = store.promote_candidates_with_records(
            candidates=incident_candidates,
            observed_at=observed_at,
            snapshot_bundle_id=request.snapshot_bundle_id,
        )

        # Aggregate opened/updated counts directly from the typed
        # records. We no longer reconstruct the mapping from separate
        # candidate and incident collections.
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

        unique_candidate_count = len(
            {c.candidate_id for c in incident_candidates}
        )

        response = PromotionResponse(
            ok=True,
            scanned=len(incident_candidates),
            firing=len(incident_candidates),
            opened_incidents=opened_count,
            updated_incidents=updated_count,
            skipped_duplicates=skipped_duplicate_count,
            errors=0,
            opened_incident_ids=opened_incident_ids,
            updated_incident_ids=updated_incident_ids,
            promotion_records=promotion_records,
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=(
                f"internal_api_alert_signals:bundle={request.snapshot_bundle_id or 'none'}"
            ),
            incident_access_mode="backend",
        )

        _logger.info(
            "Alert signals promoted via internal API",
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


def handle_promote_candidates(handler: HealthUIRequestHandler) -> None:
    """Handle POST /api/internal/incidents/promote-candidates.

    This endpoint receives incident candidate promotions from the scheduler
    and appends them to the backend SQLite store.

    Request body:
        {
            "candidates": [...],
            "observed_at": "2024-01-01T00:00:00Z",
            "snapshot_bundle_id": "bundle-123" (optional)
        }

    Response:
        {
            "ok": true,
            "scanned": N,
            "opened_incidents": N,
            "updated_incidents": N,
            "skipped_duplicates": N,
            "errors": N,
            "error_messages": [...]
        }
    """
    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Parse request body
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

    # Parse observed_at
    observed_at = _parse_observed_at(request.observed_at)
    if observed_at is None:
        handler._send_json(
            {"error": "Bad Request", "message": "Invalid observed_at format"},
            400,
        )
        return

    # Convert candidates to IncidentCandidate objects
    try:
        incident_candidates = _convert_candidates_to_objects(request.candidates)
    except Exception as e:
        _logger.exception("Failed to convert candidates")
        handler._send_json(
            {"error": "Bad Request", "message": f"Invalid candidate data: {e}"},
            400,
        )
        return

    # Promote candidates
    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()

        # Use the typed store-owned promotion boundary. This avoids
        # ``zip(candidates, promoted, strict=False)`` reconstruction and
        # returns ``PromotionRecord`` values directly from the same
        # transaction that performs the promotion. Each outcome carries
        # both the ``PromotionRecord`` (with the authoritative
        # canonical ``incident_id``) and the resulting ``Incident``
        # snapshot, so the per-candidate mapping is preserved.
        outcomes = store.promote_candidates_with_records(
            candidates=incident_candidates,
            observed_at=observed_at,
            snapshot_bundle_id=request.snapshot_bundle_id,
        )

        # Aggregate opened/updated counts directly from the typed
        # records. We no longer reconstruct the mapping from separate
        # candidate and incident collections.
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

        unique_candidate_count = len(
            {c.candidate_id for c in incident_candidates}
        )

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
