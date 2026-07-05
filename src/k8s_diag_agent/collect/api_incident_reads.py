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
from collections.abc import Mapping
from pathlib import Path

from ..observability import (
    trace_incident_store_get,
    trace_incident_store_list,
)
from ..ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_summary_payload,
)
from ..ui.api_payloads import IncidentDetailPayload, IncidentSummaryPayload
from .incident_lifecycle import Incident, IncidentStatus
from .incident_next_check_artifacts import load_next_check_plan_payloads_for_incident
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

    def _list_incidents() -> tuple:
        return store.list_incidents(status=status_filter)

    incidents = trace_incident_store_list(
        _list_incidents,
        attributes={"k9b.item.kind": "incident"},
    )

    def _project_incidents() -> list:
        return [build_incident_summary_payload(inc) for inc in incidents]

    projected = trace_incident_store_list(
        _project_incidents,
        attributes={"k9b.projection_kind": "incident_summary"},
    )

    return {
        "incidents": projected,
        "total": len(incidents),
    }


def handle_get_incident(
    incident_id: str,
    external_analysis_dir: Path | None = None,
) -> IncidentDetailPayload | None:
    """Get a specific incident by ID.

    Args:
        incident_id: The incident ID to look up
        external_analysis_dir: Optional path to external-analysis directory
            for loading:
            - Next-check plan artifacts to populate suggested_checks
            - Automatic diagnosis review packet summaries

    Returns:
        Incident detail dict if found, None if not found

    Note:
        When external_analysis_dir is None, suggested_checks will be empty
        and automatic_diagnosis_review will indicate no packet available.
        When provided, both fields are populated from linked artifacts.
        Missing or malformed artifacts do not cause errors - they are skipped.
    """
    store = get_incident_store()

    def _get_incident() -> Incident | None:
        return store.get_incident(incident_id)

    incident = trace_incident_store_get(
        _get_incident,
        attributes={"k9b.item.kind": "incident"},
    )

    if incident is None:
        return None

    # Load next-check plan payloads if external_analysis_dir is available
    plan_payloads: tuple[Mapping[str, object], ...] = ()
    if external_analysis_dir is not None:
        plan_payloads = load_next_check_plan_payloads_for_incident(
            incident,
            external_analysis_dir,
        )

    def _build_payload() -> IncidentDetailPayload:
        return build_incident_detail_payload(
            incident,
            external_analysis_dir=external_analysis_dir,
            next_check_plan_payloads=plan_payloads,
        )

    return trace_incident_store_get(  # type: ignore[no-any-return]
        _build_payload,
        attributes={"k9b.projection_kind": "incident_detail"},
    )


__all__ = [
    "handle_list_incidents",
    "handle_get_incident",
]