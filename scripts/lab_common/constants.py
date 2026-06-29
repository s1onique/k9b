"""Common constants for k9b live-lab gates.

This module defines shared failure class constants used by both CNPG and OTel labs.
"""

from __future__ import annotations

# =============================================================================
# Backend prerequisite failure classes
# =============================================================================

FAILURE_BACKEND_NAMESPACE_MISSING = "backend_namespace_missing"
FAILURE_BACKEND_SERVICE_MISSING = "backend_service_missing"
FAILURE_BACKEND_DEPLOYMENT_MISSING = "backend_deployment_missing"
FAILURE_BACKEND_ROLLOUT_NOT_READY = "backend_rollout_not_ready"


# =============================================================================
# Backend health failure classes
# =============================================================================

FAILURE_BACKEND_HEALTH_FAILED = "backend_health_failed"
FAILURE_BACKEND_HEALTH_TIMEOUT = "backend_health_timeout"


# =============================================================================
# Provider preflight failure classes
# =============================================================================

FAILURE_PROVIDER_DISABLED_REQUIRED = "provider_disabled_required"
FAILURE_PROVIDER_UNAVAILABLE = "provider_unavailable"
FAILURE_PROVIDER_NOT_INITIALIZED = "provider_not_initialized"
FAILURE_PROVIDER_CONNECTION_FAILED = "provider_connection_failed"
FAILURE_PROVIDER_CONFIG_ERROR = "provider_config_error"


# =============================================================================
# Lab result failure classes
# =============================================================================

FAILURE_BASELINE_NOT_READY = "baseline_not_ready"
FAILURE_INJECTION_FAILED = "injection_failed"
FAILURE_INCIDENT_NOT_DETECTED = "incident_not_detected"
FAILURE_DIAGNOSIS_WRONG_COMPONENT = "diagnosis_wrong_component"
FAILURE_DIAGNOSIS_MISSING_EVIDENCE = "diagnosis_missing_evidence"
FAILURE_SYMPTOM_NOT_OBSERVED = "symptom_not_observed"
FAILURE_VERIFICATION_FAILED = "verification_failed"


# =============================================================================
# Default k9b backend configuration
# =============================================================================

DEFAULT_K9B_BACKEND_DEPLOYMENT = "k9b-backend"
DEFAULT_K9B_BACKEND_CONTAINER = "backend"
DEFAULT_K9B_BACKEND_PORT = 8080
DEFAULT_K9B_NAMESPACE = "k9b"
DEFAULT_K9B_BACKEND_SERVICE = "k9b-backend"


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    # Backend prerequisites
    "FAILURE_BACKEND_NAMESPACE_MISSING",
    "FAILURE_BACKEND_SERVICE_MISSING",
    "FAILURE_BACKEND_DEPLOYMENT_MISSING",
    "FAILURE_BACKEND_ROLLOUT_NOT_READY",
    # Backend health
    "FAILURE_BACKEND_HEALTH_FAILED",
    "FAILURE_BACKEND_HEALTH_TIMEOUT",
    # Provider preflight
    "FAILURE_PROVIDER_DISABLED_REQUIRED",
    "FAILURE_PROVIDER_UNAVAILABLE",
    "FAILURE_PROVIDER_NOT_INITIALIZED",
    "FAILURE_PROVIDER_CONNECTION_FAILED",
    "FAILURE_PROVIDER_CONFIG_ERROR",
    # Lab results
    "FAILURE_BASELINE_NOT_READY",
    "FAILURE_INJECTION_FAILED",
    "FAILURE_INCIDENT_NOT_DETECTED",
    "FAILURE_DIAGNOSIS_WRONG_COMPONENT",
    "FAILURE_DIAGNOSIS_MISSING_EVIDENCE",
    "FAILURE_SYMPTOM_NOT_OBSERVED",
    "FAILURE_VERIFICATION_FAILED",
    # Defaults
    "DEFAULT_K9B_BACKEND_DEPLOYMENT",
    "DEFAULT_K9B_BACKEND_CONTAINER",
    "DEFAULT_K9B_BACKEND_PORT",
    "DEFAULT_K9B_NAMESPACE",
    "DEFAULT_K9B_BACKEND_SERVICE",
]
