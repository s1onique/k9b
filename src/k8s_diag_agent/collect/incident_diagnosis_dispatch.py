"""Incident diagnosis dispatcher for automatic diagnosis loop.

This module is a thin facade that:
- Validates caller cursors
- Resolves dispatch mode
- Delegates to specialized modules

Configuration:
- K9B_INCIDENT_PROMOTION_MODE: local|backend-api|auto (default: auto)
- K9B_BACKEND_INTERNAL_URL: Backend service URL for backend-api mode
- K9B_INTERNAL_API_TOKEN: Token for internal API authentication
- K9B_INCIDENT_STORE_BACKEND: Backend type (memory|file|sqlite)
- K9B_PROCESS_ROLE: Process role (backend|scheduler)

This module delegates to:
- incident_diagnosis_dispatch_contracts: Error types, config, summary
- incident_diagnosis_dispatch_routes: Local store operations
- incident_diagnosis_dispatch_backend: Backend API operations
- incident_diagnosis_dispatch_pagination: Backend pagination implementation
- incident_diagnosis_dispatch_page: Page types and local pagination
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .incident_diagnosis_dispatch_backend import (
    _build_listing_error_diagnostic,
    _fetch_incident_backend_api,
    _list_incidents_backend_api,
)
from .incident_diagnosis_dispatch_contracts import (
    MODE_AUTO,
    MODE_BACKEND_API,
    MODE_LOCAL,
    BackendListingErrorType,
    DiagnosisIncidentSummary,
    IncidentDiagnosisDispatchConfig,
)
from .incident_diagnosis_dispatch_page import (
    CursorDecodeFailure,
    IncidentDiagnosisPage,
    PageListed,
    PageListingFailed,
)
from .incident_diagnosis_dispatch_pagination import (
    _list_incidents_page_backend_api,
)
from .incident_diagnosis_dispatch_routes import (
    _classify_backend_listing_error,
    _fetch_incident_local,
    _get_dispatch_config,
    _list_incidents_local,
)
from .incident_diagnosis_keyset_cursor import (
    DiagnosisPageLimit,
)
from .incident_diagnosis_pagination_results import (
    IncidentPageListResult,
    PageCursorRejected,
)
from .otel_events import (
    emit_autodiag_incident_list_failed_event,
    emit_autodiag_incident_list_start_event,
    emit_autodiag_incident_list_success_event,
)
from .otel_span_context import SpanContext

if TYPE_CHECKING:
    from .incident_store import Incident


_logger = logging.getLogger(__name__)


# =============================================================================
# Main Entry Points
# =============================================================================


def list_incidents_for_diagnosis(
    active_only: bool = True,
    limit: int | None = None,
    after_incident_id: str | None = None,
) -> tuple[list[DiagnosisIncidentSummary], bool, str | None]:
    """List incidents for the automatic diagnosis loop.

    This function selects the appropriate incident source based on configuration
    and returns ONLY active incidents (open, collecting_evidence, investigating).

    The active status filtering happens BEFORE the limit is applied to ensure
    we don't return a false-zero when non-active incidents are at the front.

    Emits structured events:
    - automatic-diagnosis-incident-list-start: Before listing
    - automatic-diagnosis-incident-list-success: After successful listing
    - automatic-diagnosis-incident-list-failed: After failed listing

    Args:
        active_only: If True, only return incidents in active status
        limit: Optional maximum number of incidents to return (applied after filtering)
        after_incident_id: Optional cursor for pagination (resume after this incident ID)

    Returns:
        Tuple of (incidents, success, error_message)
        - incidents: List of DiagnosisIncidentSummary (active status)
        - success: True if listing succeeded
        - error_message: Error message if failed, None if succeeded
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    # Emit start event
    span_ctx = SpanContext(name="list_incidents_for_diagnosis")
    emit_autodiag_incident_list_start_event(span_ctx, resolved)

    if resolved == MODE_LOCAL:
        incidents, success, error = _list_incidents_local(
            active_only=active_only,
            limit=limit,
            after_incident_id=after_incident_id,
        )
        error_type = None  # Local errors don't have classified types
    else:
        # Backend API mode - returns 4-tuple with error_type
        incidents, success, error, error_type = _list_incidents_backend_api(
            backend_url=config.backend_url,
            internal_api_token=config.internal_api_token,
            active_only=active_only,
            limit=limit,
            after_incident_id=after_incident_id,
        )

    # Emit result event
    if success:
        emit_autodiag_incident_list_success_event(span_ctx, len(incidents), resolved)
    else:
        # Sanitize error message for structured event (no stack traces)
        sanitized_error = str(error)[:500] if error else "Unknown error"
        # Build diagnostic if we have an error_type from backend API failure
        diagnostic = None
        if error_type:
            diagnostic = _build_listing_error_diagnostic(error_type, None, sanitized_error)
        emit_autodiag_incident_list_failed_event(span_ctx, sanitized_error, resolved, error_type, diagnostic)

    return incidents, success, error


