"""Page-oriented incident listing for automatic diagnosis loop.

This module provides:
- BackendPageListResult: Closed union of backend page-list outcomes
- _list_incidents_page_backend_api: Backend API pagination implementation
- _classify_transport_failure_kind: Maps transport failures to listing failure kinds
- _map_scheduler_error_type: Maps scheduler error types to failure kinds

These functions handle keyset pagination with (first_observed_at, incident_id)
for deterministic ordering and progress even when incidents are updated.

Note: Cursor rejection (caller-provided cursor decode failure) is handled at the
outer dispatch boundary. This module only handles backend API results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeAlias

from .incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from .incident_diagnosis_dispatch_page import (
    IncidentDiagnosisPage,
    PageListed,
    PageListingFailed,
)
from .incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
)
from .incident_diagnosis_pagination_results import (
    IncidentPageListingFailure,
    IncidentPageListingFailureKind,
)

if TYPE_CHECKING:
    from .incident_diagnosis_page_transport import BackendProtocolFailure


_logger = logging.getLogger(__name__)


# =============================================================================
# Backend API Result Type
# =============================================================================


BackendPageListResult: TypeAlias = PageListed | PageListingFailed
"""Closed union of backend page-list outcomes.

This union contains only backend API results. Cursor rejection from caller-provided
cursors is handled at the outer dispatch boundary using PageCursorRejected from
incident_diagnosis_pagination_results.
"""


# =============================================================================
# Backend API Pagination Implementation
# =============================================================================


def _list_incidents_page_backend_api(
    backend_url: str | None,
    internal_api_token: str | None,
    active_only: bool,
    limit: DiagnosisPageLimit,
    cursor: str | None,
) -> BackendPageListResult:
    """List incidents from backend with keyset pagination.

    Uses parse_diagnosis_page_transport() for total parsing.
    Returns closed result union with proper PROTOCOL_VIOLATION classification.

    Args:
        backend_url: Backend service URL
        internal_api_token: Internal API token
        active_only: If True, only return active incidents
        limit: Maximum number of incidents per page
        cursor: Optional cursor token

    Returns:
        BackendPageListResult with proper failure classification
    """
    from typing import assert_never

    from ..ui.server_incident_internal_client import SchedulerClient
    from .incident_diagnosis_page_transport import (
        PageTransportParsed,
        PageTransportRejected,
        parse_diagnosis_page_transport,
    )

    if not backend_url:
        return PageListingFailed(
            failure=IncidentPageListingFailure(
                kind=IncidentPageListingFailureKind.MISSING_BACKEND_URL,
                message="Backend URL not configured",
            )
        )

    if not internal_api_token:
        return PageListingFailed(
            failure=IncidentPageListingFailure(
                kind=IncidentPageListingFailureKind.MISSING_INTERNAL_TOKEN,
                message="Internal API token not configured",
            )
        )

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    try:
        # Extract int value for HTTP transport (SchedulerClient expects int)
        limit_int = limit.value
        # Use new cursor-based API
        response = client.list_incidents(
            active_only=active_only,
            limit=limit_int,
            cursor=cursor,
        )

        # Check for error in response (pre-parse check)
        # Preserve error_type and status_code from SchedulerClient for proper classification
        if "error" in response:
            error_msg = str(response.get("error", "Unknown error"))
            error_type = str(response.get("error_type", "unknown"))
            status_code = response.get("status_code")

            # Map SchedulerClient error_type to IncidentPageListingFailureKind
            classified_kind = _map_scheduler_error_type(error_type, status_code)

            return PageListingFailed(
                failure=IncidentPageListingFailure(
                    kind=classified_kind,
                    message=f"Backend returned error: {error_msg}",
                    status_code=status_code,
                )
            )

        # Total parse of response using PageTransport parser
        parse_result = parse_diagnosis_page_transport(response)

        match parse_result:
            case PageTransportRejected(failure=failure):
                # Malformed backend response is a PROTOCOL_VIOLATION, not a caller cursor error.
                # Classify exact failure kind for proper error handling.
                protocol_kind = _classify_transport_failure_kind(failure)
                return PageListingFailed(
                    failure=IncidentPageListingFailure(
                        kind=protocol_kind,
                        message=f"Backend protocol error: {failure.message}",
                    )
                )
            case PageTransportParsed(value=transport):
                # Decode next cursor if present
                # NOTE: A backend-provided cursor that fails to decode is a PROTOCOL_VIOLATION,
                # not a caller cursor error. Only caller-provided cursors use PageCursorRejected.
                from .incident_diagnosis_keyset_cursor import decode_cursor

                page_cursor = None
                if transport.next_cursor_token is not None:
                    page_cursor, err = decode_cursor(str(transport.next_cursor_token))
                    if err:
                        # Backend returned an invalid nextCursor - this is a protocol violation
                        return PageListingFailed(
                            failure=IncidentPageListingFailure(
                                kind=IncidentPageListingFailureKind.PROTOCOL_VIOLATION,
                                message=f"Backend returned invalid nextCursor: {err.message}",
                            )
                        )

                # Build page from parsed transport (incidents already validated)
                page_incidents = [
                    DiagnosisPageIncident(
                        incident_id=inc.incident_id,
                        status=inc.status,
                        first_observed_at=inc.first_observed_at,
                        first_observed_at_key=inc.first_observed_at_key,
                    )
                    for inc in transport.incidents
                ]

                page = IncidentDiagnosisPage(
                    incidents=tuple(page_incidents),
                    next_cursor=page_cursor,
                    has_more=transport.has_more,
                )
                return PageListed(page=page)
            case _ as unreachable:
                assert_never(unreachable)

    except Exception as e:
        _logger.exception("Failed to list incidents page from backend")
        return PageListingFailed(
            failure=IncidentPageListingFailure(
                kind=IncidentPageListingFailureKind.INTERNAL_ERROR,
                message=str(e),
            )
        )


def _classify_transport_failure_kind(
    failure: BackendProtocolFailure,
) -> IncidentPageListingFailureKind:
    """Classify a transport protocol failure to listing failure kind.

    Maps transport failures to appropriate INTERNAL_ERROR or PROTOCOL_VIOLATION
    based on whether the failure indicates a malformed backend response.
    """
    from .incident_diagnosis_page_transport import (
        BackendProtocolFailureKind,
    )

    # These are clearly protocol violations (malformed backend response)
    protocol_violation_kinds = {
        BackendProtocolFailureKind.NON_OBJECT_PAYLOAD,
        BackendProtocolFailureKind.MISSING_INCIDENTS,
        BackendProtocolFailureKind.INCIDENTS_NOT_LIST,
        BackendProtocolFailureKind.INCIDENT_NOT_OBJECT,
        BackendProtocolFailureKind.MISSING_INCIDENT_ID,
        BackendProtocolFailureKind.INCIDENT_ID_NOT_STRING,
        BackendProtocolFailureKind.INCIDENT_ID_EMPTY,
        BackendProtocolFailureKind.INCIDENT_ID_TOO_LONG,
        BackendProtocolFailureKind.INCIDENT_ID_DUPLICATE,  # Duplicate IDs in page
        BackendProtocolFailureKind.MISSING_STATUS,
        BackendProtocolFailureKind.INVALID_STATUS,
        BackendProtocolFailureKind.MISSING_TIMESTAMP,
        BackendProtocolFailureKind.TIMESTAMP_NOT_STRING,
        BackendProtocolFailureKind.TIMESTAMP_EMPTY,
        BackendProtocolFailureKind.TIMESTAMP_INVALID,
        BackendProtocolFailureKind.TIMESTAMP_NAIVE,
        BackendProtocolFailureKind.NEXTCURSOR_WRONG_TYPE,
        BackendProtocolFailureKind.HASMORE_WRONG_TYPE,
        BackendProtocolFailureKind.TOTAL_WRONG_TYPE,
        BackendProtocolFailureKind.HASMORE_TRUE_NO_NEXTCURSOR,
        BackendProtocolFailureKind.HASMORE_FALSE_WITH_NEXTCURSOR,
        BackendProtocolFailureKind.PROTOCOL_VIOLATION,
    }

    if failure.kind in protocol_violation_kinds:
        return IncidentPageListingFailureKind.PROTOCOL_VIOLATION

    # Default to internal error for unknown transport failures
    return IncidentPageListingFailureKind.INTERNAL_ERROR


def _map_scheduler_error_type(
    error_type: str,
    status_code: int | None,
) -> IncidentPageListingFailureKind:
    """Map SchedulerClient error_type to IncidentPageListingFailureKind.

    This preserves the classified error type from the scheduler client
    instead of flattening all errors to INTERNAL_ERROR.

    SchedulerClient error_types:
    - missing_backend_url, missing_internal_token: Already handled before this
    - unauthorized (401): Map to UNAUTHORIZED
    - forbidden (403): Map to FORBIDDEN
    - timeout: Map to TIMEOUT
    - invalid_json: Map to INVALID_JSON
    - unexpected_shape: Map to PROTOCOL_VIOLATION
    - backend_unreachable, transport failures: Map to TRANSPORT_FAILURE
    - unknown, backend_error, bad_response: Map to INTERNAL_ERROR
    """
    # Check status_code first for HTTP semantics
    if status_code is not None:
        if status_code == 401:
            return IncidentPageListingFailureKind.UNAUTHORIZED
        if status_code == 403:
            return IncidentPageListingFailureKind.FORBIDDEN
        if status_code >= 500:
            return IncidentPageListingFailureKind.INTERNAL_ERROR

    # Map by error_type string
    error_type_lower = error_type.lower()
    if error_type_lower in ("unauthorized",):
        return IncidentPageListingFailureKind.UNAUTHORIZED
    if error_type_lower in ("forbidden",):
        return IncidentPageListingFailureKind.FORBIDDEN
    if error_type_lower in ("timeout",):
        return IncidentPageListingFailureKind.TIMEOUT
    if error_type_lower in ("invalid_json",):
        return IncidentPageListingFailureKind.INVALID_JSON
    if error_type_lower in ("unexpected_shape",):
        return IncidentPageListingFailureKind.PROTOCOL_VIOLATION
    if error_type_lower in ("backend_unreachable", "transport_failure", "connection_refused"):
        return IncidentPageListingFailureKind.TRANSPORT_FAILURE
    if error_type_lower in ("not_found",):
        return IncidentPageListingFailureKind.PROTOCOL_VIOLATION

    # Default to internal error for unknown error types
    return IncidentPageListingFailureKind.INTERNAL_ERROR


__all__ = [
    "BackendPageListResult",
    "_list_incidents_page_backend_api",
    "_classify_transport_failure_kind",
    "_map_scheduler_error_type",
]
