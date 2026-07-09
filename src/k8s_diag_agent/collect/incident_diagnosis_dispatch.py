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
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .incident_diagnosis_dispatch_contracts import (
    _ACTIVE_STATUS_NAMES,
    MODE_AUTO,
    MODE_BACKEND_API,
    MODE_LOCAL,
    BackendListingErrorType,
    DiagnosisIncidentSummary,
    IncidentDiagnosisDispatchConfig,
)
from .incident_diagnosis_dispatch_routes import (
    _classify_backend_listing_error,
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
        emit_autodiag_incident_list_failed_event(span_ctx, sanitized_error, resolved, error_type)

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


# =============================================================================
# Backend API Operations
# =============================================================================


def _list_incidents_backend_api(
    backend_url: str | None,
    internal_api_token: str | None,
    active_only: bool,
    limit: int | None,
) -> tuple[list[DiagnosisIncidentSummary], bool, str | None, str | None]:
    """List incidents from backend via internal API.

    Args:
        backend_url: Backend service URL
        internal_api_token: Internal API token
        active_only: If True, only return incidents in active status
        limit: Optional maximum number of incidents

    Returns:
        Tuple of (incidents, success, error_message, error_type)
        - error_type: Classified error type (unauthorized, timeout, etc.) or None
    """
    # Canonical internal API path for incident listing
    api_path = "/api/internal/incidents"

    if not backend_url or not internal_api_token:
        error_type = (
            BackendListingErrorType.MISSING_BACKEND_URL
            if not backend_url
            else BackendListingErrorType.MISSING_INTERNAL_TOKEN
        )
        error_msg = "Backend API configuration incomplete: missing backend_url or internal_api_token"
        _logger.error(
            error_msg,
            extra={
                "event": "backend-incident-listing-failed",
                "component": "automatic-diagnosis",
                "run_id": None,
                "mode": MODE_BACKEND_API,
                "backend_url_present": backend_url is not None,
                "internal_api_token_present": internal_api_token is not None,
                "path": api_path,
                "error_type": error_type,
                "sanitized_error": error_msg,
            },
        )
        return [], False, error_msg, error_type

    from ..ui.server_incident_internal_client import SchedulerClient

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    try:
        # Note: We fetch without status filter first, then filter active
        response = client.list_incidents(status=None, limit=limit)

        # Check for error in response
        if "error" in response:
            error_msg = str(response.get("error", "Unknown error"))
            status_code = response.get("status_code")

            # Determine error type - prefer explicit type from response, otherwise classify
            classified_error_type: str = response.get("error_type") or ""
            if not classified_error_type:
                if "401" in error_msg or "unauthorized" in error_msg.lower():
                    classified_error_type = BackendListingErrorType.UNAUTHORIZED
                elif "not found" in error_msg.lower():
                    classified_error_type = BackendListingErrorType.BAD_RESPONSE  # 404
                elif "timeout" in error_msg.lower():
                    classified_error_type = BackendListingErrorType.TIMEOUT
                else:
                    classified_error_type = BackendListingErrorType.UNKNOWN

            _logger.error(
                "Backend API incident listing failed",
                extra={
                    "event": "backend-incident-listing-failed",
                    "component": "automatic-diagnosis",
                    "run_id": None,
                    "mode": MODE_BACKEND_API,
                    "backend_url_present": True,
                    "internal_api_token_present": True,
                    "path": api_path,
                    "status_code": status_code,
                    "error_type": classified_error_type,
                    "sanitized_error": error_msg[:500],  # Truncate for log safety
                },
            )
            return [], False, error_msg, classified_error_type

        # Extract incidents from response
        raw_incidents = response.get("incidents", [])

        # Filter to active statuses if requested
        if active_only:
            raw_incidents = [
                inc for inc in raw_incidents
                if inc.get("status", "") in _ACTIVE_STATUS_NAMES
            ]

        # Apply limit after filtering
        if limit is not None and limit > 0:
            raw_incidents = raw_incidents[:limit]

        summaries = [
            DiagnosisIncidentSummary(
                incident_id=inc.get("incident_id", ""),
                status=inc.get("status", "unknown"),
            )
            for inc in raw_incidents
            if inc.get("incident_id")  # Skip entries without incident_id
        ]

        _logger.info(
            "Listed incidents from backend API",
            extra={
                "event": "diagnosis-incident-list-backend",
                "count": len(summaries),
                "active_only": active_only,
                "total_from_api": response.get("total", 0),
            },
        )

        return summaries, True, None, None

    except Exception as e:
        # Classify the error for structured event
        error_type, sanitized_error = _classify_backend_listing_error(e)

        # Determine status_code from exception if available
        status_code = None
        if hasattr(e, "code"):
            status_code = e.code
        elif hasattr(e, "status"):
            status_code = e.status

        _logger.error(
            "Backend API incident listing failed",
            extra={
                "event": "backend-incident-listing-failed",
                "component": "automatic-diagnosis",
                "run_id": None,
                "mode": MODE_BACKEND_API,
                "backend_url_present": True,
                "internal_api_token_present": True,
                "path": api_path,
                "status_code": status_code,
                "error_type": error_type,
                "sanitized_error": sanitized_error,
            },
        )
        # Return the classified error - caller will emit the failure event
        return [], False, sanitized_error, error_type


def _fetch_incident_backend_api(
    backend_url: str | None,
    internal_api_token: str | None,
    incident_id: str,
) -> tuple[Incident | None, bool, str | None]:
    """Fetch a single incident from backend API.

    Uses GET /api/internal/incidents/{incident_id} endpoint to fetch
    the full incident object from the backend SQLite store.

    Args:
        backend_url: Backend service URL
        internal_api_token: Internal API token
        incident_id: The incident ID to fetch

    Returns:
        Tuple of (incident, success, error_message)
        - incident: Incident object or None if not found
    """
    if not backend_url or not internal_api_token:
        error_msg = "Backend API configuration incomplete: missing backend_url or internal_api_token"
        _logger.error(
            error_msg,
            extra={
                "event": "diagnosis-incident-fetch-backend-config-incomplete",
                "backend_url": backend_url is not None,
                "internal_api_token": internal_api_token is not None,
            },
        )
        return None, False, error_msg

    from ..ui.server_incident_internal_client import SchedulerClient
    from .incident_lifecycle import Incident

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    try:
        # Fetch incident from backend via internal API
        incident_data = client.get_incident(incident_id)

        if incident_data is None:
            _logger.info(
                "Incident not found in backend",
                extra={
                    "event": "diagnosis-incident-fetch-backend-not-found",
                    "incident_id": incident_id,
                },
            )
            return None, True, None  # Not found is a success with None incident

        # Deserialize dict to Incident object
        incident = Incident.from_dict(incident_data)

        _logger.info(
            "Fetched incident from backend API",
            extra={
                "event": "diagnosis-incident-fetch-backend-success",
                "incident_id": incident_id,
                "status": incident.status.value,
            },
        )

        return incident, True, None

    except Exception as e:
        _logger.exception("Backend API incident fetch failed")
        return None, False, str(e)


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
