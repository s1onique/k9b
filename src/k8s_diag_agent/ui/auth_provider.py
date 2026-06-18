"""Authentication provider interface and local admin implementation.

This module defines the AuthProvider protocol/interface that abstracts
authentication backends, with a LocalAdminAuthProvider implementation
for single-admin session-based authentication.

The interface is designed to allow future replacement with Keycloak/OIDC
without changes to route protection or session handling code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .auth_config import get_auth_config
from .auth_password import verify_password
from .auth_session import Session, create_session, delete_session, get_session

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Principal / Identity types
# =============================================================================


@dataclass
class AuthenticatedPrincipal:
    """Represents an authenticated user/principal."""

    principal_id: str
    """Unique identifier for the principal (e.g., username, user ID)."""

    display_name: str
    """Human-readable name for display in UI."""

    auth_method: str
    """Authentication method used (e.g., 'local', 'oidc', 'saml')."""

    roles: tuple[str, ...]
    """Roles/permissions granted to this principal."""

    @property
    def is_admin(self) -> bool:
        """Check if principal has admin role."""
        return "admin" in self.roles


# =============================================================================
# AuthProvider Protocol
# =============================================================================


class AuthProvider(Protocol):
    """Protocol defining the authentication provider interface.

    This protocol allows different authentication backends (local admin,
    Keycloak/OIDC, LDAP, etc.) to be plugged in without changing the
    rest of the authentication system.

    Implementations must be thread-safe.
    """

    def authenticate(self, username: str, password: str) -> AuthenticatedPrincipal | None:
        """Authenticate a user with username and password.

        Args:
            username: The username to authenticate
            password: The password to verify

        Returns:
            AuthenticatedPrincipal if authentication succeeds, None otherwise
        """
        ...

    def get_principal_for_session(self, session_id: str) -> AuthenticatedPrincipal | None:
        """Get the principal associated with a session.

        Args:
            session_id: The session ID to look up

        Returns:
            AuthenticatedPrincipal if session is valid, None otherwise
        """
        ...

    def create_session_for_principal(self, principal: AuthenticatedPrincipal) -> Session:
        """Create a new session for an authenticated principal.

        Args:
            principal: The authenticated principal

        Returns:
            New Session instance
        """
        ...

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session (logout).

        Args:
            session_id: The session ID to invalidate

        Returns:
            True if session was found and invalidated
        """
        ...

    @property
    def is_enabled(self) -> bool:
        """Whether authentication is enabled."""
        ...

    @property
    def supports_password_auth(self) -> bool:
        """Whether this provider supports password authentication."""
        ...


# =============================================================================
# Local Admin Auth Provider
# =============================================================================


class LocalAdminAuthProvider:
    """Local single-admin authentication provider.

    This provider authenticates against a single admin account configured
    via environment variables. It's suitable for small deployments or
    development environments.

    Future migration to Keycloak/OIDC:
    - Replace this provider with OIDCProvider that validates Keycloak tokens
    - Session layer can remain (app session after OIDC callback)
    - Or use gateway-auth headers from reverse proxy with OIDC
    - Route protection continues to use AuthenticatedPrincipal
    """

    def __init__(self) -> None:
        """Initialize the local admin auth provider."""
        self._config = get_auth_config()

    @property
    def is_enabled(self) -> bool:
        """Whether authentication is enabled."""
        return self._config.enabled

    @property
    def supports_password_auth(self) -> bool:
        """Whether this provider supports password authentication."""
        return True

    def authenticate(self, username: str, password: str) -> AuthenticatedPrincipal | None:
        """Authenticate against the local admin account.

        Args:
            username: The username to authenticate
            password: The password to verify

        Returns:
            AuthenticatedPrincipal if credentials are valid, None otherwise

        Note:
            Always returns a generic "Invalid credentials" error to avoid
            disclosing whether username or password was wrong.
        """
        if not self._config.enabled:
            # Auth disabled - allow access (development mode)
            return AuthenticatedPrincipal(
                principal_id="dev",
                display_name="Developer",
                auth_method="local-dev",
                roles=("admin",),
            )

        # Check username
        if username != self._config.admin_username:
            # Use constant-time comparison to prevent username enumeration
            import hmac
            hmac.compare_digest(username, self._config.admin_username)
            return None

        # Check password
        stored_hash = self._config.admin_password_hash
        if not stored_hash:
            # No hash configured
            return None

        if not verify_password(password, stored_hash):
            return None

        # Authentication successful
        return AuthenticatedPrincipal(
            principal_id=self._config.admin_username,
            display_name=self._config.admin_username,
            auth_method="local",
            roles=("admin",),
        )

    def get_principal_for_session(self, session_id: str) -> AuthenticatedPrincipal | None:
        """Get the principal associated with a session.

        Args:
            session_id: The session ID to look up

        Returns:
            AuthenticatedPrincipal if session is valid and not expired
        """
        if not self._config.enabled:
            # Auth disabled - return dev principal
            return AuthenticatedPrincipal(
                principal_id="dev",
                display_name="Developer",
                auth_method="local-dev",
                roles=("admin",),
            )

        session = get_session(session_id)
        if session is None:
            return None

        return AuthenticatedPrincipal(
            principal_id=session.principal_id,
            display_name=session.principal_id,
            auth_method="local",
            roles=("admin",),
        )

    def create_session_for_principal(self, principal: AuthenticatedPrincipal) -> Session:
        """Create a new session for an authenticated principal.

        Args:
            principal: The authenticated principal

        Returns:
            New Session instance
        """
        return create_session(principal.principal_id)

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session (logout).

        Args:
            session_id: The session ID to invalidate

        Returns:
            True if session was found and invalidated
        """
        return delete_session(session_id)


# =============================================================================
# Global provider instance
# =============================================================================

_auth_provider: AuthProvider | None = None


def get_auth_provider() -> AuthProvider:
    """Get the global auth provider instance.

    Returns:
        The LocalAdminAuthProvider instance
    """
    global _auth_provider
    if _auth_provider is None:
        _auth_provider = LocalAdminAuthProvider()
    return _auth_provider


def reset_auth_provider() -> None:
    """Reset the global auth provider (for testing)."""
    global _auth_provider
    _auth_provider = None


def authenticate(username: str, password: str) -> AuthenticatedPrincipal | None:
    """Convenience function to authenticate via the global provider.

    Args:
        username: The username to authenticate
        password: The password to verify

    Returns:
        AuthenticatedPrincipal if successful, None otherwise
    """
    return get_auth_provider().authenticate(username, password)


def get_principal_for_session(session_id: str) -> AuthenticatedPrincipal | None:
    """Convenience function to get principal for session via global provider.

    Args:
        session_id: The session ID to look up

    Returns:
        AuthenticatedPrincipal if session is valid
    """
    return get_auth_provider().get_principal_for_session(session_id)