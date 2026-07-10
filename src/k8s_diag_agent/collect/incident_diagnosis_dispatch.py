"""Incident diagnosis dispatcher for automatic diagnosis loop.

This module selects the appropriate incident source (local vs backend-api) based on
configuration and provides a unified interface for the automatic diagnosis loop.

Configuration:
- K9B_INCIDENT_PROMOTION_MODE: local|backend-api|auto (default: auto)
- K9B_BACKEND_INTERNAL_URL: Backend service URL for backend-api mode
- K9B_INTERNAL_API_TOKEN: Token for internal API authentication
- K9B_INCIDENT_STORE_BACKEND: Backend type (memory|file|sqlite)
- K9B_PROCESS_ROLE: Process role (backend|scheduler)

Behavior:
- local: Use existing local get_incident_store() for incident listing and fetch
- backend-api: List and fetch incidents via backend internal API (required for scheduler+sqlite)
- auto: Use backend-api if K9B_INCIDENT_STORE_BACKEND=sqlite or K9B_PROCESS_ROLE=scheduler

This module mirrors the pattern from incident_promotion_dispatch.py but for
the automatic diagnosis loop's incident listing requirement.

Structured Events:
- automatic-diagnosis-incident-list-start: Emitted when incident listing begins
- automatic-diagnosis-incident-list-success: Emitted when incident listing succeeds
- automatic-diagnosis-incident-list-failed: Emitted when incident listing fails

This module is a facade that re-exports from specialized modules:
- incident_diagnosis_dispatch_contracts: Error types, config, summary
- incident_diagnosis_dispatch_routes: Local store operations
- incident_diagnosis_dispatch_backend: Backend API operations
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .incident_diagnosis_dispatch_backend import (
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
from .incident_diagnosis_dispatch_routes import (
    _fetch_incident_local,
    _get_dispatch_config,
    _list_incidents_local,
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
        incidents, success, error = _list_incidents_local(active_only=active_only, limit=limit)
        error_type = None  # Local errors don't have classified types
    else:
        # Backend API mode - returns 4-tuple with error_type
        incidents, success, error, error_type = _list_incidents_backend_api(
            backend_url=config.backend_url,
            internal_api_token=config.internal_api_token,
            active_only=active_only,
            limit=limit,
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
            from .incident_diagnosis_dispatch_backend import _build_listing_error_diagnostic

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


__all__ = [
    "BackendListingErrorType",
    "IncidentDiagnosisDispatchConfig",
    "DiagnosisIncidentSummary",
    "list_incidents_for_diagnosis",
    "fetch_incident_for_diagnosis",
    "MODE_AUTO",
    "MODE_BACKEND_API",
    "MODE_LOCAL",
]
