"""Internal API read handlers for incident listing.

This module provides GET handlers for the scheduler-to-backend incident
read API endpoints (listing and fetching incidents).

Query parameters for GET /api/internal/incidents:
    status: Optional status filter (e.g., "open", "collecting_evidence")
    limit: Optional maximum number of incidents to return (1-1000)
    cursor: Optional opaque cursor token for keyset pagination
    activeOnly: If "true", only return active incidents (open, collecting_evidence, investigating)

Response format:
    {
        "incidents": [...],
        "nextCursor": "opaque-token-or-null",
        "hasMore": false,
        "total": N
    }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..collect.incident_diagnosis_keyset_cursor import (
    MAX_DIAGNOSIS_PAGE_LIMIT as _MAX_DIAGNOSIS_PAGE_LIMIT,
)

# Import canonical page limit constant and branded type
from ..collect.incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
)
from .api_incident_internal_reads import (
    build_incident_internal_detail_response_payload,
    build_incident_internal_list_item_payload,
)
from .server_incident_internal_auth import _validate_internal_token

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)


# =============================================================================
# HTTP Query Validation Constants
# =============================================================================

# Valid activeOnly values
VALID_ACTIVE_ONLY_VALUES = frozenset({"true", "false", "1", "0", "yes", "no"})

# Maximum allowed page limit (uses canonical constant from incident_diagnosis_keyset_cursor)
# Exposed for external compatibility; validation uses _MAX_DIAGNOSIS_PAGE_LIMIT
MAX_DIAGNOSIS_PAGE_LIMIT = _MAX_DIAGNOSIS_PAGE_LIMIT


# =============================================================================
# Typed Query Result (Side-Effect Free)
# =============================================================================


@dataclass(frozen=True, slots=True)
class IncidentListQuery:
    """Parsed and validated query parameters for incident listing.

    Attributes:
        status: Exact status filter (only for legacy path without pagination)
        page_limit: Validated DiagnosisPageLimit for pagination mode (None means no pagination)
        cursor: Validated cursor token for pagination
        active_only: Whether to filter by active statuses only
        uses_pagination: True if pagination mode (limit specified)
    """

    status: str | None
    page_limit: DiagnosisPageLimit | None
    cursor: str | None
    active_only: bool
    uses_pagination: bool


@dataclass(frozen=True, slots=True)
class QueryRejected:
    """Query parameter validation failed.

    Attributes:
        parameter: Name of the parameter that failed validation
        message: Human-readable error message
    """

    parameter: str
    message: str


# Valid activeOnly values
_VALID_ACTIVE_ONLY_VALUES = frozenset({"true", "false", "1", "0", "yes", "no"})

# Maximum allowed page limit - use canonical constant from incident_diagnosis_keyset_cursor
# Note: _MAX_DIAGNOSIS_PAGE_LIMIT is defined at module level (imported from canonical module)


def _parse_incident_list_query(
    query_string: str,
) -> IncidentListQuery | QueryRejected:
    """Parse and validate incident list query parameters.

    This function is pure: it does not send HTTP responses.
    Callers MUST handle QueryRejected before sending any response.

    Validation rules:
    - limit: 1-1000, required for pagination mode
    - cursor: non-empty string, requires limit
    - activeOnly: valid boolean vocabulary
    - status: not allowed with pagination (use activeOnly instead)

    Args:
        query_string: Raw query string from URL

    Returns:
        IncidentListQuery on success
        QueryRejected on validation failure
    """
    from urllib.parse import parse_qs

    # Parse with keep_blank_values=True to distinguish ?limit= from no param
    params = parse_qs(query_string, keep_blank_values=True)

    # Validate limit
    limit_values = params.get("limit", [])
    if len(limit_values) > 1:
        return QueryRejected(
            parameter="limit",
            message="Multiple 'limit' values not allowed",
        )

    page_limit: DiagnosisPageLimit | None = None
    if limit_values:
        limit_str = limit_values[0]
        if not limit_str:
            return QueryRejected(
                parameter="limit",
                message="'limit' parameter cannot be blank",
            )
        try:
            parsed_limit = int(limit_str)
        except ValueError:
            return QueryRejected(
                parameter="limit",
                message=f"'limit' must be an integer, got: {limit_str}",
            )
        # Construct branded DiagnosisPageLimit - this owns range validation
        try:
            page_limit = DiagnosisPageLimit(parsed_limit)
        except (TypeError, ValueError) as exc:
            return QueryRejected(
                parameter="limit",
                message=str(exc),
            )

    uses_pagination = page_limit is not None

    # Validate cursor
    cursor_values = params.get("cursor", [])
    if len(cursor_values) > 1:
        return QueryRejected(
            parameter="cursor",
            message="Multiple 'cursor' values not allowed",
        )

    cursor: str | None = None
    if cursor_values:
        cursor = cursor_values[0]
        if not cursor:
            return QueryRejected(
                parameter="cursor",
                message="'cursor' parameter cannot be blank",
            )
        # Cursor requires pagination mode
        if not uses_pagination:
            return QueryRejected(
                parameter="cursor",
                message="'cursor' requires 'limit' parameter for pagination mode",
            )

    # Validate activeOnly
    active_only_values = params.get("activeOnly", [])
    if len(active_only_values) > 1:
        return QueryRejected(
            parameter="activeOnly",
            message="Multiple 'activeOnly' values not allowed",
        )

    active_only = False
    if active_only_values:
        value = active_only_values[0].lower()
        if value not in _VALID_ACTIVE_ONLY_VALUES:
            return QueryRejected(
                parameter="activeOnly",
                message=f"Invalid 'activeOnly' value: '{value}'. "
                        f"Expected one of: true, false, 1, 0, yes, no",
            )
        active_only = value in ("true", "1", "yes")

    # Validate status
    status_values = params.get("status", [])
    if len(status_values) > 1:
        return QueryRejected(
            parameter="status",
            message="Multiple 'status' values not allowed",
        )

    status: str | None = None
    if status_values:
        status = status_values[0]
        # Reject status with pagination (use activeOnly instead)
        if uses_pagination:
            return QueryRejected(
                parameter="status",
                message="Cannot combine 'status' filter with 'limit' parameter. "
                        "Use 'activeOnly=true' for status filtering with pagination.",
            )

    return IncidentListQuery(
        status=status,
        page_limit=page_limit,
        cursor=cursor,
        active_only=active_only,
        uses_pagination=uses_pagination,
    )


def _send_bad_request(handler: HealthUIRequestHandler, message: str) -> None:
    """Send a 400 Bad Request response."""
    handler._send_json({
        "error": "Bad Request",
        "message": message,
    }, 400)


# =============================================================================
# Handlers
# =============================================================================


def handle_get_incident(handler: HealthUIRequestHandler, incident_id: str) -> None:
    """Handle GET /api/internal/incidents/{incident_id}.

    This endpoint fetches a single incident from the backend SQLite store
    for processing by the automatic diagnosis loop when running in backend-api mode.

    Response:
        Full incident dict if found, or error response
    """
    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Fetch incident from store
    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()
        incident = store.get_incident(incident_id)

        if incident is None:
            handler._send_json(
                {"error": "Not Found", "message": f"Incident {incident_id} not found"},
                404,
            )
            return

        # Haskellized: use total projection function for serialization
        # instead of ad-hoc field access scattered in handler
        # Uses wrapper response with canonical incident.to_dict() for scheduler compatibility
        handler._send_json(
            build_incident_internal_detail_response_payload(incident),
            200,
        )

    except Exception as e:
        _logger.exception("Failed to get incident %s", incident_id)
        handler._send_json({
            "error": "Internal Error",
            "message": str(e),
        }, 500)


def handle_list_incidents(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/internal/incidents/list.

    This endpoint lists incidents from the backend SQLite store for the
    automatic diagnosis loop when running in backend-api mode.

    Query parameters:
        status: Optional exact status filter (e.g., "open", "collecting_evidence")
            - Only respected when limit is NOT specified (legacy path)
            - Rejected when limit is specified (uses activeOnly instead)
        limit: Optional maximum number of incidents to return (1-1000)
            - When specified, uses keyset pagination with activeOnly filtering
        cursor: Optional opaque cursor token for keyset pagination
            - Requires limit parameter
        activeOnly: If "true", only return active incidents (open, collecting_evidence,
            investigating, ready_for_review)
            - Only used when limit is specified

    Response:
        {
            "incidents": [...],
            "nextCursor": "opaque-token-or-null",
            "hasMore": false,
            "total": N
        }

    Note:
        When limit is specified, the page API uses activeOnly for status filtering.
        The status query parameter is rejected in this case to ensure consistent
        behavior with the keyset pagination implementation.
    """
    from urllib.parse import urlparse

    from ..collect.incident_diagnosis_dispatch_page import (
        IncidentDiagnosisPage,
    )
    from ..collect.incident_diagnosis_keyset_cursor import (
        decode_cursor,
        encode_cursor,
    )

    # Validate authentication
    if not _validate_internal_token(handler):
        handler._send_json(
            {"error": "Unauthorized", "message": "Valid internal API token required"},
            401,
        )
        return

    # Parse and validate query parameters (pure, no side effects)
    parsed = urlparse(handler.path)
    query_result = _parse_incident_list_query(parsed.query)

    if isinstance(query_result, QueryRejected):
        _send_bad_request(handler, query_result.message)
        return

    # query_result is IncidentListQuery
    query: IncidentListQuery = query_result

    # Decode cursor if provided
    cursor = None
    if query.cursor:
        cursor, cursor_err = decode_cursor(query.cursor)
        if cursor_err is not None:
            _logger.info(
                "Invalid cursor in request",
                extra={
                    "event": "incident-list-cursor-invalid",
                    "error_kind": cursor_err.kind,
                    "error_message": cursor_err.message,
                },
            )
            handler._send_json({
                "error": "Bad Request",
                "message": "Invalid cursor",
                "error_kind": cursor_err.kind,
                "error_message": cursor_err.message,
            }, 400)
            return

    # List incidents from store
    try:
        from ..collect.incident_store_provider import get_incident_store

        store = get_incident_store()

        # Pagination path: limit specified
        if query.uses_pagination:
            # Use the already-validated DiagnosisPageLimit from query parsing
            assert query.page_limit is not None
            page: IncidentDiagnosisPage = store.list_incidents_for_diagnosis_page(
                active_only=query.active_only,
                limit=query.page_limit,
                after_cursor=cursor,
            )

            # Encode next cursor if present
            next_cursor_token: str | None = None
            if page.next_cursor is not None:
                next_cursor_token = encode_cursor(page.next_cursor)

            handler._send_json({
                "incidents": [
                    {
                        "incident_id": inc.incident_id,
                        "status": inc.status,
                        # R13: Use first_observed_at_key for exact cursor ordering
                        "first_observed_at": inc.first_observed_at_key,
                    }
                    for inc in page.incidents
                ],
                "nextCursor": next_cursor_token,
                "hasMore": page.has_more,
                "total": len(page.incidents),
            }, 200)
            return

        # Legacy path: no limit specified, use original behavior for backward compatibility
        from ..collect.incident_lifecycle import IncidentStatus

        # Parse status filter if provided (for backward compat)
        status_filter: IncidentStatus | None = None
        if query.status is not None:
            try:
                status_filter = IncidentStatus(query.status)
            except ValueError:
                handler._send_json(
                    {"error": "Bad Request", "message": f"Invalid status: {query.status}"},
                    400,
                )
                return

        # Get incidents from store
        incidents = store.list_incidents(status=status_filter)

        # Haskellized: use total projection function for serialization
        # instead of ad-hoc field access scattered in handler
        incident_summaries = [
            build_incident_internal_list_item_payload(inc)
            for inc in incidents
        ]

        handler._send_json({
            "incidents": incident_summaries,
            "nextCursor": None,
            "hasMore": False,
            "total": len(incident_summaries),
        }, 200)

    except Exception as e:
        _logger.exception("Failed to list incidents")
        # Projection failure is an internal error - return 500, not 200
        handler._send_json({
            "error": "Internal Error",
            "message": str(e),
        }, 500)
