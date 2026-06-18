"""Authentication configuration from environment variables.

This module handles parsing and validation of auth-related configuration,
with fail-closed behavior in production when required config is missing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

# Environment variable names
_ENV_ADMIN_USERNAME: Final[str] = "K9B_ADMIN_USERNAME"
_ENV_ADMIN_PASSWORD_HASH: Final[str] = "K9B_ADMIN_PASSWORD_HASH"
_ENV_SESSION_COOKIE_NAME: Final[str] = "K9B_SESSION_COOKIE_NAME"
_ENV_SESSION_MAX_AGE: Final[str] = "K9B_SESSION_MAX_AGE_SECONDS"
_ENV_SESSION_IDLE_TIMEOUT: Final[str] = "K9B_SESSION_IDLE_TIMEOUT_SECONDS"
_ENV_SECURE_COOKIE: Final[str] = "K9B_SECURE_COOKIE"
_ENV_AUTH_ENABLED: Final[str] = "K9B_AUTH_ENABLED"

# Default values
_DEFAULT_SESSION_COOKIE_NAME: Final[str] = "k9b_session"
_DEFAULT_SESSION_MAX_AGE: Final[int] = 8 * 60 * 60  # 8 hours
_DEFAULT_SESSION_IDLE_TIMEOUT: Final[int] = 30 * 60  # 30 minutes
_DEFAULT_ADMIN_USERNAME: Final[str] = "admin"

# Development warning banner
_DEV_MODE_WARNING: Final[str] = """
WARNING: Running with K9B_AUTH_ENABLED=false or missing auth config.
Authentication is disabled. This is INSECURE for production use.
Set K9B_AUTH_ENABLED=true and configure K9B_ADMIN_PASSWORD_HASH for production.
"""


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool
    """Whether authentication is enabled."""

    admin_username: str
    """Username for the admin account."""

    admin_password_hash: str | None
    """PBKDF2-HMAC-SHA256 hash of the admin password."""

    session_cookie_name: str
    """Name of the session cookie."""

    session_max_age: int
    """Maximum session age in seconds."""

    session_idle_timeout: int
    """Session idle timeout in seconds."""

    secure_cookie: bool
    """Whether to set Secure flag on session cookie."""

    is_development_mode: bool
    """Whether running in development mode (no auth)."""

    def validate(self) -> list[str]:
        """Validate the configuration and return list of warnings/errors.

        Returns:
            List of validation messages (empty if valid for current mode)
        """
        issues = []

        if self.enabled:
            if not self.admin_username:
                issues.append("K9B_ADMIN_USERNAME is required when auth is enabled")
            if not self.admin_password_hash:
                issues.append("K9B_ADMIN_PASSWORD_HASH is required when auth is enabled")
        else:
            issues.append(
                "Authentication is DISABLED. This is insecure for production."
            )

        return issues


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Args:
        value: The environment variable value
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _parse_int(value: str | None, default: int) -> int:
    """Parse an integer environment variable.

    Args:
        value: The environment variable value
        default: Default value if not set or invalid

    Returns:
        Parsed integer value
    """
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(
            "Invalid integer value %r for config, using default %d",
            value,
            default,
        )
        return default


def load_auth_config() -> AuthConfig:
    """Load authentication configuration from environment variables.

    This function implements fail-closed behavior:
    - If K9B_AUTH_ENABLED is explicitly true, auth is required
    - If K9B_AUTH_ENABLED is not set, defaults to enabled (safe default)
    - If K9B_AUTH_ENABLED is explicitly false, auth is disabled (dev only)

    Production mode (auth enabled):
    - Requires K9B_ADMIN_USERNAME and K9B_ADMIN_PASSWORD_HASH
    - Logs warning if no password hash is configured but auth is enabled

    Development mode (auth disabled):
    - Logs prominent warning
    - Allows operation without credentials

    Returns:
        AuthConfig instance with loaded configuration
    """
    # Check if auth is explicitly enabled/disabled
    auth_enabled_env = os.environ.get(_ENV_AUTH_ENABLED)
    auth_enabled = _parse_bool(auth_enabled_env, default=True)  # Default to enabled

    # Load admin credentials
    admin_username = os.environ.get(_ENV_ADMIN_USERNAME, _DEFAULT_ADMIN_USERNAME)
    admin_password_hash = os.environ.get(_ENV_ADMIN_PASSWORD_HASH)

    # Load session configuration
    session_cookie_name = os.environ.get(
        _ENV_SESSION_COOKIE_NAME, _DEFAULT_SESSION_COOKIE_NAME
    )
    session_max_age = _parse_int(
        os.environ.get(_ENV_SESSION_MAX_AGE), _DEFAULT_SESSION_MAX_AGE
    )
    session_idle_timeout = _parse_int(
        os.environ.get(_ENV_SESSION_IDLE_TIMEOUT), _DEFAULT_SESSION_IDLE_TIMEOUT
    )

    # Secure cookie defaults to False for local dev, should be True for HTTPS
    secure_cookie = _parse_bool(os.environ.get(_ENV_SECURE_COOKIE), default=False)

    # Determine if we're in development mode
    is_development_mode = False

    if auth_enabled:
        # Production mode
        if not admin_password_hash:
            logger.warning(
                "K9B_AUTH_ENABLED=true but no admin password configured. "
                "Set K9B_ADMIN_PASSWORD_HASH for secure authentication."
            )
    else:
        # Development mode - auth disabled
        is_development_mode = True
        logger.warning(_DEV_MODE_WARNING)

    return AuthConfig(
        enabled=auth_enabled,
        admin_username=admin_username,
        admin_password_hash=admin_password_hash,
        session_cookie_name=session_cookie_name,
        session_max_age=session_max_age,
        session_idle_timeout=session_idle_timeout,
        secure_cookie=secure_cookie,
        is_development_mode=is_development_mode,
    )


# Global config instance (loaded lazily)
_auth_config: AuthConfig | None = None


def get_auth_config() -> AuthConfig:
    """Get the global auth configuration instance.

    Returns:
        The AuthConfig instance (loaded from environment on first call)
    """
    global _auth_config
    if _auth_config is None:
        _auth_config = load_auth_config()
    return _auth_config


def reset_auth_config() -> None:
    """Reset the global auth config (for testing)."""
    global _auth_config
    _auth_config = None