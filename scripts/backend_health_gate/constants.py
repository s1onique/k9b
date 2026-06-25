"""Constants for backend health gate."""

# Failure class constants
FAILURE_BACKEND_HEALTH_500 = "backend_health_500"
FAILURE_BACKEND_HEALTH_TIMEOUT = "backend_health_timeout"
FAILURE_BACKEND_HEALTH_INVALID_RESPONSE = "backend_health_invalid_response"
FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR = "backend_health_transport_error"

# Health dependency failure class constants
# These map to specific internal dependency failures for self-diagnosis
FAILURE_DEP_SCHEDULER_UNAVAILABLE = "dependency_scheduler_unavailable"
FAILURE_DEP_SCHEDULER_UNHEALTHY = "dependency_scheduler_unhealthy"
FAILURE_DEP_PVC_UNAVAILABLE = "dependency_pvc_unavailable"
FAILURE_DEP_PVC_MOUNT_ERROR = "dependency_pvc_mount_error"
FAILURE_DEP_BACKEND_RESTARTING = "dependency_backend_restarting"
FAILURE_DEP_BACKEND_CRASHED = "dependency_backend_crashed"
FAILURE_DEP_BACKEND_PENDING = "dependency_backend_pending"
FAILURE_DEP_PROVIDER_INIT_FAILED = "dependency_provider_init_failed"
FAILURE_DEP_PROVIDER_CONNECTION_FAILED = "dependency_provider_connection_failed"
FAILURE_DEP_UNKNOWN = "dependency_unknown"
