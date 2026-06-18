"""Server-side session management with in-memory store.

This module provides opaque session handling with secure random session IDs,
server-side storage, and expiry management.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Final

# Session ID length in bytes (256 bits of entropy)
_SESSION_ID_BYTES: Final[int] = 32

# Default session settings
_DEFAULT_SESSION_MAX_AGE_SECONDS: Final[int] = 8 * 60 * 60  # 8 hours
_DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS: Final[int] = 30 * 60  # 30 minutes


@dataclass
class Session:
    """Represents an authenticated session."""

    session_id: str
    """Opaque session identifier (cryptographically random)."""

    principal_id: str
    """Identifier for the authenticated principal (e.g., username)."""

    created_at: float
    """Unix timestamp when session was created."""

    last_accessed_at: float
    """Unix timestamp of last activity."""

    max_age: int
    """Maximum session age in seconds from creation."""

    idle_timeout: int
    """Idle timeout in seconds (session expires after this long without activity)."""

    @property
    def is_expired(self) -> bool:
        """Check if session has expired due to max age."""
        return time.time() > (self.created_at + self.max_age)

    @property
    def is_idle_expired(self) -> bool:
        """Check if session has expired due to inactivity."""
        return time.time() > (self.last_accessed_at + self.idle_timeout)

    def touch(self) -> None:
        """Update last accessed time to now."""
        self.last_accessed_at = time.time()


class SessionStore:
    """Thread-safe in-memory session store.

    This store holds sessions server-side with opaque IDs. Sessions expire
    based on either max age (absolute lifetime) or idle timeout (inactivity).
    """

    def __init__(
        self,
        max_age_seconds: int = _DEFAULT_SESSION_MAX_AGE_SECONDS,
        idle_timeout_seconds: int = _DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the session store.

        Args:
            max_age_seconds: Maximum session lifetime from creation (default: 8 hours)
            idle_timeout_seconds: Session idle timeout (default: 30 minutes)
        """
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._max_age = max_age_seconds
        self._idle_timeout = idle_timeout_seconds

    def create(self, principal_id: str) -> Session:
        """Create a new session for the given principal.

        Args:
            principal_id: The identifier for the authenticated user

        Returns:
            New Session instance with cryptographically random ID
        """
        session_id = secrets.token_urlsafe(_SESSION_ID_BYTES)
        now = time.time()

        session = Session(
            session_id=session_id,
            principal_id=principal_id,
            created_at=now,
            last_accessed_at=now,
            max_age=self._max_age,
            idle_timeout=self._idle_timeout,
        )

        with self._lock:
            self._sessions[session_id] = session

        return session

    def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID, updating last accessed time.

        Args:
            session_id: The session ID to look up

        Returns:
            Session if found and valid, None otherwise
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            # Check expiry
            if session.is_expired or session.is_idle_expired:
                del self._sessions[session_id]
                return None

            # Update last accessed time
            session.touch()
            return session

    def delete(self, session_id: str) -> bool:
        """Invalidate a session.

        Args:
            session_id: The session ID to invalidate

        Returns:
            True if session was found and deleted, False otherwise
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed
        """
        removed = 0

        with self._lock:
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if session.is_expired or session.is_idle_expired
            ]

            for sid in expired_ids:
                del self._sessions[sid]
                removed += 1

        return removed

    def count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)

    def clear(self) -> None:
        """Remove all sessions (used for testing)."""
        with self._lock:
            self._sessions.clear()


# Global session store instance (per-process)
_session_store: SessionStore | None = None
_session_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    """Get the global session store instance.

    Returns:
        The singleton SessionStore instance, configured from AuthConfig
    """
    global _session_store
    with _session_store_lock:
        if _session_store is None:
            # Import here to avoid circular imports
            from .auth_config import get_auth_config

            config = get_auth_config()
            _session_store = SessionStore(
                max_age_seconds=config.session_max_age,
                idle_timeout_seconds=config.session_idle_timeout,
            )
        return _session_store


def reset_session_store() -> None:
    """Reset the global session store (for testing)."""
    global _session_store
    with _session_store_lock:
        if _session_store is not None:
            _session_store.clear()
        _session_store = None


def create_session(principal_id: str) -> Session:
    """Create a new session for the given principal.

    Args:
        principal_id: The username/identifier for the authenticated user

    Returns:
        New Session instance
    """
    return get_session_store().create(principal_id)


def get_session(session_id: str) -> Session | None:
    """Retrieve a session by ID.

    Args:
        session_id: The session ID to look up

    Returns:
        Session if valid, None otherwise
    """
    return get_session_store().get(session_id)


def delete_session(session_id: str) -> bool:
    """Invalidate a session.

    Args:
        session_id: The session ID to invalidate

    Returns:
        True if session was found and deleted
    """
    return get_session_store().delete(session_id)