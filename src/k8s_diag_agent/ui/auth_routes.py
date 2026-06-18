"""Authentication routes: login, logout, and session check.

This module provides the HTTP handlers for authentication endpoints:
- POST /api/auth/login - Authenticate and create session
- POST /api/auth/logout - Invalidate session
- GET /api/auth/me - Check current session state
- GET /api/auth/status - Get authentication configuration status

These routes are intentionally public (no auth required) but they set
HttpOnly session cookies for subsequent authenticated requests.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .auth_config import get_auth_config
from .auth_provider import authenticate, get_auth_provider, get_principal_for_session
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


# =============================================================================
# Route: GET /api/auth/status
# =============================================================================


def handle_status(handler: HealthUIRequestHandler) -> None:
    """Handle auth status request.

    Returns the authentication configuration status, including:
    - Whether authentication is enabled
    - Whether password authentication is supported
    - Whether running in development mode

    This endpoint is intentionally public (used by frontend to determine
    whether to show login page).

    Args:
        handler: The HTTP request handler
    """
    config = get_auth_config()
    provider = get_auth_provider()

    send_json_response(
        handler,
        {
            "auth_enabled": config.enabled,
            "supports_password_auth": provider.supports_password_auth,
            "development_mode": config.is_development_mode,
        },
        200,
    )


# =============================================================================
# Route: POST /api/auth/login
# =============================================================================


def handle_login(handler: HealthUIRequestHandler) -> None:
    """Handle login request.

    Expects JSON body with 'username' and 'password' fields.
    On success, creates a session and sets an HttpOnly cookie.
    On failure, returns a generic error to avoid disclosing which field was wrong.

    Args:
        handler: The HTTP request handler
    """
    config = get_auth_config()

    # Parse request body
    try:
        content_length = int(handler.headers.get("Content-Length", "0"))
        if content_length <= 0:
            send_json_response(handler, {"error": "Request body required"}, 400)
            return

        raw_body = handler.rfile.read(content_length).decode("utf-8")
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        send_json_response(handler, {"error": "Invalid JSON payload"}, 400)
        return

    if not isinstance(body, dict):
        send_json_response(handler, {"error": "Invalid JSON payload"}, 400)
        return

    username = body.get("username", "")
    password = body.get("password", "")

    if not username or not password:
        send_json_response(handler, {"error": "Username and password required"}, 400)
        return

    # Attempt authentication
    principal = authenticate(username, password)

    if principal is None:
        # Generic error - do not disclose whether username or password was wrong
        send_json_response(handler, {"error": "Invalid credentials"}, 401)
        return

    # Authentication successful - create session
    provider = get_auth_provider()
    session = provider.create_session_for_principal(principal)

    # Set session cookie via extra_headers (proper header ordering)
    cookie_header = _build_session_cookie(session.session_id, config)

    # Return success response (no sensitive data)
    send_json_response(
        handler,
        {
            "authenticated": True,
            "user": {
                "principal_id": principal.principal_id,
                "display_name": principal.display_name,
                "auth_method": principal.auth_method,
            },
        },
        200,
        extra_headers={"Set-Cookie": cookie_header},
    )


# =============================================================================
# Route: POST /api/auth/logout
# =============================================================================


def handle_logout(handler: HealthUIRequestHandler) -> None:
    """Handle logout request.

    Reads session ID from cookie, invalidates the session, and clears the cookie.
    Always returns success even if no session exists (idempotent).

    Args:
        handler: The HTTP request handler
    """
    config = get_auth_config()
    cookie_name = config.session_cookie_name

    # Get session ID from cookie
    session_id = _get_session_cookie(handler, cookie_name)

    if session_id:
        # Invalidate the session
        provider = get_auth_provider()
        provider.invalidate_session(session_id)

    # Clear the session cookie via extra_headers (proper header ordering)
    clear_cookie_header = _build_clear_cookie(cookie_name, config)

    # Always return success (logout is idempotent)
    send_json_response(
        handler,
        {"authenticated": False},
        200,
        extra_headers={"Set-Cookie": clear_cookie_header},
    )


# =============================================================================
# Route: GET /api/auth/me
# =============================================================================


def handle_me(handler: HealthUIRequestHandler) -> None:
    """Handle session check request.

    Returns the current authentication state based on the session cookie.
    This endpoint is intentionally public (used by frontend to check auth state).

    Args:
        handler: The HTTP request handler
    """
    config = get_auth_config()
    cookie_name = config.session_cookie_name

    # Get session ID from cookie
    session_id = _get_session_cookie(handler, cookie_name)

    if not session_id:
        # No session cookie - not authenticated
        send_json_response(
            handler,
            {
                "authenticated": False,
                "user": None,
            },
            200,
        )
        return

    # Look up principal for session
    principal = get_principal_for_session(session_id)

    if principal is None:
        # Session expired or invalid - clear cookie and return not authenticated
        clear_cookie_header = _build_clear_cookie(cookie_name, config)
        send_json_response(
            handler,
            {
                "authenticated": False,
                "user": None,
            },
            200,
            extra_headers={"Set-Cookie": clear_cookie_header},
        )
        return

    # Valid session - return authenticated state
    # NOTE: Do NOT include password hash, session ID, or other secrets
    send_json_response(
        handler,
        {
            "authenticated": True,
            "user": {
                "principal_id": principal.principal_id,
                "display_name": principal.display_name,
                "auth_method": principal.auth_method,
            },
        },
        200,
    )


# =============================================================================
# Cookie helpers
# =============================================================================


def _get_session_cookie(handler: HealthUIRequestHandler, cookie_name: str) -> str | None:
    """Extract session ID from cookie.

    Args:
        handler: The HTTP request handler
        cookie_name: Name of the session cookie

    Returns:
        Session ID if found, None otherwise
    """
    cookie_header = handler.headers.get("Cookie", "")
    if not cookie_header:
        return None

    # Parse cookies (simple implementation)
    for cookie in cookie_header.split(";"):
        cookie = cookie.strip()
        if "=" in cookie:
            name, value = cookie.split("=", 1)
            if name == cookie_name:
                return value

    return None


def _build_session_cookie(
    session_id: str,
    config: Any,
) -> str:
    """Build the session cookie header value.

    Args:
        session_id: The session ID to set
        config: AuthConfig instance

    Returns:
        The full Set-Cookie header value
    """
    cookie_name = config.session_cookie_name
    max_age = config.session_max_age
    secure = config.secure_cookie

    # Build cookie header
    # HttpOnly: prevents JavaScript access (XSS protection)
    # SameSite=Lax: allows navigation from external sites but prevents CSRF on state-changing ops
    # Secure: only send over HTTPS (set in production)
    # Path=/: available for all paths
    # Max-Age: session expiry
    cookie_parts = [
        f"{cookie_name}={session_id}",
        "HttpOnly",
        "Path=/",
        f"Max-Age={max_age}",
        "SameSite=Lax",
    ]

    if secure:
        cookie_parts.append("Secure")

    return "; ".join(cookie_parts)


def _build_clear_cookie(cookie_name: str, config: Any) -> str:
    """Build the clear session cookie header value.

    Args:
        cookie_name: Name of the session cookie
        config: AuthConfig instance

    Returns:
        The full Set-Cookie header value for clearing the cookie
    """
    # Clear cookie by setting Max-Age=0 and expiring
    cookie_parts = [
        f"{cookie_name}=",
        "HttpOnly",
        "Path=/",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
    ]

    if config.secure_cookie:
        cookie_parts.append("Secure")

    return "; ".join(cookie_parts)


def _set_session_cookie(handler: HealthUIRequestHandler, session_id: str, config: Any) -> dict[str, str]:
    """Prepare the session cookie for setting on the response.

    This returns a dict to be passed as extra_headers to send_json_response.
    The cookie header is built but NOT sent directly - that happens via send_json_response.

    Args:
        handler: The HTTP request handler (unused but kept for API consistency)
        session_id: The session ID to set
        config: AuthConfig instance

    Returns:
        Dict with Set-Cookie header to be passed to send_json_response
    """
    cookie_value = _build_session_cookie(session_id, config)
    return {"Set-Cookie": cookie_value}
