"""Authentication guard middleware for protecting API routes.

This module provides the central auth guard that protects sensitive routes.
All protected API routes should use require_auth() before processing.

Route classification:
- Public routes (no auth required):
  - /api/auth/login - Login endpoint
  - /api/auth/logout - Logout endpoint  
  - /api/auth/me - Session check endpoint
  - /health, /ready - Health/readiness endpoints
  - Static assets and SPA routes
  
- Protected routes (auth required):
  - /api/run/* - Run data
  - /api/fleet/* - Fleet data
  - /api/proposals/* - Proposals
  - /api/notifications/* - Notifications
  - /api/cluster-detail/* - Cluster details
  - /api/next-check-* - Next check operations
  - /api/runs/* - Runs list
  - /api/incidents/* - Incident data
  - /api/deterministic-next-check/* - Deterministic checks
  - /api/run-batch-* - Batch execution
  - /api/alertmanager-* - Alertmanager operations
  - /api/runtime-status - Runtime status
  - /api/debug/* - Debug endpoints
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Final

from .auth_config import get_auth_config
from .auth_provider import AuthenticatedPrincipal, get_principal_for_session

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)

# Route patterns for public/unauthenticated routes
_PUBLIC_API_PATTERNS: Final[list[re.Pattern[str]]] = [
    # Auth routes are always public (they SET the session)
    re.compile(r"^/api/auth/"),
    # Health/readiness endpoints (if they don't expose cluster data)
    re.compile(r"^/health$"),
    re.compile(r"^/ready$"),
    # Debug endpoints that only check diagnostics status
    re.compile(r"^/api/debug/diagnostics-enabled$"),
]

# Route prefixes that require authentication
_PROTECTED_API_PREFIXES: Final[tuple[str, ...]] = (
    "/api/run",
    "/api/fleet",
    "/api/proposals",
    "/api/notifications",
    "/api/cluster-detail",
    "/api/next-check",
    "/api/runs",
    "/api/incidents",
    "/api/deterministic-next-check",
    "/api/run-batch",
    "/api/alertmanager",
    "/api/runtime-status",
    "/api/vmalert",
    # Artifact serving requires auth (may expose sensitive data)
    "/artifact",
)


def is_public_route(route: str) -> bool:
    """Check if a route is public (no auth required).

    Args:
        route: The request path

    Returns:
        True if route is public, False if requires auth
    """
    # Check exact pattern matches first
    for pattern in _PUBLIC_API_PATTERNS:
        if pattern.match(route):
            return True

    # Check if route matches any protected prefix
    for prefix in _PROTECTED_API_PREFIXES:
        if route == prefix or route.startswith(prefix + "/"):
            return False

    # Static assets and SPA routes are always public
    if not route.startswith("/api/"):
        return True

    # All other API routes require authentication
    return False


def get_session_id_from_request(handler: HealthUIRequestHandler) -> str | None:
    """Extract session ID from the request cookie.

    Args:
        handler: The HTTP request handler

    Returns:
        Session ID if found in cookie, None otherwise
    """
    config = get_auth_config()
    cookie_name = config.session_cookie_name

    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None

    # Parse cookies
    for cookie in cookie_header.split(";"):
        cookie = cookie.strip()
        if "=" in cookie:
            name, value = cookie.split("=", 1)
            if name == cookie_name:
                return value

    return None


def require_auth(handler: HealthUIRequestHandler) -> AuthenticatedPrincipal | None:
    """Require authentication for a request.

    This is the central auth guard used by all protected routes.
    It extracts the session from the cookie and validates it.

    Args:
        handler: The HTTP request handler

    Returns:
        AuthenticatedPrincipal if authenticated, None otherwise.
        If None is returned, the handler has already sent a 401 response.
    """
    config = get_auth_config()

    # If auth is disabled (dev mode), return a dev principal
    if not config.enabled:
        return AuthenticatedPrincipal(
            principal_id="dev",
            display_name="Developer",
            auth_method="local-dev",
            roles=("admin",),
        )

    # Extract session ID from cookie
    session_id = get_session_id_from_request(handler)

    if not session_id:
        # No session - return 401
        from .server_response import send_json_response

        send_json_response(
            handler,
            {"error": "Authentication required"},
            401,
        )
        return None

    # Look up principal for session
    principal = get_principal_for_session(session_id)

    if principal is None:
        # Invalid or expired session - return 401
        from .server_response import send_json_response

        send_json_response(
            handler,
            {"error": "Session expired or invalid"},
            401,
        )
        return None

    return principal


def check_route_auth(handler: HealthUIRequestHandler) -> bool:
    """Check if the current request route requires auth and validate it.

    This is called at the start of request handling to enforce auth
    on protected routes while allowing public routes through.

    Args:
        handler: The HTTP request handler

    Returns:
        True if request should proceed, False if rejected.
        If False, the handler has already sent an error response.
    """
    route = handler.path.partition("?")[0]

    # Public routes always pass
    if is_public_route(route):
        return True

    # For protected routes, require authentication
    principal = require_auth(handler)
    return principal is not None


# Decorator-style helper for explicit route protection
def with_auth(handler: HealthUIRequestHandler) -> AuthenticatedPrincipal | None:
    """Decorator-style helper that requires auth and returns the principal.

    Use this when you need to ensure auth and get the principal:

        principal = with_auth(handler)
        # or check if auth passed
        if principal is None:
            return  # Error already sent

    Args:
        handler: The HTTP request handler

    Returns:
        AuthenticatedPrincipal if authenticated, None if not authenticated
        (error response already sent if returning None)
    """
    return require_auth(handler)
