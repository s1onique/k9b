"""Incident diagnosis dispatch contracts.

This module contains:
- BackendListingErrorType: Error type classification for backend listing failures
- BackendIncidentShapeError: Shape validation error for incident fetch contract
- IncidentDiagnosisDispatchConfig: Configuration for incident diagnosis dispatcher
- DiagnosisIncidentSummary: Minimal incident summary for diagnosis loop
- parse_backend_incident_detail_payload: Parser for backend incident responses

These are pure data contracts with no implementation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .incident_lifecycle import Incident


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

# Required canonical fields for incident detail payload
# These must be present in the nested incident dict for Incident.from_dict() to succeed
_REQUIRED_CANONICAL_INCIDENT_FIELDS = frozenset({
    "incident_id",
    "source_candidate_id",
    "namespace",
    "object_kind",
    "object_name",
    "severity",
    "status",
    "first_observed_at",
    "last_observed_at",
})


# =============================================================================
# Error Classification
# =============================================================================


class BackendListingErrorType:
    """Error type classification for backend incident listing failures.

    These error types are emitted in structured events to enable
    targeted alerting and diagnostics.
    """

    MISSING_BACKEND_URL = "missing_backend_url"  # Backend URL not configured
    MISSING_INTERNAL_TOKEN = "missing_internal_token"  # Internal API token not configured
    UNAUTHORIZED = "unauthorized"  # 401/403 status codes
    TIMEOUT = "timeout"  # Request timed out
    BACKEND_UNREACHABLE = "backend_unreachable"  # Connection refused, DNS failed, etc.
    BAD_RESPONSE = "bad_response"  # Non-success HTTP status (other than 401/403)
    INVALID_JSON = "invalid_json"  # Response body is not valid JSON
    UNEXPECTED_SHAPE = "unexpected_shape"  # Response structure is unexpected
    UNKNOWN = "unknown"  # Everything else


class BackendIncidentShapeError(ValueError):
    """Shape validation error for backend incident fetch contract.

    This error is raised when the backend returns a response that does not
    conform to the expected canonical incident shape required by
    Incident.from_dict().

    Attributes:
        missing_field: The name of the missing field that caused the error, if any.
    """

    def __init__(self, message: str, *, missing_field: str | None = None) -> None:
        super().__init__(message)
        self.missing_field = missing_field


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
    "_REQUIRED_CANONICAL_INCIDENT_FIELDS",
    "BackendListingErrorType",
    "BackendIncidentShapeError",
    "IncidentDiagnosisDispatchConfig",
    "DiagnosisIncidentSummary",
    "parse_backend_incident_detail_payload",
]


# =============================================================================
# Scheduler-Side Contract Parser
# =============================================================================


def parse_backend_incident_detail_payload(data: object) -> Incident:
    """Parse and validate a backend incident detail response.

    This function validates that the backend response conforms to the expected
    canonical incident shape before calling Incident.from_dict(). It ensures
    that no KeyError can escape when parsing invalid responses.

    The parser accepts two response formats:
    1. Wrapped format (preferred):
       {
           "schema_version": "1",
           "payload_type": "incident-internal-detail",
           "incident": { canonical_incident_dict }
       }
    2. Raw canonical format (backwards compatibility):
       { canonical_incident_dict }

    The parser REJECTS:
    - List item summaries (missing first_observed_at, last_observed_at)
    - UI projections (using created_at/updated_at instead of first_observed_at/last_observed_at)
    - Any payload missing required canonical fields

    Args:
        data: Raw JSON response from backend

    Returns:
        Parsed Incident object

    Raises:
        BackendIncidentShapeError: If the response does not conform to the expected shape
    """
    from .incident_lifecycle import Incident

    if not isinstance(data, dict):
        raise BackendIncidentShapeError(
            "backend incident response is not a JSON object",
            missing_field=None,
        )

    # Extract incident data from wrapper or raw format
    if data.get("payload_type") == "incident-internal-detail":
        # Wrapped format: extract nested incident dict
        incident_data = data.get("incident")
    elif "incident" in data and isinstance(data["incident"], dict):
        # Legacy wrapped format (incident key present)
        incident_data = data["incident"]
    else:
        # Raw canonical format (backwards compatibility)
        incident_data = data

    if not isinstance(incident_data, dict):
        raise BackendIncidentShapeError(
            "backend incident response does not contain an incident object",
            missing_field=None,
        )

    # Validate class/candidate_class alias (Incident.from_dict accepts both)
    if "class" not in incident_data and "candidate_class" not in incident_data:
        raise BackendIncidentShapeError(
            "backend incident payload missing required field: class or candidate_class",
            missing_field="class",
        )

    # Validate required canonical fields
    for field in sorted(_REQUIRED_CANONICAL_INCIDENT_FIELDS):
        if field not in incident_data:
            raise BackendIncidentShapeError(
                f"backend incident payload missing required field: {field}",
                missing_field=field,
            )

    # Now safe to call Incident.from_dict() - no KeyError can escape
    return Incident.from_dict(incident_data)
