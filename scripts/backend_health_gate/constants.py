"""Constants for backend health gate."""

# Failure class constants
FAILURE_BACKEND_HEALTH_500 = "backend_health_500"
FAILURE_BACKEND_HEALTH_TIMEOUT = "backend_health_timeout"
FAILURE_BACKEND_HEALTH_INVALID_RESPONSE = "backend_health_invalid_response"
FAILURE_BACKEND_HEALTH_TRANSPORT_ERROR = "backend_health_transport_error"

# Prerequisite failure class constants (Phase 0 / early detection)
# These indicate the k9b backend namespace/service/deployment is missing
# before any HTTP health check is attempted.
FAILURE_BACKEND_NAMESPACE_MISSING = "backend_namespace_missing"
FAILURE_BACKEND_SERVICE_MISSING = "backend_service_missing"
FAILURE_BACKEND_DEPLOYMENT_MISSING = "backend_deployment_missing"
FAILURE_BACKEND_ROLLOUT_NOT_READY = "backend_rollout_not_ready"

# k9b backend service name constant (single source of truth)
K9B_BACKEND_SERVICE = "k9b-backend"

# k9b backend deployment and namespace constants (for prerequisites.py)
K9B_BACKEND_DEPLOYMENT = "k9b-backend"
K9B_BACKEND_PORT = 8080
K9B_NAMESPACE = "k9b"

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
