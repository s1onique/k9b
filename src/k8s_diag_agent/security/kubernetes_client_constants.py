"""Constants for Kubernetes client configuration.

These constants define default bounds and limits for Kubernetes API operations.
"""

# Default bounds for API operations
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_LIMIT = 200
DEFAULT_MAX_ITEMS = 500
DEFAULT_LOG_BYTES = 1024 * 1024  # 1 MiB
DEFAULT_LOG_TAIL_LINES = 500

# Bounds for cross-namespace pod collection (health loop)
# Active pods: exclude terminal phases (Succeeded, Failed) by default
DEFAULT_POD_PAGE_LIMIT = 200
DEFAULT_ACTIVE_PODS_MAX = 1000
# Failed/evicted pod sampling caps
DEFAULT_FAILED_PODS_SCANNED_MAX = 500
DEFAULT_FAILED_PODS_REPORTED_MAX = 50
DEFAULT_EVICTED_PODS_REPORTED_MAX = 20

__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_LOG_BYTES",
    "DEFAULT_LOG_TAIL_LINES",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_POD_PAGE_LIMIT",
    "DEFAULT_ACTIVE_PODS_MAX",
    "DEFAULT_FAILED_PODS_SCANNED_MAX",
    "DEFAULT_FAILED_PODS_REPORTED_MAX",
    "DEFAULT_EVICTED_PODS_REPORTED_MAX",
]
