"""In-memory pagination fallback for incident store.

This module provides pagination capability for the in-memory store
when SQLite is not available. Extracted from incident_store.py to
keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .incident_diagnosis_dispatch_contracts import DiagnosisPageIncident
    from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
    from .incident_diagnosis_keyset_cursor import (
        DiagnosisPageLimit,
        IncidentDiagnosisCursor,
    )
    from .incident_lifecycle import Incident


def in_memory_pagination(
    incidents: list[Incident],
    active_only: bool,
    limit: DiagnosisPageLimit,
    after_cursor: IncidentDiagnosisCursor | None,
) -> IncidentDiagnosisPage:
    """Build a page from in-memory incident list.

    This provides a simple fallback for pagination when SQLite
    is not available. It uses list-based pagination which is
    suitable for small to medium incident counts.

    Args:
        incidents: List of incidents to paginate
        active_only: If True, only return active incidents
        limit: Maximum number of incidents per page
        after_cursor: Optional cursor to resume after

    Returns:
        IncidentDiagnosisPage with paginated results
    """
    from .incident_diagnosis_dispatch_contracts import DiagnosisPageIncident
    from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
    from .incident_diagnosis_keyset_cursor import cursor_after_page_incident
    from .incident_lifecycle import IncidentStatus

    # Filter by active status if requested
    if active_only:
        active_statuses = (
            IncidentStatus.OPEN,
            IncidentStatus.COLLECTING_EVIDENCE,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.READY_FOR_REVIEW,
        )
        incidents = [i for i in incidents if i.status in active_statuses]

    # Filter by cursor position
    if after_cursor is not None:
        ts = after_cursor.first_observed_at_text
        inc_id = after_cursor.incident_id
        # Find position after cursor
        pos = 0
        for i, inc in enumerate(incidents):
            inc_ts = inc.first_observed_at.isoformat() if inc.first_observed_at else ""
            if inc_ts > ts or (inc_ts == ts and inc.incident_id > inc_id):
                pos = i
                break
            pos = i + 1
        incidents = incidents[pos:]

    # Take limit + 1 to determine has_more
    limit_value = limit.value
    page_incidents = incidents[: limit_value + 1]
    has_more = len(page_incidents) > limit_value
    page_incidents = page_incidents[:limit_value]

    # Build page incidents
    page_inc_list: list[DiagnosisPageIncident] = []
    for inc in page_incidents:
        first_ts: datetime = inc.first_observed_at
        page_inc_list.append(DiagnosisPageIncident(
            incident_id=inc.incident_id,
            status=inc.status.value if hasattr(inc.status, 'value') else inc.status,
            first_observed_at=first_ts,
            first_observed_at_key=first_ts.isoformat() if first_ts else "",
        ))

    # Build next cursor if has_more
    next_cursor = None
    if has_more and page_inc_list:
        next_cursor = cursor_after_page_incident(page_inc_list[-1])

    return IncidentDiagnosisPage(
        incidents=tuple(page_inc_list),
        next_cursor=next_cursor,
        has_more=has_more,
    )


__all__ = [
    "in_memory_pagination",
]
