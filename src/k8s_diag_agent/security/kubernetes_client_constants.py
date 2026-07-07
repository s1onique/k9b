"""Constants for Kubernetes client configuration.

These constants define default bounds and limits for Kubernetes API operations.
"""

# Default bounds for API operations
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_LIMIT = 200
DEFAULT_MAX_ITEMS = 500
DEFAULT_LOG_BYTES = 1024 * 1024  # 1 MiB
DEFAULT_LOG_TAIL_LINES = 500

__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_LOG_BYTES",
    "DEFAULT_LOG_TAIL_LINES",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_TIMEOUT_SECONDS",
]
