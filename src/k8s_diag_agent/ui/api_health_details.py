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
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

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


def _get_runtime_health_status() -> dict:
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


def _get_provider_health_status() -> dict:
    """Get the diagnosis provider health status.
    
    Returns:
        dict with 'available' bool and optional 'error' string
    """
    try:
        from ..external_analysis.provider import get_provider_status
        status = get_provider_status()
        return {
            "available": status.get("available", False),
            "error": status.get("error"),
        }
    except Exception:
        return {"available": False, "error": "provider_status_unavailable"}


def _build_health_dependencies() -> list[dict]:
    """Build the health dependencies list.
    
    This function checks internal health dependencies and returns a safe,
    sanitized list of dependency statuses.
    
    Returns:
        List of dependency status dicts with bounded fields only.
        reason_code is enum-only - no raw error strings.
    """
    dependencies = []
    
    # Check runtime health
    runtime_status = _get_runtime_health_status()
    runtime_reason_code = (
        HealthReasonCode.RUNTIME_HEALTHY
        if runtime_status["healthy"]
        else HealthReasonCode.RUNTIME_ERROR_PRESENT
    )
    runtime_dep = {
        "dependency_name": "health_loop_runtime",
        "status": "healthy" if runtime_status["healthy"] else "unhealthy",
        "failure_class": HealthDependencyFailure.RUNTIME_ERROR if runtime_status["error"] else "",
        "reason_code": runtime_reason_code,
        "message_snippet": "",  # Never include raw messages
    }
    dependencies.append(runtime_dep)
    
    # Check provider health
    provider_status = _get_provider_health_status()
    provider_reason_code = _classify_provider_reason_code(provider_status["error"])
    provider_dep = {
        "dependency_name": "diagnosis_provider",
        "status": "available" if provider_status["available"] else "unavailable",
        "failure_class": HealthDependencyFailure.PROVIDER_CONNECTION_FAILED if provider_status["error"] else "",
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


def _classify_primary_failure(dependencies: list[dict]) -> str:
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


def handle_health_details(handler: HealthUIRequestHandler) -> None:
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
    
    dependencies = _build_health_dependencies()
    primary_failure = _classify_primary_failure(dependencies)
    
    # Determine overall health from dependencies
    healthy = all(d.get("status") in ("healthy", "available", "running") for d in dependencies)
    
    response = {
        "timestamp": datetime.now(UTC).isoformat(),
        "healthy": healthy,
        "primary_failure_class": primary_failure,
        "dependency_count": len(dependencies),
        "dependencies": dependencies,
        "summary": {
            "dependencies_checked": len(dependencies),
            "failures_detected": len([d for d in dependencies if d.get("failure_class")]),
        },
    }
    
    handler._send_json(response, code=200 if healthy else 503)
