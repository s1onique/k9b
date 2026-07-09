"""Scheduler client for internal API communication.

This module re-exports from server_incident_internal_fetch to maintain
backward compatibility for existing importers.

Usage:
    from k8s_diag_agent.ui.server_incident_internal_client import (
        SchedulerClient,
        create_scheduler_client,
        PromotionErrorReason,
        SchedulerBackendPromotionError,
    )
"""

from __future__ import annotations

# Re-export all public symbols from the split module
from .server_incident_internal_fetch import (
    SchedulerBackendPromotionError,
    SchedulerClient,
    create_scheduler_client,
)


# Error reason codes for structured error handling
# Kept here for backward compatibility with existing importers
class PromotionErrorReason:
    """Error reason codes for promotion failures."""

    BACKEND_NOT_CONFIGURED = "backend_not_configured"
    INVALID_TOKEN = "invalid_token"
    BACKEND_UNREACHABLE = "backend_unreachable"
    UNAUTHORIZED = "unauthorized"
    BAD_RESPONSE = "bad_response"
    TIMEOUT = "timeout"
    INVALID_JSON = "invalid_json"
    UNKNOWN = "unknown"


__all__ = [
    "SchedulerClient",
    "SchedulerBackendPromotionError",
    "create_scheduler_client",
    "PromotionErrorReason",
]