def fetch_incident_for_diagnosis(
    incident_id: str,
) -> tuple[Incident | None, bool, str | None]:
    """Fetch a single incident for processing.

    This function provides backend-aware incident fetching. When running in
    backend-api mode (scheduler with sqlite), this fetches from the backend
    API instead of the local store.

    Args:
        incident_id: The incident ID to fetch

    Returns:
        Tuple of (incident, success, error_message)
        - incident: Incident object (local) or None if not found
        - success: True if fetch succeeded (even if not found)
        - error_message: Error message if failed, None if succeeded
    """
    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    if resolved == MODE_LOCAL:
        return _fetch_incident_local(incident_id)

    # Backend API mode
    return _fetch_incident_backend_api(
        backend_url=config.backend_url,
        internal_api_token=config.internal_api_token,
        incident_id=incident_id,
    )


def list_incidents_for_diagnosis_page(
    limit: DiagnosisPageLimit,
    active_only: bool = True,
    cursor: str | None = None,
) -> IncidentPageListResult:
    """List incidents for diagnosis with keyset pagination.

    This is the cursor-based API that uses keyset pagination with
    (first_observed_at, incident_id) for deterministic ordering.

    Returns algebraic result:
    - PageListed: Successful page listing
    - PageCursorRejected: Cursor decoding failed
    - PageListingFailed: Page listing operation failed

    Args:
        active_only: If True, only return incidents in active status
        limit: Maximum number of incidents per page (DiagnosisPageLimit)
        cursor: Optional opaque cursor token for pagination

    Returns:
        IncidentPageListResult with exhaustive variants
    """
    from typing import assert_never

    from .incident_diagnosis_keyset_cursor import (
        decode_cursor,
    )

    # Decode cursor if provided (cursor validation)
    decoded_cursor = None
    if cursor is not None:
        decoded_cursor, cursor_err = decode_cursor(cursor)
        if cursor_err is not None:
            # Convert CursorDecodeError to CursorDecodeFailure for PageCursorRejected
            return PageCursorRejected(
                failure=CursorDecodeFailure(
                    error_kind=cursor_err.kind,
                    error_message=cursor_err.message,
                )
            )

    config = _get_dispatch_config()
    resolved = config.resolved_mode()

    if resolved == MODE_LOCAL:
        from .incident_diagnosis_dispatch_page import list_incidents_for_diagnosis_page_local

        result = list_incidents_for_diagnosis_page_local(
            active_only=active_only,
            limit=limit,
            after_cursor=decoded_cursor,
        )
        # Local mode returns PageListed | PageListingFailed - pass through directly
        match result:
            case PageListed():
                return result
            case PageListingFailed():
                return result
            case _ as unreachable:
                assert_never(unreachable)

    # Backend API mode - delegate to pagination module
    return _list_incidents_page_backend_api(
        backend_url=config.backend_url,
        internal_api_token=config.internal_api_token,
        active_only=active_only,
        limit=limit,
        cursor=cursor,
    )


__all__ = [
    "BackendListingErrorType",
    "CursorDecodeFailure",
    "DiagnosisPageLimit",
    "IncidentDiagnosisDispatchConfig",
    "IncidentDiagnosisPage",
    "IncidentPageListResult",
    "DiagnosisIncidentSummary",
    "list_incidents_for_diagnosis",
    "list_incidents_for_diagnosis_page",
    "fetch_incident_for_diagnosis",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
    # Internal helpers exported for testing compatibility
    "_build_listing_error_diagnostic",
    "_classify_backend_listing_error",
]
