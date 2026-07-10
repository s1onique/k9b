"""Page-oriented incident listing for automatic diagnosis loop.

This module provides:
- IncidentDiagnosisPage: Return type for paginated incident listing
- Page-oriented store operation: list_incidents_for_diagnosis_page
- SQLite backend implementation for keyset pagination

The page operation uses keyset pagination with (first_observed_at, incident_id)
to ensure deterministic ordering and progress even when incidents are updated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from .incident_diagnosis_active_status import (
    ACTIVE_STATUS_PREDICATE,
)
from .incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from .incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
    IncidentDiagnosisCursor,
)
from .incident_diagnosis_pagination_results import (
    IncidentPageListingFailure,
    IncidentPageListingFailureKind,
    PageListed,
    PageListingFailed,
)

if TYPE_CHECKING:
    pass


_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncidentDiagnosisPage:
    """Paginated result for incident diagnosis listing.

    Attributes:
        incidents: Tuple of page incidents with mandatory first_observed_at for cursor.
            May be empty for terminal pages (empty suffix).
        next_cursor: Cursor for the next page, or None if this is the last page
        has_more: True if there are more pages after this one

    Invariants (validated in __post_init__):
    - has_more=True requires next_cursor is not None
    - has_more=False requires next_cursor is None
    - Empty page is only valid when has_more=False (terminal empty suffix)
    - No duplicate incident IDs

    Note:
        Empty pages are allowed as terminal pages (empty suffix reached after
        processing all eligible incidents). This happens when:
        - All incidents have been processed and the cursor reaches the end
        - The next page after the last incident is empty
    """

    incidents: tuple[DiagnosisPageIncident, ...]
    next_cursor: IncidentDiagnosisCursor | None
    has_more: bool

    def __post_init__(self) -> None:
        # Invariant: has_more=True requires next_cursor
        if self.has_more and self.next_cursor is None:
            raise ValueError(
                "has_more=True requires next_cursor to be present"
            )
        # Invariant: has_more=False requires next_cursor=None
        if not self.has_more and self.next_cursor is not None:
            raise ValueError(
                "has_more=False requires next_cursor to be None"
            )
        # Invariant: Empty page with has_more=True is invalid
        # (empty pages are only valid as terminal pages)
        if len(self.incidents) == 0 and self.has_more:
            raise ValueError(
                "Empty page cannot have has_more=True"
            )
        # Invariant: No empty incident IDs
        for inc in self.incidents:
            if not inc.incident_id:
                raise ValueError("incident_id must not be empty")
            if not inc.first_observed_at_key:
                raise ValueError("first_observed_at_key must not be empty")
        # Invariant: No duplicate incident IDs
        seen_ids: set[str] = set()
        for inc in self.incidents:
            if inc.incident_id in seen_ids:
                raise ValueError(f"Duplicate incident_id: {inc.incident_id}")
            seen_ids.add(inc.incident_id)
        # Invariant: next_cursor must match the last incident exactly
        # This ensures the cursor is consistent with the page contents
        if self.next_cursor is not None and len(self.incidents) > 0:
            last_incident = self.incidents[-1]
            if self.next_cursor.incident_id != last_incident.incident_id:
                raise ValueError(
                    f"next_cursor.incident_id ({self.next_cursor.incident_id}) "
                    f"must match last incident's incident_id ({last_incident.incident_id})"
                )
            if self.next_cursor.first_observed_at_text != last_incident.first_observed_at_key:
                raise ValueError(
                    f"next_cursor.first_observed_at_text ({self.next_cursor.first_observed_at_text}) "
                    f"must match last incident's first_observed_at_key ({last_incident.first_observed_at_key})"
                )


@dataclass(frozen=True, slots=True)
class CursorDecodeFailure:
    """Structured failure for cursor decoding errors."""

    error_kind: str
    error_message: str


def _build_diagnosis_page_query(
    active_only: bool,
    limit: DiagnosisPageLimit,
    after: IncidentDiagnosisCursor | None,
) -> tuple[str, list[str | int]]:
    """Build SQL query for diagnosis page.

    Uses a partial index (idx_incident_current_active_diagnosis_scan) for
    active_only queries that covers ORDER BY columns without requiring a sort.
    Uses idx_incident_current_diagnosis_scan for unfiltered queries.

    IMPORTANT: The active_only query uses literal status values instead of
    bound parameters so SQLite's query planner can match the partial index
    predicate. The ACTIVE_STATUS_PREDICATE constant must match the partial
    index WHERE clause exactly.
    """

    base_select = """
        SELECT
            incident_id,
            status,
            first_observed_at
        FROM incident_current
        WHERE 1=1
    """

    params: list[str | int] = []

    if active_only:
        # Use literal predicate to enable partial-index matching
        # NOT bound parameters - SQLite's predicate matching requires
        # the predicate text to match exactly
        base_select += f" AND {ACTIVE_STATUS_PREDICATE}"

    if after is not None:
        base_select += """
            AND (
                first_observed_at > ?
                OR (first_observed_at = ? AND incident_id > ?)
            )
        """
        # R11: Use EXACT database text for cursor key to preserve ordering
        ts_str = after.first_observed_at_text
        params.extend([ts_str, ts_str, after.incident_id])

    base_select += """
        ORDER BY first_observed_at ASC, incident_id ASC
        LIMIT ?
    """
    params.append(limit.value + 1)

    return base_select, params


def _rows_to_page(
    rows: list[tuple[str, str, str]],
    has_more: bool,
) -> IncidentDiagnosisPage:
    """Convert query rows to IncidentDiagnosisPage."""
    from datetime import datetime

    from .incident_diagnosis_keyset_cursor import cursor_after_page_incident

    incidents: list[DiagnosisPageIncident] = []
    next_cursor: IncidentDiagnosisCursor | None = None

    page_rows = rows[:len(rows) - 1] if has_more and len(rows) > 0 else rows

    for row in page_rows:
        incident_id, status, first_observed_at = row
        ts = datetime.fromisoformat(first_observed_at)
        incidents.append(DiagnosisPageIncident(
            incident_id=incident_id,
            status=status,
            first_observed_at=ts,
            first_observed_at_key=first_observed_at,  # R11: Preserve exact DB text
        ))

    if has_more and len(page_rows) > 0:
        # Use cursor_after_page_incident for exact cursor construction
        next_cursor = cursor_after_page_incident(incidents[-1])

    return IncidentDiagnosisPage(
        incidents=tuple(incidents),
        next_cursor=next_cursor,
        has_more=has_more,
    )


def list_incidents_for_diagnosis_page_impl(
    conn: object,
    active_only: bool,
    limit: DiagnosisPageLimit,
    after: IncidentDiagnosisCursor | None,
) -> IncidentDiagnosisPage:
    """Execute keyset pagination query against SQLite connection."""
    sql, params = _build_diagnosis_page_query(active_only, limit, after)
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    has_more = len(rows) > limit.value
    return _rows_to_page(list(rows), has_more)


def list_incidents_for_diagnosis_page_local(
    active_only: bool,
    limit: DiagnosisPageLimit,
    after_cursor: IncidentDiagnosisCursor | None,
) -> PageLocalListResult:
    """List incidents for diagnosis with keyset pagination (local store).

    Returns a closed result union:
    - PageListed: Successful page listing
    - PageListingFailed: Store operation failed

    This function uses the store's page listing capability seam instead of
    directly accessing the connection, keeping the store encapsulation intact.
    """
    try:
        from .incident_store_provider import get_incident_store
        store = get_incident_store()
        # Use the store's page listing capability seam
        page = store.list_incidents_for_diagnosis_page(
            active_only=active_only,
            limit=limit,
            after_cursor=after_cursor,
        )
        return PageListed(page=page)
    except Exception as e:
        _logger.exception("Failed to list incidents for diagnosis page")
        return PageListingFailed(
            failure=IncidentPageListingFailure(
                kind=IncidentPageListingFailureKind.STORE_UNAVAILABLE,
                message=str(e),
            )
        )


PageLocalListResult: TypeAlias = PageListed | PageListingFailed
"""Closed union of local page-list outcomes."""


__all__ = [
    "IncidentDiagnosisPage",
    "CursorDecodeFailure",
    "PageLocalListResult",
    "list_incidents_for_diagnosis_page_impl",
    "list_incidents_for_diagnosis_page_local",
]
