"""Incident diagnosis dispatch contracts.

This module contains:
- BackendListingErrorType: Error type classification for backend listing failures
- IncidentDiagnosisDispatchConfig: Configuration for incident diagnosis dispatcher
- DiagnosisIncidentSummary: Minimal incident summary for diagnosis loop

These are pure data contracts with no implementation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass


# Environment variable names
ENV_PROMOTION_MODE = "K9B_INCIDENT_PROMOTION_MODE"
ENV_BACKEND_URL = "K9B_BACKEND_INTERNAL_URL"
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Promotion modes
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


# =============================================================================
# Error Classification
# =============================================================================


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


# =============================================================================
# Dispatch Configuration
# =============================================================================


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


# =============================================================================
# Incident Summary
# =============================================================================


@dataclass(frozen=True)
class DiagnosisIncidentSummary:
    """Minimal incident summary for diagnosis loop."""

    incident_id: str
    status: str


__all__ = [
    "ENV_PROMOTION_MODE",
    "ENV_BACKEND_URL",
    "ENV_INTERNAL_API_TOKEN",
    "ENV_STORE_BACKEND",
    "ENV_PROCESS_ROLE",
    "MODE_LOCAL",
    "MODE_BACKEND_API",
    "MODE_AUTO",
    "ROLE_BACKEND",
    "ROLE_SCHEDULER",
    "_ACTIVE_STATUS_NAMES",
    "BackendListingErrorType",
    "IncidentDiagnosisDispatchConfig",
    "DiagnosisIncidentSummary",
]
