"""Internal API request handlers.

Provides handlers for the scheduler-to-backend promotion API endpoints.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .server_incident_internal_auth import _validate_internal_token
from .server_incident_internal_models import (
    PromoteAlertSignalsRequest,
    PromoteCandidatesRequest,
    PromotionResponse,
)

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromotionStats:
    """Statistics from a promotion operation.

    Tracks the counts of opened, updated, and skipped incidents
    during promotion for accurate reporting.
    """
    scanned: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)

    def to_response(self, ok: bool = True) -> PromotionResponse:
        """Convert stats to API response.

        Args:
            ok: Whether the operation was successful

        Returns:
            PromotionResponse with accurate counts
        """
        return PromotionResponse(
            ok=ok,
            scanned=self.scanned,
            opened_incidents=self.opened_incidents,
            updated_incidents=self.updated_incidents,
            skipped_duplicates=self.skipped_duplicates,
            errors=self.errors,
            error_messages=self.error_messages if self.errors > 0 else [],
        )


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

        # Track which incidents existed before promotion
        existing_ids = set(store._incidents.keys())

        promoted = store.promote_candidates(
            candidates=incident_candidates,
            observed_at=observed_at,
            snapshot_bundle_id=request.snapshot_bundle_id,
        )

        # Count opened vs updated based on pre-existing incidents
        opened_count = 0
        updated_count = 0
        for incident in promoted:
            if incident.incident_id in existing_ids:
                updated_count += 1
            else:
                opened_count += 1

        response = PromotionResponse(
            ok=True,
            scanned=len(incident_candidates),
            firing=len(incident_candidates),
            opened_incidents=opened_count,
            updated_incidents=updated_count,
            skipped_duplicates=0,
            errors=0,
        )

        _logger.info(
            "Alert signals promoted via internal API",
            extra={
                "event": "incident-promotion-ingested",
                "source": "scheduler",
                "scanned": response.scanned,
                "opened_incidents": response.opened_incidents,
                "updated_incidents": response.updated_incidents,
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

        # Track which incidents existed before promotion
        existing_ids = set(store._incidents.keys())

        promoted = store.promote_candidates(
            candidates=incident_candidates,
            observed_at=observed_at,
            snapshot_bundle_id=request.snapshot_bundle_id,
        )

        # Count opened vs updated based on pre-existing incidents
        opened_count = 0
        updated_count = 0
        for incident in promoted:
            if incident.incident_id in existing_ids:
                updated_count += 1
            else:
                opened_count += 1

        response = PromotionResponse(
            ok=True,
            scanned=len(incident_candidates),
            opened_incidents=opened_count,
            updated_incidents=updated_count,
            skipped_duplicates=0,
            errors=0,
        )

        _logger.info(
            "Candidates promoted via internal API",
            extra={
                "event": "incident-promotion-ingested",
                "source": "scheduler",
                "scanned": response.scanned,
                "opened_incidents": response.opened_incidents,
                "updated_incidents": response.updated_incidents,
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
