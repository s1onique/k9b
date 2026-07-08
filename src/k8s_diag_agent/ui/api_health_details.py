"""Backend health detail endpoint for self-diagnosis.

This endpoint provides a safe, bounded contract for diagnosing which internal
dependency caused an HTTP 500 response from /api/health.

The response is designed to be:
- Upload-safe: no secrets, no raw IPs, no provider URLs
- Bounded: fixed schema with allowlisted fields only
- Self-diagnosing: names the failed dependency and failure class

This endpoint is available even when /api/health returns HTTP 500.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Final, cast

from .protocols import JsonResponseSender

logger = logging.getLogger(__name__)


# Failure class constants for internal dependencies
# These map to specific internal health dependency failures
class HealthDependencyFailure:
    """Health dependency failure classes."""
    
    # Scheduler failures
    SCHEDULER_UNAVAILABLE = "dependency_scheduler_unavailable"
    SCHEDULER_UNHEALTHY = "dependency_scheduler_unhealthy"
    
    # Storage failures
    PVC_UNAVAILABLE = "dependency_pvc_unavailable"
    PVC_MOUNT_ERROR = "dependency_pvc_mount_error"
    
    # Backend lifecycle failures
    BACKEND_RESTARTING = "dependency_backend_restarting"
    BACKEND_CRASHED = "dependency_backend_crashed"
    BACKEND_PENDING = "dependency_backend_pending"
    
    # Provider failures
    PROVIDER_INIT_FAILED = "dependency_provider_init_failed"
    PROVIDER_CONNECTION_FAILED = "dependency_provider_connection_failed"
    
    # Runtime failures
    RUNTIME_ERROR = "dependency_runtime_error"
    RUNTIME_TIMEOUT = "dependency_runtime_timeout"
    
    # Backend health route failures (when /api/health returns 500)
    BACKEND_HEALTH_INTERNAL_ERROR = "backend_health_internal_error"
    
    # Unknown
    UNKNOWN = "dependency_unknown"


# Reason code constants - enum-only, no raw error strings
# These are safe to include in uploadable JSON
class HealthReasonCode:
    """Reason codes for health dependencies - enum-only, no raw error text."""
    
    # Runtime reasons
    RUNTIME_HEALTHY: Final[str] = "runtime_healthy"
    RUNTIME_ERROR_PRESENT: Final[str] = "runtime_error_present"
    RUNTIME_STATUS_UNAVAILABLE: Final[str] = "runtime_status_unavailable"
    
    # Provider reasons
    PROVIDER_AVAILABLE: Final[str] = "provider_available"
    PROVIDER_UNAVAILABLE: Final[str] = "provider_unavailable"
    PROVIDER_STATUS_UNAVAILABLE: Final[str] = "provider_status_unavailable"
    PROVIDER_CONNECTION_FAILED: Final[str] = "provider_connection_failed"
    PROVIDER_AUTH_FAILED: Final[str] = "provider_auth_failed"
    PROVIDER_TIMEOUT: Final[str] = "provider_timeout"
    PROVIDER_UNKNOWN_ERROR: Final[str] = "provider_unknown_error"
    
    # Backend health route reasons
    HEALTH_ROUTE_HEALTHY: Final[str] = "health_route_healthy"
    HEALTH_ROUTE_EXCEPTION: Final[str] = "health_route_exception"
    HEALTH_ROUTE_RETURNED_500: Final[str] = "health_route_returned_500"


# Shared evaluator state - tracks if /api/health route encountered an exception
# This is set by evaluate_backend_health() before calling /api/health handlers
_backend_health_evaluation: HealthEvaluation | None = None


@dataclass
class HealthEvaluation:
    """Result of backend health evaluation used by both /api/health and /api/health/details.
    
    This is the shared backend health evaluator result that ensures consistency
    between /api/health and /api/health/details responses.
    """
    healthy: bool
    primary_failure_class: str = ""
    dependencies: list[dict[str, object]] = field(default_factory=list)
    reason_code: str = ""
    phase: str = ""
    # Internal state tracking
    _route_exception: str | None = None
    _route_returned_500: bool = False
    
    def to_dict(self) -> dict[str, object]:
        """Convert to dict for JSON serialization."""
        return {
            "healthy": self.healthy,
            "primary_failure_class": self.primary_failure_class,
            "dependencies": self.dependencies,
            "reason_code": self.reason_code,
            "phase": self.phase,
        }


def set_backend_health_evaluation(evaluation: HealthEvaluation | None) -> None:
    """Set the shared backend health evaluation result.
    
    DEPRECATED: Routes now call safe_evaluate_backend_health() directly.
    This function is kept for backwards compatibility only.
    """
    global _backend_health_evaluation
    _backend_health_evaluation = evaluation


def get_backend_health_evaluation() -> HealthEvaluation | None:
    """Get the current backend health evaluation result.
    
    DEPRECATED: Routes now call safe_evaluate_backend_health() directly.
    This function is kept for backwards compatibility only.
    """
    global _backend_health_evaluation
    return _backend_health_evaluation


def clear_backend_health_evaluation() -> None:
    """Clear the backend health evaluation result.
    
    DEPRECATED: Routes now call safe_evaluate_backend_health() directly.
    This function is kept for backwards compatibility only.
    """
    global _backend_health_evaluation
    _backend_health_evaluation = None


def _unsafe_evaluate_backend_health() -> HealthEvaluation:
    """Internal evaluator that raises on exception. Use safe_evaluate_backend_health() instead."""
    dependencies = _build_health_dependencies()
    primary_failure = _classify_primary_failure(dependencies)
    
    # Determine overall health from dependencies
    healthy = all(d.get("status") in ("healthy", "available", "running") for d in dependencies)
    
    # Determine reason_code from primary failure
    reason_code = _get_reason_code_for_failure(primary_failure, dependencies)
    
    # Determine phase (which component failed)
    phase = _get_phase_for_failure(primary_failure, dependencies)
    
    return HealthEvaluation(
        healthy=healthy,
        primary_failure_class=primary_failure,
        dependencies=dependencies,
        reason_code=reason_code,
        phase=phase,
    )


def safe_evaluate_backend_health() -> HealthEvaluation:
    """Safe backend health evaluator that catches exceptions and returns sanitized result.
    
    This function evaluates the health of all backend dependencies and returns
    a sanitized HealthEvaluation with enum fields only. If any exception occurs
    during evaluation, it returns a HealthEvaluation with:
    - healthy: False
    - primary_failure_class: BACKEND_HEALTH_INTERNAL_ERROR
    - backend_health_route dependency with health_handler phase
    
    No raw URLs, IPs, tokens, or exception text are included.
    
    Returns:
        HealthEvaluation with sanitized fields
    """
    try:
        return _unsafe_evaluate_backend_health()
    except Exception:
        # Evaluator exception - return internal error result
        return HealthEvaluation(
            healthy=False,
            primary_failure_class=HealthDependencyFailure.BACKEND_HEALTH_INTERNAL_ERROR,
            dependencies=[{
                "dependency_name": "backend_health_route",
                "status": "unavailable",
                "phase": "health_handler",
                "failure_class": HealthDependencyFailure.BACKEND_HEALTH_INTERNAL_ERROR,
                "reason_code": HealthReasonCode.HEALTH_ROUTE_EXCEPTION,
                "message_snippet": "",
            }],
            reason_code=HealthReasonCode.HEALTH_ROUTE_EXCEPTION,
            phase="health_handler",
        )


# Backward compatibility alias
evaluate_backend_health = safe_evaluate_backend_health


def _get_reason_code_for_failure(primary_failure: str, dependencies: list[dict[str, object]]) -> str:
    """Get the reason code for the primary failure."""
    if not primary_failure:
        return HealthReasonCode.HEALTH_ROUTE_HEALTHY
    
    if primary_failure == HealthDependencyFailure.RUNTIME_ERROR:
        return HealthReasonCode.RUNTIME_ERROR_PRESENT
    elif primary_failure == HealthDependencyFailure.PROVIDER_INIT_FAILED:
        return HealthReasonCode.PROVIDER_UNAVAILABLE
    elif primary_failure == HealthDependencyFailure.PROVIDER_CONNECTION_FAILED:
        return HealthReasonCode.PROVIDER_CONNECTION_FAILED
    elif primary_failure == HealthDependencyFailure.SCHEDULER_UNAVAILABLE:
        return "scheduler_unavailable"
    elif primary_failure == HealthDependencyFailure.SCHEDULER_UNHEALTHY:
        return "scheduler_unhealthy"
    elif primary_failure == HealthDependencyFailure.BACKEND_CRASHED:
        return "backend_crashed"
    elif primary_failure == HealthDependencyFailure.BACKEND_PENDING:
        return "backend_pending"
    elif primary_failure == HealthDependencyFailure.BACKEND_RESTARTING:
        return "backend_restarting"
    elif primary_failure == HealthDependencyFailure.PVC_MOUNT_ERROR:
        return "pvc_mount_error"
    elif primary_failure == HealthDependencyFailure.BACKEND_HEALTH_INTERNAL_ERROR:
        return HealthReasonCode.HEALTH_ROUTE_EXCEPTION
    
    return "unknown"


def _get_phase_for_failure(primary_failure: str, dependencies: list[dict[str, object]]) -> str:
    """Get the phase (which component failed) for the primary failure."""
    if not primary_failure:
        return "healthy"
    
    # Find the dependency with the failure
    for dep in dependencies:
        if dep.get("failure_class") == primary_failure:
            phase: str = str(dep.get("phase", "unknown"))
            return phase
    
    # Map failure class to default phase
    if primary_failure == HealthDependencyFailure.RUNTIME_ERROR:
        return "health_loop"
    elif primary_failure == HealthDependencyFailure.PROVIDER_INIT_FAILED:
        return "provider_init"
    elif primary_failure == HealthDependencyFailure.PROVIDER_CONNECTION_FAILED:
        return "provider_connect"
    elif primary_failure == HealthDependencyFailure.SCHEDULER_UNAVAILABLE:
        return "scheduler"
    elif primary_failure == HealthDependencyFailure.SCHEDULER_UNHEALTHY:
        return "scheduler"
    elif primary_failure == HealthDependencyFailure.BACKEND_CRASHED:
        return "backend"
    elif primary_failure == HealthDependencyFailure.BACKEND_PENDING:
        return "backend"
    elif primary_failure == HealthDependencyFailure.BACKEND_RESTARTING:
        return "backend"
    elif primary_failure == HealthDependencyFailure.BACKEND_HEALTH_INTERNAL_ERROR:
        return "health_handler"
    
    return "unknown"


def _get_runtime_health_status() -> dict[str, object]:
    """Get the runtime health status from the health loop.
    
    Returns:
        dict with 'healthy' bool and optional 'error' string
    """
    # Import here to avoid circular imports
    try:
        from ..health.loop import get_last_health_result
        result = get_last_health_result()
        if result is None:
            return {"healthy": True, "error": None}
        return {"healthy": result.is_healthy, "error": result.error}
    except Exception:
        return {"healthy": True, "error": None}


def _get_provider_health_status() -> dict[str, object]:
    """Get the diagnosis provider health status.
    
    Returns:
        dict with 'available' bool, optional 'error' string, optional 'phase' string,
        and optional 'error_class' string with full reason code.
    """
    try:
        from ..external_analysis.provider import get_provider_status
        status = get_provider_status()
        return {
            "available": status.get("available", False),
            "error": status.get("error"),
            "phase": status.get("phase"),
            "error_class": status.get("error_class"),
        }
    except Exception:
        return {
            "available": False,
            "error": "provider_status_unavailable",
            "phase": "status_probe_failed",
            "error_class": HealthReasonCode.PROVIDER_STATUS_UNAVAILABLE,
        }


def _build_health_dependencies() -> list[dict[str, object]]:
    """Build the health dependencies list.
    
    This function checks internal health dependencies and returns a safe,
    sanitized list of dependency statuses.
    
    Returns:
        List of dependency status dicts with bounded fields only.
        reason_code is enum-only - no raw error strings.
    """
    dependencies: list[dict[str, object]] = []
    
    # Check runtime health
    runtime_status = _get_runtime_health_status()
    runtime_reason_code = (
        HealthReasonCode.RUNTIME_HEALTHY
        if runtime_status["healthy"]
        else HealthReasonCode.RUNTIME_ERROR_PRESENT
    )
    runtime_dep: dict[str, object] = {
        "dependency_name": "health_loop_runtime",
        "status": "healthy" if runtime_status["healthy"] else "unhealthy",
        "failure_class": HealthDependencyFailure.RUNTIME_ERROR if runtime_status["error"] else "",
        "reason_code": runtime_reason_code,
        "message_snippet": "",  # Never include raw messages
    }
    dependencies.append(runtime_dep)
    
    # Check provider health
    provider_status = _get_provider_health_status()
    
    # Prefer error_class from provider probe, fall back to classification
    # error_class is the sanitized enum from the provider connectivity probe
    raw_error = provider_status.get("error")
    error_class = provider_status.get("error_class")
    
    # Use error_class if it's a valid enum value, otherwise classify the raw error
    # Validate against known provider reason codes
    valid_provider_codes = {
        HealthReasonCode.PROVIDER_AVAILABLE,
        HealthReasonCode.PROVIDER_UNAVAILABLE,
        HealthReasonCode.PROVIDER_STATUS_UNAVAILABLE,
        HealthReasonCode.PROVIDER_CONNECTION_FAILED,
        HealthReasonCode.PROVIDER_AUTH_FAILED,
        HealthReasonCode.PROVIDER_TIMEOUT,
        HealthReasonCode.PROVIDER_UNKNOWN_ERROR,
    }
    
    if error_class and error_class in valid_provider_codes:
        provider_reason_code = error_class
    elif error_class:
        # error_class exists but not in our enum - use unknown
        provider_reason_code = HealthReasonCode.PROVIDER_UNKNOWN_ERROR
    else:
        # No error_class - classify the raw error
        provider_reason_code = _classify_provider_reason_code(str(raw_error) if raw_error is not None else None)
    
    provider_dep: dict[str, object] = {
        "dependency_name": "diagnosis_provider",
        "status": "available" if provider_status["available"] else "unavailable",
        "phase": provider_status.get("phase") or "unknown",
        "failure_class": HealthDependencyFailure.PROVIDER_CONNECTION_FAILED if raw_error else "",
        "reason_code": provider_reason_code,
        "message_snippet": "",  # Never include raw messages
    }
    dependencies.append(provider_dep)
    
    return dependencies


def _classify_provider_reason_code(error: str | None) -> str:
    """Classify provider status into an enum reason code.
    
    Args:
        error: The error string from provider status (may be None)
        
    Returns:
        Enum reason code - never raw error text.
    """
    if error is None:
        return HealthReasonCode.PROVIDER_AVAILABLE
    
    # Normalize error to lowercase for classification
    error_lower = error.lower()
    
    # Classify based on error type - enum only, no raw strings
    if "timeout" in error_lower or "timed out" in error_lower:
        return HealthReasonCode.PROVIDER_TIMEOUT
    elif "auth" in error_lower or "401" in error_lower or "403" in error_lower:
        return HealthReasonCode.PROVIDER_AUTH_FAILED
    elif "connection" in error_lower or "refused" in error_lower or "unreachable" in error_lower:
        return HealthReasonCode.PROVIDER_CONNECTION_FAILED
    elif "unavailable" in error_lower or "not found" in error_lower:
        return HealthReasonCode.PROVIDER_UNAVAILABLE
    else:
        return HealthReasonCode.PROVIDER_UNKNOWN_ERROR


def _classify_primary_failure(dependencies: list[dict[str, object]]) -> str:
    """Classify the primary failure from dependency list.
    
    Args:
        dependencies: List of dependency status dicts
        
    Returns:
        The primary failure class or empty string if all healthy
    """
    for dep in dependencies:
        failure_class = dep.get("failure_class")
        if failure_class:
            return cast(str, failure_class)
    return ""


def handle_health_details(handler: JsonResponseSender) -> None:
    """Handle GET /api/health/details route.
    
    This endpoint provides a safe, bounded health dependency diagnosis
    even when /api/health returns HTTP 500.
    
    Response schema:
    {
        "timestamp": "ISO timestamp",
        "healthy": bool,
        "primary_failure_class": str,
        "dependency_count": int,
        "dependencies": [
            {
                "dependency_name": str,
                "status": str,
                "failure_class": str,
                "reason_code": str,
                "message_snippet": str,  # Always empty - no raw messages
            }
        ],
        "summary": {
            "dependencies_checked": int,
            "failures_detected": int,
        }
    }
    """
    from datetime import UTC, datetime
    
    # Always evaluate fresh - no stale cached state
    evaluation = safe_evaluate_backend_health()
    
    deps: list[dict[str, object]] = list(evaluation.dependencies)  # Copy to avoid mutation
    response: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "healthy": evaluation.healthy,
        "primary_failure_class": evaluation.primary_failure_class,
        "dependency_count": len(deps),
        "dependencies": deps,
        "summary": {
            "dependencies_checked": len(deps),
            "failures_detected": len([d for d in deps if d.get("failure_class")]),
        },
    }
    
    # Return consistent code: 200 if healthy, 503 if unhealthy
    handler._send_json(response, code=200 if evaluation.healthy else 503)
