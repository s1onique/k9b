"""Allowlists for backend health gate normalization."""

from __future__ import annotations

# Allowlisted fields for dependency entries from backend endpoint
ALLOWED_DEPENDENCY_KEYS = frozenset({
    "dependency_name",
    "status",
    "phase",
    "failure_class",
    "reason_code",
    "message_snippet",
})

# Allowlisted provider phase values (enum-only, no raw URLs/IPs/tokens)
ALLOWED_PROVIDER_PHASES = frozenset({
    # Success
    "success",
    "tcp_only",
    "tcp_connected",
    # OpenAI-compatible /models probe success
    "models_list_ok",
    # Connectivity failures
    "timeout",
    "dns_failed",
    "connection_refused",
    "connection_failed",
    "tcp_timeout",
    "tcp_refused",
    "tcp_error",
    # HTTP-level failures
    "http_auth_required",
    "http_not_found",
    "models_endpoint_not_found",
    "http_server_error",
    "http_rate_limited",
    # TLS failures
    "tls_failed",
    # Configuration/state failures
    "config_missing",
    "config_check_skipped",
    "not_initialized",
    "null_provider",
    "import_failed",
    "status_probe_failed",
    # Legacy/error phases
    "unknown",
    "N/A",
    # Health route phases
    "health_handler",
})

# Allowlisted failure class values
ALLOWED_FAILURE_CLASSES = frozenset({
    "dependency_scheduler_unavailable",
    "dependency_scheduler_unhealthy",
    "dependency_pvc_unavailable",
    "dependency_pvc_mount_error",
    "dependency_backend_restarting",
    "dependency_backend_crashed",
    "dependency_backend_pending",
    "dependency_provider_init_failed",
    "dependency_provider_connection_failed",
    "dependency_runtime_error",
    "dependency_runtime_timeout",
    "backend_health_internal_error",  # When /api/health route throws exception
    "dependency_unknown",
    "",  # Empty string for healthy dependencies
})

# Allowlisted reason code values (enum-only, no raw error strings)
ALLOWED_REASON_CODES = frozenset({
    # Runtime
    "runtime_healthy",
    "runtime_error_present",
    "runtime_status_unavailable",
    # Provider
    "provider_available",
    "provider_unavailable",
    "provider_status_unavailable",
    "provider_connection_failed",
    "provider_auth_failed",
    "provider_timeout",
    "provider_unknown_error",
    # K8s-state fallback - backend containers
    "container_waiting_crashloopbackoff",
    "container_waiting_error",
    "container_waiting_terminated",
    "container_waiting_containercreating",
    "container_creating",
    "container_running",
    "container_state_running",
    "container_state_waiting",
    "container_state_terminated",
    "container_state_unknown",
    # K8s-state fallback - scheduler containers
    "scheduler_checked",
    "scheduler_healthy",
    "scheduler_pods_not_found",
    "scheduler_waiting_crashloopbackoff",
    "scheduler_waiting_error",
    "scheduler_waiting_containercreating",
    "scheduler_waiting_terminated",
    "scheduler_waiting_unknown",
    "scheduler_phase_pending",
    "scheduler_phase_failed",
    "scheduler_terminated",
    "scheduler_running",
    # PVC
    "pvc_mount_pending",
    # Provider config
    "provider_config_checked",
    "provider_configured",
    "provider_disabled",
    "provider_enabled_no_secret",
    # Health route reason codes
    "health_route_healthy",
    "health_route_exception",
    "health_route_returned_500",
    # Generic
    "unknown",
})


def _normalize_reason_code(raw_reason: str | None, context: str = "unknown") -> str:
    """Normalize a raw reason string to an allowlisted reason code.
    
    Args:
        raw_reason: Raw reason string from Kubernetes container state
        context: One of "container", "scheduler", "provider"
        
    Returns:
        An allowlisted reason code from ALLOWED_REASON_CODES
    """
    if not raw_reason:
        return "unknown"
    
    reason_lower = raw_reason.lower()
    
    # CrashLoopBackOff -> specific enum
    if "crashloop" in reason_lower or "crashloopbackoff" in reason_lower:
        prefix = "scheduler" if context == "scheduler" else "container"
        return f"{prefix}_waiting_crashloopbackoff"
    
    # Error -> specific enum
    if reason_lower == "error":
        prefix = "scheduler" if context == "scheduler" else "container"
        return f"{prefix}_waiting_error"
    
    # ContainerCreating -> specific enum
    if "containercreating" in reason_lower:
        prefix = "scheduler" if context == "scheduler" else "container"
        return f"{prefix}_waiting_containercreating"
    
    # Terminated -> specific enum
    if "terminated" in reason_lower:
        prefix = "scheduler" if context == "scheduler" else "container"
        return f"{prefix}_waiting_terminated"
    
    # PVC mount issues
    if "pvc" in reason_lower or "mount" in reason_lower:
        return "pvc_mount_pending"
    
    # Generic waiting state
    if context == "scheduler":
        return "scheduler_waiting_unknown"
    
    return "container_state_waiting"


def _normalize_provider_phase(raw_phase: str | None) -> str:
    """Normalize a provider phase to an allowlisted enum value.
    
    This function prevents raw URLs, IPs, or tokens from leaking through
    the phase field which is used for connectivity diagnosis.
    
    Args:
        raw_phase: Raw phase string from provider status (may be None)
        
    Returns:
        An allowlisted phase from ALLOWED_PROVIDER_PHASES, or "unknown" if invalid
    """
    if raw_phase is None:
        return "unknown"
    
    if not isinstance(raw_phase, str):
        return "unknown"
    
    # Trim whitespace
    normalized = raw_phase.strip()
    
    # Check against allowlist
    if normalized in ALLOWED_PROVIDER_PHASES:
        return normalized
    
    # Unknown phase -> "unknown"
    return "unknown"
