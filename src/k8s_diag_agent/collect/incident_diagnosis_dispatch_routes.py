"""Incident diagnosis dispatch routes and local implementation.

This module contains:
- _get_dispatch_config(): Get the current dispatch configuration from environment
- _classify_backend_listing_error(): Classify a backend listing error into specific error type
- _list_incidents_local(): List incidents from local incident store
- _fetch_incident_local(): Fetch a single incident from local store
- list_incidents_for_diagnosis(): List incidents for the automatic diagnosis loop
- fetch_incident_for_diagnosis(): Fetch a single incident for processing

These functions handle the routing and local backend implementation.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
from typing import TYPE_CHECKING

from .incident_diagnosis_dispatch_contracts import (
    ENV_BACKEND_URL,
    ENV_INTERNAL_API_TOKEN,
    ENV_PROCESS_ROLE,
    ENV_PROMOTION_MODE,
    ENV_STORE_BACKEND,
    MODE_AUTO,
    BackendListingErrorType,
    DiagnosisIncidentSummary,
    IncidentDiagnosisDispatchConfig,
)

if TYPE_CHECKING:
    from .incident_store import Incident


_logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


def _get_dispatch_config() -> IncidentDiagnosisDispatchConfig:
    """Get the current dispatch configuration from environment."""
    return IncidentDiagnosisDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, MODE_AUTO).lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )


# =============================================================================
# Error Classification
# =============================================================================


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
    if isinstance(exc, socket.timeout):
        return BackendListingErrorType.TIMEOUT, "Request timed out"
    if exc_type == "TimeoutError" or "timeout" in exc_lower:
        return BackendListingErrorType.TIMEOUT, f"Timeout: {exc_str[:200]}"

    # Check for connection errors (backend unreachable)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if reason:
            reason_str = str(reason).lower()
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


# =============================================================================
# Local Store Operations
# =============================================================================


def _list_incidents_local(
    active_only: bool,
    limit: int | None,
    after_incident_id: str | None = None,
) -> tuple[list[DiagnosisIncidentSummary], bool, str | None]:
    """List incidents from local incident store with cursor-based pagination.

    Args:
        active_only: If True, only return incidents in active status
        limit: Optional maximum number of incidents
        after_incident_id: Resume after this incident ID (cursor-based pagination)

    Returns:
        Tuple of (incidents, success, error_message)
    """
    try:
        from .incident_lifecycle import IncidentStatus
        from .incident_store_provider import get_incident_store

        store = get_incident_store()

        # Get ALL incidents first (no status filter)
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

        # Apply cursor-based pagination (skip incidents before cursor)
        if after_incident_id is not None:
            # Find the position of the cursor incident
            cursor_idx = None
            for idx, inc in enumerate(filtered_incidents):
                if inc.incident_id == after_incident_id:
                    cursor_idx = idx
                    break
            if cursor_idx is not None:
                # Resume after the cursor incident
                filtered_incidents = filtered_incidents[cursor_idx + 1:]
            else:
                # Cursor incident not found (may have been resolved/deleted)
                # Start from beginning but log the issue
                _logger.warning(
                    "Scan cursor incident not found, restarting from beginning",
                    extra={
                        "event": "scan-cursor-restart",
                        "cursor_incident_id": after_incident_id,
                    },
                )

        # Apply limit after pagination
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
                "after_incident_id": after_incident_id,
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


__all__ = [
    "_get_dispatch_config",
    "_classify_backend_listing_error",
    "_list_incidents_local",
    "_fetch_incident_local",
]
