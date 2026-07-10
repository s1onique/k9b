"""Backend transport parser for incident diagnosis page responses.

This module provides a TOTAL parser for backend page responses that:
- Validates the response structure exactly once
- Rejects malformed data with classified errors
- Returns typed DiagnosisPageTransport on success

After successful parsing, raw payload dictionaries must NOT be accessed again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias

from .incident_diagnosis_page_transport_failures import (
    MAX_INCIDENT_ID_LENGTH,
    MAX_NEXTCURSOR_LENGTH,
    BackendProtocolFailure,
    BackendProtocolFailureKind,
)

if TYPE_CHECKING:
    from .incident_diagnosis_dispatch_contracts import DiagnosisPageIncident
    from .incident_diagnosis_pagination_types import OpaqueCursorToken


# =============================================================================
# Transport Result Variants
# =============================================================================


@dataclass(frozen=True, slots=True)
class DiagnosisPageTransport:
    """Parsed backend page transport.

    After successful parsing, raw payload dictionaries must NOT be accessed.
    Use this typed transport for all subsequent operations.

    Attributes:
        incidents: Tuple of parsed page incidents.
        next_cursor_token: Opaque cursor token for next page, or None.
        has_more: True if there are more pages.
        total: Total count of incidents.
    """

    incidents: tuple[DiagnosisPageIncident, ...]
    next_cursor_token: OpaqueCursorToken | None
    has_more: bool
    total: int


@dataclass(frozen=True, slots=True)
class PageTransportParsed:
    """Successful transport parse result (full page)."""

    value: DiagnosisPageTransport


@dataclass(frozen=True, slots=True)
class PageIncidentParsed:
    """Successful incident parse result (single incident)."""

    value: DiagnosisPageIncident


@dataclass(frozen=True, slots=True)
class PageTransportRejected:
    """Transport parse failed due to protocol violation."""

    failure: BackendProtocolFailure


PageTransportParseResult: TypeAlias = PageTransportParsed | PageTransportRejected
"""Closed union of transport parse outcomes for full page."""

PageIncidentParseResult: TypeAlias = PageIncidentParsed | PageTransportRejected
"""Closed union of parse outcomes for single incident."""


# =============================================================================
# Parser
# =============================================================================


def parse_diagnosis_page_transport(
    payload: object,
) -> PageTransportParseResult:
    """Parse and validate a backend diagnosis page response.

    This function validates:
    - Top-level payload is an object
    - 'incidents' is a list of objects
    - Each incident has valid incident_id (nonempty, bounded string)
    - Each incident has valid status
    - Each incident has valid first_observed_at (nonempty, parseable, timezone-aware)
    - 'nextCursor' is null or a bounded string
    - 'hasMore' is exactly bool
    - 'total' is a nonnegative integer
    - hasMore=True requires nextCursor
    - hasMore=False requires nextCursor=None

    After successful parsing, raw payload dictionaries must NOT be accessed.

    Args:
        payload: Raw JSON response from backend

    Returns:
        PageTransportParseResult with either parsed transport or rejection
    """
    # Validate top-level object
    if not isinstance(payload, dict):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.NON_OBJECT_PAYLOAD,
                message=f"Expected object, got {type(payload).__name__}",
            )
        )

    # Validate incidents list
    incidents_raw = payload.get("incidents")
    if incidents_raw is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.MISSING_INCIDENTS,
                message="Missing 'incidents' field",
            )
        )

    if not isinstance(incidents_raw, list):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INCIDENTS_NOT_LIST,
                message=f"'incidents' must be a list, got {type(incidents_raw).__name__}",
            )
        )

    # Parse each incident
    incidents: list[DiagnosisPageIncident] = []
    seen_ids: set[str] = set()  # Track for duplicate detection
    for i, inc in enumerate(incidents_raw):
        incident_result = _parse_incident(inc, i)
        if isinstance(incident_result, PageTransportRejected):
            return incident_result
        # incident_result is PageIncidentParsed with DiagnosisPageIncident value

        # Check for duplicate incident IDs within the page
        if incident_result.value.incident_id in seen_ids:
            return PageTransportRejected(
                failure=BackendProtocolFailure(
                    kind=BackendProtocolFailureKind.INCIDENT_ID_DUPLICATE,
                    message=f"Duplicate incident_id '{incident_result.value.incident_id}' in page",
                    incident_index=i,
                )
            )
        seen_ids.add(incident_result.value.incident_id)
        incidents.append(incident_result.value)

    # Validate hasMore
    has_more_raw = payload.get("hasMore")
    if not isinstance(has_more_raw, bool):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.HASMORE_WRONG_TYPE,
                message=f"'hasMore' must be bool, got {type(has_more_raw).__name__}",
            )
        )

    # Validate nextCursor
    next_cursor_raw = payload.get("nextCursor")
    if next_cursor_raw is not None and not isinstance(next_cursor_raw, str):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.NEXTCURSOR_WRONG_TYPE,
                message=f"'nextCursor' must be null or string, got {type(next_cursor_raw).__name__}",
            )
        )

    # Validate nextCursor is not empty
    if next_cursor_raw is not None and not next_cursor_raw:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.NEXTCURSOR_WRONG_TYPE,
                message="'nextCursor' must not be empty",
            )
        )

    # Validate nextCursor length bound
    if next_cursor_raw is not None and len(next_cursor_raw) > MAX_NEXTCURSOR_LENGTH:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.NEXTCURSOR_WRONG_TYPE,
                message=f"'nextCursor' exceeds maximum length of {MAX_NEXTCURSOR_LENGTH}",
            )
        )

    # Validate hasMore/nextCursor consistency
    if has_more_raw and next_cursor_raw is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.HASMORE_TRUE_NO_NEXTCURSOR,
                message="'hasMore=true' requires 'nextCursor' to be present",
            )
        )

    if not has_more_raw and next_cursor_raw is not None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.HASMORE_FALSE_WITH_NEXTCURSOR,
                message="'hasMore=false' requires 'nextCursor' to be null",
            )
        )

    # Validate total
    total_raw = payload.get("total")
    # Use type() check to reject bool (bool is subclass of int in Python)
    if type(total_raw) is not int or total_raw < 0:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.TOTAL_WRONG_TYPE,
                message=f"'total' must be a nonnegative integer, got {type(total_raw).__name__}: {total_raw}",
            )
        )

    # Build transport
    from .incident_diagnosis_pagination_types import OpaqueCursorToken

    next_cursor_token: OpaqueCursorToken | None = None
    if next_cursor_raw is not None:
        next_cursor_token = OpaqueCursorToken(next_cursor_raw)

    return PageTransportParsed(
        value=DiagnosisPageTransport(
            incidents=tuple(incidents),
            next_cursor_token=next_cursor_token,
            has_more=has_more_raw,
            total=total_raw,
        )
    )


def _parse_incident(
    inc: object,
    index: int,
) -> PageIncidentParseResult:
    """Parse a single incident from the incidents list.

    Returns PageIncidentParsed with DiagnosisPageIncident on success,
    or PageTransportRejected on failure.
    """
    from .incident_diagnosis_dispatch_contracts import DiagnosisPageIncident
    from .incident_diagnosis_pagination_types import (
        FirstObservedAtKey,
    )

    if not isinstance(inc, dict):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INCIDENT_NOT_OBJECT,
                message=f"Incident {index} must be an object, got {type(inc).__name__}",
                incident_index=index,
            )
        )

    # Parse incident_id
    incident_id_raw = inc.get("incident_id")
    if incident_id_raw is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.MISSING_INCIDENT_ID,
                message=f"Incident {index} missing 'incident_id'",
                incident_index=index,
            )
        )

    if not isinstance(incident_id_raw, str):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INCIDENT_ID_NOT_STRING,
                message=f"Incident {index} 'incident_id' must be string, got {type(incident_id_raw).__name__}",
                incident_index=index,
            )
        )

    if not incident_id_raw:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INCIDENT_ID_EMPTY,
                message=f"Incident {index} 'incident_id' is empty",
                incident_index=index,
            )
        )

    if len(incident_id_raw) > MAX_INCIDENT_ID_LENGTH:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INCIDENT_ID_TOO_LONG,
                message=f"Incident {index} 'incident_id' exceeds {MAX_INCIDENT_ID_LENGTH} chars",
                incident_index=index,
            )
        )

    # Parse status using canonical enum
    from .incident_lifecycle_types import IncidentStatus

    status_raw = inc.get("status")
    if status_raw is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.MISSING_STATUS,
                message=f"Incident {index} missing 'status'",
                incident_index=index,
            )
        )

    if not isinstance(status_raw, str):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INVALID_STATUS,
                message=f"Incident {index} 'status' must be string, got {type(status_raw).__name__}",
                incident_index=index,
            )
        )

    # Validate status using canonical enum parsing
    try:
        status_enum = IncidentStatus(status_raw)
    except ValueError:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.INVALID_STATUS,
                message=f"Incident {index} 'status' must be one of {[s.value for s in IncidentStatus]}, got '{status_raw}'",
                incident_index=index,
            )
        )

    # Use enum value for storage
    status_value = status_enum.value

    # Parse timestamp
    ts_raw = inc.get("first_observed_at")
    if ts_raw is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.MISSING_TIMESTAMP,
                message=f"Incident {index} missing 'first_observed_at'",
                incident_index=index,
            )
        )

    if not isinstance(ts_raw, str):
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.TIMESTAMP_NOT_STRING,
                message=f"Incident {index} 'first_observed_at' must be string, got {type(ts_raw).__name__}",
                incident_index=index,
            )
        )

    if not ts_raw:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.TIMESTAMP_EMPTY,
                message=f"Incident {index} 'first_observed_at' is empty",
                incident_index=index,
            )
        )

    # Parse timestamp value
    try:
        ts = datetime.fromisoformat(ts_raw)
    except ValueError:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.TIMESTAMP_INVALID,
                message=f"Incident {index} 'first_observed_at' is not a valid ISO timestamp: {ts_raw}",
                incident_index=index,
            )
        )

    # Validate timezone awareness
    if ts.tzinfo is None:
        return PageTransportRejected(
            failure=BackendProtocolFailure(
                kind=BackendProtocolFailureKind.TIMESTAMP_NAIVE,
                message=f"Incident {index} 'first_observed_at' is timezone-naive: {ts_raw}",
                incident_index=index,
            )
        )

    # Build incident with exact key preserved
    return PageIncidentParsed(
        value=DiagnosisPageIncident(
            incident_id=incident_id_raw,
            status=status_value,
            first_observed_at=ts,
            first_observed_at_key=FirstObservedAtKey(ts_raw),  # Preserve exact text
        )
    )


__all__ = [
    "BackendProtocolFailureKind",
    "BackendProtocolFailure",
    "DiagnosisPageTransport",
    "PageTransportParsed",
    "PageIncidentParsed",
    "PageTransportRejected",
    "PageTransportParseResult",
    "PageIncidentParseResult",
    "parse_diagnosis_page_transport",
]
