"""Internal API token authentication.

Handles bearer token validation for internal API endpoints.

Security model:
- When K9B_INCIDENT_STORE_BACKEND=sqlite (production mode), token is REQUIRED
- Missing token in production mode returns 401 (fail-closed)
- Missing token in non-production mode logs warning and allows request (dev mode)
- Uses hmac.compare_digest() per Python docs for timing-attack resistance
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Internal API token environment variable
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_BACKEND_MODE = "K9B_INCIDENT_STORE_BACKEND"


def _get_internal_api_token() -> str | None:
    """Get the internal API token from environment.

    Returns:
        The token string, or None if not configured
    """
    return os.environ.get(ENV_INTERNAL_API_TOKEN)


def _is_sqlite_backend_mode() -> bool:
    """Check if running in SQLite backend mode (production).

    Returns:
        True if K9B_INCIDENT_STORE_BACKEND=sqlite, False otherwise
    """
    return os.environ.get(ENV_BACKEND_MODE, "").lower() == "sqlite"


def _validate_internal_token(handler: HealthUIRequestHandler) -> bool:
    """Validate the bearer token for internal API requests.

    Args:
        handler: HTTP request handler

    Returns:
        True if token is valid and present, False otherwise

    Security policy:
        - SQLite backend mode (production): REQUIRES valid token (fail-closed)
        - Other modes (dev/test): Warning logged if token missing but allows request
    """
    token = _get_internal_api_token()

    # Extract bearer token from Authorization header
    auth_header = handler.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        _logger.warning(
            "Missing or invalid Authorization header for internal API",
            extra={"event": "internal-api-auth-failed", "reason": "missing_bearer"},
        )
        return False

    provided_token = auth_header[7:]  # Strip "Bearer "

    # If no token configured in production mode, fail-closed
    if not token:
        if _is_sqlite_backend_mode():
            _logger.error(
                "Internal API token not configured in SQLite/backend mode - rejecting request",
                extra={"event": "internal-api-auth-blocked", "reason": "no_token_in_production"},
            )
            return False
        else:
            # Dev/test mode: warn but allow
            _logger.warning(
                "Internal API token not configured - allowing request (dev/test mode)",
                extra={"event": "internal-api-auth-warning", "reason": "no_token_in_dev_mode"},
            )
            return True

    # Use hmac.compare_digest() for timing-attack resistant comparison
    # Python docs recommend this for externally supplied digest/token comparisons
    if not hmac.compare_digest(token, provided_token):
        _logger.warning(
            "Invalid token provided for internal API",
            extra={"event": "internal-api-auth-failed", "reason": "invalid_token"},
        )
        return False

    return True


def validate_token_for_production() -> bool:
    """Validate that internal API can function in production mode.

    Call this at startup to fail-fast if token is missing.

    Returns:
        True if token is configured, False otherwise
    """
    if _is_sqlite_backend_mode() and not _get_internal_api_token():
        _logger.error(
            "K9B_INTERNAL_API_TOKEN must be set when K9B_INCIDENT_STORE_BACKEND=sqlite",
            extra={"event": "startup-failed", "reason": "missing_internal_api_token"},
        )
        return False
    return True
