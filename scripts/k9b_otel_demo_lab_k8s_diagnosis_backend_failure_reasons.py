"""Failure reason constants for OTel demo backend contract checks."""

from __future__ import annotations

# =============================================================================
# Backend Fetch Failure Reasons
# =============================================================================

# DNS resolution failures
FAILURE_BACKEND_DNS_RESOLUTION_FAILED = "backend_dns_resolution_failed"

# Endpoint readiness failures
FAILURE_BACKEND_ENDPOINT_NOT_READY = "backend_endpoint_not_ready"

# Incident fetch failures
FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR = "backend_incident_fetch_transport_error"
FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR = "backend_incident_fetch_http_error"
FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND = "backend_incident_fetch_not_found"
FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON = "backend_incident_fetch_invalid_json"
FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR = "backend_incident_fetch_contract_error"
FAILURE_BACKEND_INCIDENT_FETCH_FAILED = "backend_incident_fetch_failed"

# Budget exhaustion (generic fallback for compatibility)
FAILURE_BUDGET_EXHAUSTED = "budget_exhausted"

# =============================================================================
# Targeted Invocation Failure Reasons (P4c)
# =============================================================================

# Transport-level failures
FAILURE_TARGETED_INVOCATION_HTTP_ERROR = "targeted_automatic_diagnosis_invocation_http_error"
FAILURE_TARGETED_INVOCATION_INVALID_JSON = "targeted_automatic_diagnosis_invocation_invalid_json"
FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR = "targeted_automatic_diagnosis_invocation_transport_error"
FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY = "targeted_automatic_diagnosis_backend_empty_reply"

# Runtime state failures (not transport errors)
# Budget exhaustion / not eligible - distinct from transport/HTTP errors
FAILURE_TARGETED_LOOP_NOT_ELIGIBLE = "targeted_automatic_diagnosis_loop_not_eligible"

# Post-invocation failures
FAILURE_TARGETED_LOOP_NOT_COMPLETED = "targeted_automatic_diagnosis_loop_not_completed"
FAILURE_TARGETED_LOOP_NOT_STARTED = "targeted_automatic_diagnosis_loop_not_started"
FAILURE_TARGETED_NO_PASS_ARTIFACTS = "targeted_automatic_diagnosis_no_pass_artifacts"
FAILURE_TARGETED_REVIEW_PACKET_MISSING = "targeted_automatic_diagnosis_review_packet_missing"
FAILURE_TARGETED_INSUFFICIENT_PASSES = "targeted_automatic_diagnosis_insufficient_passes"
FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES = (
    "targeted_automatic_diagnosis_budget_exhausted_before_required_passes"
)
FAILURE_TARGETED_BUDGET_LIMIT_TOO_LOW = "targeted_automatic_diagnosis_budget_limit_too_low"
FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS = (
    "targeted_automatic_diagnosis_completed_without_observable_pass_artifacts"
)
FAILURE_TARGETED_TERMINAL_NO_CHECKS = "targeted_automatic_diagnosis_terminal_no_checks"

# =============================================================================
# Legacy / Compatibility
# =============================================================================

# Alias for FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY for callers that use the shorter name
FAILURE_BACKEND_EMPTY_REPLY = FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY

__all__ = [
    # Backend fetch
    "FAILURE_BACKEND_DNS_RESOLUTION_FAILED",
    "FAILURE_BACKEND_ENDPOINT_NOT_READY",
    "FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND",
    "FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON",
    "FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR",
    "FAILURE_BACKEND_INCIDENT_FETCH_FAILED",
    # Budget
    "FAILURE_BUDGET_EXHAUSTED",
    # Targeted invocation
    "FAILURE_TARGETED_INVOCATION_HTTP_ERROR",
    "FAILURE_TARGETED_INVOCATION_INVALID_JSON",
    "FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR",
    "FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY",
    "FAILURE_TARGETED_LOOP_NOT_ELIGIBLE",
    "FAILURE_TARGETED_LOOP_NOT_COMPLETED",
    "FAILURE_TARGETED_LOOP_NOT_STARTED",
    "FAILURE_TARGETED_NO_PASS_ARTIFACTS",
    "FAILURE_TARGETED_REVIEW_PACKET_MISSING",
    "FAILURE_TARGETED_INSUFFICIENT_PASSES",
    "FAILURE_TARGETED_BUDGET_EXHAUSTED_BEFORE_REQUIRED_PASSES",
    "FAILURE_TARGETED_BUDGET_LIMIT_TOO_LOW",
    "FAILURE_TARGETED_COMPLETED_WITHOUT_OBSERVABLE_PASS",
    "FAILURE_TARGETED_TERMINAL_NO_CHECKS",
    # Legacy alias
    "FAILURE_BACKEND_EMPTY_REPLY",
]
