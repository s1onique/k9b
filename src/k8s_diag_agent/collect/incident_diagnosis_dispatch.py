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

Error Classification:
Backend-listing failures are classified into specific error types for structured logging:
- unauthorized: 401/403 HTTP status codes
- timeout: Request timeout errors
- backend_unreachable: Connection refused/destination unreachable errors
- bad_response: Non-success HTTP status codes (other than 401/403)
- invalid_json: Response body is not valid JSON
- unknown: All other errors
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..ui.server_incident_internal_client import SchedulerClient
from .otel_events import (
    emit_autodiag_incident_list_failed_event,
    emit_autodiag_incident_list_start_event,
    emit_autodiag_incident_list_success_event,
)
from .otel_span_context import SpanContext

if TYPE_CHECKING:
    from .incident_store import Incident

_logger = logging.getLogger(__name__)

# Environment variables (same as promotion dispatch)
ENV_PROMOTION_MODE = "K9B_INCIDENT_PROMOTION_MODE"
ENV_BACKEND_URL = "K9B_BACKEND_INTERNAL_URL"
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Promotion modes (same as promotion dispatch)
MODE_LOCAL: Literal["local"] = "local"
MODE_BACKEND_API: Literal["backend-api"] = "backend-api"
MODE_AUTO: Literal["auto"] = "auto"

# Process roles
ROLE_BACKEND = "backend"
ROLE_SCHEDULER = "scheduler"

# Active statuses for diagnosis eligibility
_ACTIVE_STATUS_NAMES = frozenset({
    "open",
    "collecting_evidence",
    "investigating",
})


# Error type classification for backend listing failures
class BackendListingErrorType:
    """Error type classification for backend incident listing failures.

    These error types are emitted in structured events to enable
    targeted alerting and diagnostics.
    """

    UNAUTHORIZED = "unauthorized"  # 401/403 status codes
    TIMEOUT = "timeout"  # Request timed out
    BACKEND_UNREACHABLE = "backend_unreachable"  # Connection refused, DNS failed, etc.
    BAD_RESPONSE = "bad_response"  # Non-success HTTP status (other than 401/403)
    INVALID_JSON = "invalid_json"  # Response body is not valid JSON
    UNKNOWN = "unknown"  # Everything else


def _classify_backend_listing_error(exc: BaseException) -> tuple[str, str]:
    """Classify a backend listing error into a specific error type.

    This function analyzes the exception to determine the error category,
    enabling targeted alerting and diagnostics for different failure modes.

    Args:
        exc: The exception from the backend listing attempt

    Returns:
        Tuple of (error_type, error_message)
        - error_type: One of BackendListingErrorType values
        - error_message: Sanitized error message (truncated, no stack traces)
    """
    exc_str = str(exc)
    exc_type = type(exc).__name__
    exc_lower = exc_str.lower()

    # Check for HTTP errors with status codes
    if isinstance(exc, urllib.error.HTTPError):
        status_code = exc.code
        # 401 Unauthorized or 403 Forbidden
        if status_code in (401, 403):
            return BackendListingErrorType.UNAUTHORIZED, f"HTTP {status_code}: {exc_str[:200]}"
        # Other HTTP errors are bad responses
        return BackendListingErrorType.BAD_RESPONSE, f"HTTP {status_code}: {exc_str[:200]}"

    # Check for timeouts
    # socket.timeout is raised by urllib on timeout
    if isinstance(exc, socket.timeout):
        return BackendListingErrorType.TIMEOUT, "Request timed out"
    # Also check for TimeoutError and explicit timeout in message
    if exc_type == "TimeoutError" or "timeout" in exc_lower:
        return BackendListingErrorType.TIMEOUT, f"Timeout: {exc_str[:200]}"

    # Check for connection errors (backend unreachable)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if reason:
            reason_str = str(reason).lower()
            # Connection refused, DNS failed, network unreachable
            if any(
                keyword in reason_str
                for keyword in [
                    "connection refused",
                    "name or service not known",
                    "network is unreachable",
                    "no route to host",
                    "nodename nor servname",
                ]
            ):
                return (
                    BackendListingErrorType.BACKEND_UNREACHABLE,
                    f"Backend unreachable: {reason_str[:200]}",
                )
        return BackendListingErrorType.BACKEND_UNREACHABLE, f"URLError: {exc_str[:200]}"

    # Check for JSON decode errors
    if isinstance(exc, json.JSONDecodeError):
        return BackendListingErrorType.INVALID_JSON, f"Invalid JSON: {exc_str[:200]}"

    # Check for OS-level network errors
    if isinstance(exc, OSError) and any(
        keyword in exc_lower
        for keyword in [
            "connection refused",
            "network is unreachable",
            "no route to host",
            "name does not resolve",
            "temporary failure in name resolution",
        ]
    ):
        return BackendListingErrorType.BACKEND_UNREACHABLE, f"OS error: {exc_str[:200]}"

    # Default to unknown
    return BackendListingErrorType.UNKNOWN, f"{exc_type}: {exc_str[:200]}"


