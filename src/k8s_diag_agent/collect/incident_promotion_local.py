"""Local incident promotion implementation.

This module provides the local promotion path for incident candidates,
used when the scheduler runs in the same process as the incident store.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from .incident_candidates import IncidentCandidate

if TYPE_CHECKING:
    from .incident_store import IncidentStore

_logger = logging.getLogger(__name__)


def promote_local(
    candidates: list[IncidentCandidate],
    observed_at: datetime,
    snapshot_bundle_id: str | None = None,
    store: IncidentStore | None = None,
) -> dict[str, int | list[str]]:
    """Promote candidates via local incident store.

    Args:
        candidates: List of candidates to promote
        observed_at: When candidates were observed
        snapshot_bundle_id: Optional snapshot bundle ID
        store: Optional pre-obtained store instance

    Returns:
        Dict with promotion counts: ok, scanned, firing, opened_incidents,
        updated_incidents, skipped_duplicates, errors, error_messages
    """
    try:
        if store is None:
            from .incident_store_provider import get_incident_store

            store = get_incident_store()

        # Track existing incidents
        existing_ids = set(store._incidents.keys()) if hasattr(store, "_incidents") else set()

        # Promote candidates
        promoted = store.promote_candidates(
            candidates=candidates,
            observed_at=observed_at,
            snapshot_bundle_id=snapshot_bundle_id,
        )

        # Count opened vs updated
        opened_count = 0
        updated_count = 0
        for incident in promoted:
            if incident.incident_id in existing_ids:
                updated_count += 1
            else:
                opened_count += 1

        return {
            "ok": True,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": opened_count,
            "updated_incidents": updated_count,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": [],
        }
    except Exception as exc:
        _logger.exception("Local promotion failed")
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
