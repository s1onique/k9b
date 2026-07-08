"""Backend API incident promotion implementation.

This module provides the backend API promotion path for incident candidates,
used when the scheduler runs separately from the incident store (SQLite mode).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..ui.server_incident_internal_client import SchedulerClient
from .incident_candidate_serialization import incident_candidates_to_dict_list
from .incident_candidates import IncidentCandidate

_logger = logging.getLogger(__name__)

# Backend API mode
MODE_BACKEND_API = "backend-api"


def promote_via_backend_api(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Promote generic candidates via backend internal API.

    Args:
        candidates: List of candidates to promote
        observed_at: When candidates were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        Dict with promotion counts from backend: ok, scanned, firing, opened_incidents,
        updated_incidents, skipped_duplicates, errors, error_messages
    """
    import os

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
        }

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    # Serialize candidates
    candidate_dicts = incident_candidates_to_dict_list(candidates)

    try:
        # Call backend API - generic candidates endpoint
        response = client.promote_candidates(
            candidates=candidate_dicts,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )

        return {
            "ok": response.ok,
            "scanned": response.scanned,
            "firing": response.firing,
            "opened_incidents": response.opened_incidents,
            "updated_incidents": response.updated_incidents,
            "skipped_duplicates": response.skipped_duplicates,
            "errors": response.errors,
            "error_messages": list(response.error_messages),
        }
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
        }


def promote_alert_signals_via_backend_api(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Promote alert signal candidates via backend internal API.

    This function posts to the /promote-alert-signals endpoint which is
    optimized for alert signal processing.

    Args:
        candidates: List of alert signal candidates to promote
        observed_at: When signals were observed
        snapshot_bundle_id: Optional snapshot bundle ID

    Returns:
        Dict with promotion counts from backend: ok, scanned, firing, opened_incidents,
        updated_incidents, skipped_duplicates, errors, error_messages
    """
    import os

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
        }

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    # Serialize candidates
    candidate_dicts = incident_candidates_to_dict_list(candidates)

    try:
        # Call backend API - alert signals endpoint
        response = client.promote_alert_signals(
            candidates=candidate_dicts,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )

        return {
            "ok": response.ok,
            "scanned": response.scanned,
            "firing": response.firing,
            "opened_incidents": response.opened_incidents,
            "updated_incidents": response.updated_incidents,
            "skipped_duplicates": response.skipped_duplicates,
            "errors": response.errors,
            "error_messages": list(response.error_messages),
        }
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
        }