@dataclass(frozen=True)
class IncidentDiagnosisDispatchConfig:
    """Configuration for incident diagnosis dispatcher."""

    mode: Literal["local", "backend-api", "auto"]
    backend_url: str | None
    internal_api_token: str | None
    store_backend: str
    process_role: str

    def resolved_mode(self) -> Literal["local", "backend-api"]:
        """Resolve auto mode to concrete mode."""
        if self.mode == MODE_LOCAL:
            return MODE_LOCAL
        if self.mode == MODE_BACKEND_API:
            return MODE_BACKEND_API
        # Auto mode
        if self.store_backend == "sqlite":
            return MODE_BACKEND_API
        if self.process_role == ROLE_SCHEDULER:
            return MODE_BACKEND_API
        return MODE_LOCAL

    def requires_backend_api(self) -> bool:
        """Check if backend API is required for incident listing."""
        return self.resolved_mode() == MODE_BACKEND_API


def _get_dispatch_config() -> IncidentDiagnosisDispatchConfig:
    """Get the current dispatch configuration from environment."""
    return IncidentDiagnosisDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, MODE_AUTO).lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )


@dataclass(frozen=True)
class DiagnosisIncidentSummary:
    """Minimal incident summary for diagnosis loop."""

    incident_id: str
    status: str


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


def _list_incidents_local(
    active_only: bool,
    limit: int | None,
) -> tuple[list[DiagnosisIncidentSummary], bool, str | None]:
    """List incidents from local incident store.

    Args:
        active_only: If True, only return incidents in active status
        limit: Optional maximum number of incidents

    Returns:
        Tuple of (incidents, success, error_message)
    """
    try:
        from .incident_lifecycle import IncidentStatus
        from .incident_store_provider import get_incident_store

        store = get_incident_store()

        # Get ALL incidents first (no status filter)
        # We'll filter active status after to apply limit correctly
        all_incidents = list(store.list_incidents(status=None))

        # Filter to active statuses if requested
        if active_only:
            active_status_values = {s.value for s in [
                IncidentStatus.OPEN,
                IncidentStatus.COLLECTING_EVIDENCE,
                IncidentStatus.INVESTIGATING,
            ]}
            filtered_incidents = [
                inc for inc in all_incidents
                if inc.status.value in active_status_values
            ]
        else:
            filtered_incidents = all_incidents

        # Apply limit after filtering
        if limit is not None and limit > 0:
            filtered_incidents = filtered_incidents[:limit]

        # Convert to summary format
        summaries = [
            DiagnosisIncidentSummary(
                incident_id=inc.incident_id,
                status=inc.status.value,
            )
            for inc in filtered_incidents
        ]

        _logger.info(
            "Listed incidents from local store",
            extra={
                "event": "diagnosis-incident-list-local",
                "count": len(summaries),
                "active_only": active_only,
            },
        )

        return summaries, True, None

    except Exception as e:
        _logger.exception("Failed to list incidents from local store")
        return [], False, str(e)


def _fetch_incident_local(
    incident_id: str,
) -> tuple[Incident | None, bool, str | None]:
    """Fetch a single incident from local store.

    Args:
        incident_id: The incident ID to fetch

    Returns:
        Tuple of (incident, success, error_message)
    """
    try:
        from .incident_store_provider import get_incident_store

        store = get_incident_store()
        incident = store.get_incident(incident_id)
        return incident, True, None

    except Exception as e:
        _logger.exception("Failed to fetch incident from local store")
        return None, False, str(e)


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
    if not backend_url or not internal_api_token:
        error_msg = "Backend API configuration incomplete: missing backend_url or internal_api_token"
        _logger.error(
            error_msg,
            extra={
                "event": "diagnosis-incident-list-backend-config-incomplete",
                "backend_url": backend_url is not None,
                "internal_api_token": internal_api_token is not None,
            },
        )
        return [], False, error_msg, None

    client = SchedulerClient(base_url=backend_url, token=internal_api_token)

    try:
        # Note: We fetch without status filter first, then filter active
        # This ensures we don't get a false-zero when non-active incidents are at the front
        response = client.list_incidents(status=None, limit=limit)

        # Check for error in response
        if "error" in response:
            error_msg = str(response.get("error", "Unknown error"))
            _logger.error(
                "Backend API incident listing failed",
                extra={
                    "event": "diagnosis-incident-list-backend-error",
                    "error": error_msg,
                },
            )
            return [], False, error_msg, None

        # Extract incidents from response
        raw_incidents = response.get("incidents", [])

        # Filter to active statuses if requested
        if active_only:
            raw_incidents = [
                inc for inc in raw_incidents
                if inc.get("status", "") in _ACTIVE_STATUS_NAMES
            ]

        # Apply limit after filtering (in case limit was None or very large)
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
        _logger.exception("Backend API incident listing failed")
        # Classify the error for structured event
        error_type, sanitized_error = _classify_backend_listing_error(e)
        # Return the classified error - caller will emit the failure event
        return [], False, sanitized_error, error_type


def _classify_and_get_error_type(e: BaseException) -> tuple[str, str]:
    """Classify an exception and return (error_type, sanitized_message).

    This helper is used by the caller to emit structured failure events
    with error type classification.
    """
    return _classify_backend_listing_error(e)


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
        from .incident_lifecycle import Incident

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
