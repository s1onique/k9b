"""Backend health gate module.

This module provides the backend health gate functionality for provider smoke testing.
It polls /api/health with bounded retries and classifies failures.

Public API:
- run_health_gate: Main function to run the health gate
- HealthCheckResult: Dataclass for structured results
- Constants: FAILURE_BACKEND_HEALTH_*, FAILURE_DEP_*

Exit codes:
    0 - Backend health check passed (HTTP 200)
    1 - Backend health check failed (classified with failure artifact written)
"""

from .constants import (
    FAILURE_BACKEND_HEALTH_500,
    FAILURE_BACKEND_HEALTH_INVALID_RESPONSE,
    FAILURE_BACKEND_HEALTH_TIMEOUT,
    FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR,
    FAILURE_DEP_BACKEND_CRASHED,
    FAILURE_DEP_BACKEND_PENDING,
    FAILURE_DEP_BACKEND_RESTARTING,
    FAILURE_DEP_PROVIDER_CONNECTION_FAILED,
    FAILURE_DEP_PROVIDER_INIT_FAILED,
    FAILURE_DEP_PVC_MOUNT_ERROR,
    FAILURE_DEP_PVC_UNAVAILABLE,
    FAILURE_DEP_SCHEDULER_UNAVAILABLE,
    FAILURE_DEP_SCHEDULER_UNHEALTHY,
    FAILURE_DEP_UNKNOWN,
)
from .main import run_health_gate
from .types import HealthCheckResult

__all__ = [
    "run_health_gate",
    "HealthCheckResult",
    "FAILURE_BACKEND_HEALTH_500",
    "FAILURE_BACKEND_HEALTH_INVALID_RESPONSE",
    "FAILURE_BACKEND_HEALTH_TIMEOUT",
    "FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR",
    "FAILURE_DEP_BACKEND_CRASHED",
    "FAILURE_DEP_BACKEND_PENDING",
    "FAILURE_DEP_BACKEND_RESTARTING",
    "FAILURE_DEP_PROVIDER_CONNECTION_FAILED",
    "FAILURE_DEP_PROVIDER_INIT_FAILED",
    "FAILURE_DEP_PVC_MOUNT_ERROR",
    "FAILURE_DEP_PVC_UNAVAILABLE",
    "FAILURE_DEP_SCHEDULER_UNAVAILABLE",
    "FAILURE_DEP_SCHEDULER_UNHEALTHY",
    "FAILURE_DEP_UNKNOWN",
]
