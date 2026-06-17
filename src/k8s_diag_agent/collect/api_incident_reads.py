"""Read-only API handlers for incident store.

This module provides read-only access to the in-memory IncidentStore.
It exposes:
- GET /api/incidents - list all incidents with optional status filter
- GET /api/incidents/{incident_id} - get a specific incident

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only)

Uses api_incident_reads serializers for typed payloads.
"""

from __future__ import annotations

import logging

from ..ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_summary_payload,
)
from ..ui.api_payloads import IncidentDetailPayload, IncidentSummaryPayload
from .incident_lifecycle import IncidentStatus
from .incident_store_provider import get_incident_store

_logger = logging.getLogger(__name__)


def handle_list_incidents(
    status: str | None = None,
) -> dict[str, list[IncidentSummaryPayload] | int]:
    """List incidents from the in-memory store.

    Args:
        status: Optional status filter (e.g., "open", "collecting_evidence")

    Returns:
        Dict with "incidents" list and "total" count
    """
    store = get_incident_store()

    # Parse status filter if provided
    status_filter: IncidentStatus | None = None
    if status is not None:
        try:
            status_filter = IncidentStatus(status)
        except ValueError:
            # Invalid status value - return empty list
            return {"incidents": [], "total": 0}

    incidents = store.list_incidents(status=status_filter)

    return {
        "incidents": [build_incident_summary_payload(inc) for inc in incidents],
        "total": len(incidents),
    }


def handle_get_incident(incident_id: str) -> IncidentDetailPayload | None:
    """Get a specific incident by ID.

    Args:
        incident_id: The incident ID to look up

    Returns:
        Incident detail dict if found, None if not found
    """
    store = get_incident_store()
    incident = store.get_incident(incident_id)

    if incident is None:
        return None

    return build_incident_detail_payload(incident)


__all__ = [
    "handle_list_incidents",
    "handle_get_incident",
]
