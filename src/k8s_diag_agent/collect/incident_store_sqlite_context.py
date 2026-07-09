"""SQLite write context capability for incident store.

This module provides narrow capability objects that encapsulate write authority
for the SQLite incident store. The design follows Rust/Haskell principles:

- SQLiteWriteContext: Owns write authority (event append + cache mutation)
- SQLiteReadContext: Owns read-only authority (no cache mutation, no writes)

The store is the only context creator. Lifecycle/state helpers receive context,
not raw connections.

Design invariants:
- Raw sqlite3.Connection does not escape outside store/context layer
- Cache mutation only through context methods
- Write context is valid only inside store-owned critical section
- Closed/expired contexts reject reuse

Usage:
    with store._write_context() as ctx:
        ctx.append_event(...)
        ctx.put_cached_incident(updated)
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import Incident
from .incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
)

if TYPE_CHECKING:
    import sqlite3

    from .incident_store_sqlite import SQLiteIncidentStore

_logger = __import__("logging").getLogger(__name__)


# =============================================================================
# Capability Errors
# =============================================================================


class ContextClosedError(RuntimeError):
    """Raised when a closed context is used."""

    pass


class ContextNotOpenError(RuntimeError):
    """Raised when a context is not yet open."""

    pass


# =============================================================================
# SQLiteWriteContext
# =============================================================================


class SQLiteWriteContext:
    """Write capability for SQLite incident store.

    This context owns:
    - Event append authority
    - Projection update authority
    - Incident-cache read/write authority
    - Snapshot helper access

    The context is created by SQLiteIncidentStore._write_context() and is
    only valid inside the critical section.

    Attributes:
        _conn: The SQLite connection (private, not exposed)
        _cache: Reference to the store's incident cache (private, not exposed)
        _closed: Whether the context has been closed
        _store: Reference to the creating store (for snapshot method)
    """

    __slots__ = ("_conn", "_cache", "_closed", "_store", "_append_event_impl")

    def __init__(
        self,
        conn: sqlite3.Connection,
        cache: dict[str, Incident],
        store: SQLiteIncidentStore,
    ) -> None:
        """Initialize write context (store-internal, not for direct use)."""
        self._conn = conn
        self._cache = cache
        self._closed = False
        self._store = store
        # Import implementation here to avoid circular imports at module level
        from .incident_store_sqlite_events_writer import append_event as _impl
        self._append_event_impl = _impl

    def _ensure_open(self) -> None:
        """Ensure the context is open and raise if not."""
        if self._closed:
            raise ContextClosedError(
                "SQLite write context is closed. "
                "The context is only valid inside the store's write_context() block."
            )

    # -------------------------------------------------------------------------
    # Event Authority
    # -------------------------------------------------------------------------

    def append_event(
        self,
        incident_id: str,
        event_type: IncidentEventType,
        actor: IncidentEventActor,
        payload: dict[str, Any],
        occurred_at: datetime,
        actor_id: str | None = None,
    ) -> StoredEvent:
        """Append an event to the incident events table atomically.

        This method owns the event append authority. It uses BEGIN IMMEDIATE
        to acquire a write lock immediately and updates the projection
        within the same transaction.

        Args:
            incident_id: The incident ID
            event_type: The type of event to append
            actor: Who triggered the event
            payload: Event payload dict
            occurred_at: When the event occurred
            actor_id: Optional actor identifier

        Returns:
            The stored event record

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        # Delegate to the event writer implementation
        return self._append_event_impl(
            store=self._store,
            conn=self._conn,
            incident_id=incident_id,
            event_type=event_type,
            actor=actor,
            payload=payload,
            occurred_at=occurred_at,
            actor_id=actor_id,
        )

    # -------------------------------------------------------------------------
    # Cache Authority
    # -------------------------------------------------------------------------

    def has_incident(self, incident_id: str) -> bool:
        """Check if an incident exists in the cache.

        Args:
            incident_id: The incident ID to check

        Returns:
            True if the incident exists in the cache

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        return incident_id in self._cache

    def get_cached_incident(self, incident_id: str) -> Incident | None:
        """Get an incident from the cache.

        Args:
            incident_id: The incident ID to retrieve

        Returns:
            The incident if found, None otherwise

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        return self._cache.get(incident_id)

    def put_cached_incident(self, incident: Incident) -> None:
        """Store an incident in the cache.

        Args:
            incident: The incident to store

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        self._cache[incident.incident_id] = incident

    def remove_cached_incident(self, incident_id: str) -> bool:
        """Remove an incident from the cache.

        Args:
            incident_id: The incident ID to remove

        Returns:
            True if the incident was removed, False if not found

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        if incident_id in self._cache:
            del self._cache[incident_id]
            return True
        return False

    # -------------------------------------------------------------------------
    # Snapshot Authority
    # -------------------------------------------------------------------------

    def snapshot_incident(self, incident: Incident) -> Incident:
        """Create a snapshot copy of an incident.

        This method delegates to the store's snapshot method to ensure
        consistent snapshot creation.

        Args:
            incident: The incident to snapshot

        Returns:
            A snapshot copy of the incident

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        return self._store._snapshot_incident(incident)

    # -------------------------------------------------------------------------
    # Context Lifetime
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the context, marking it as no longer usable.

        After calling close(), all methods on this context will raise
        ContextClosedError.
        """
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Return True if the context has been closed."""
        return self._closed


# =============================================================================
# SQLiteReadContext
# =============================================================================


class SQLiteReadContext:
    """Read-only capability for SQLite incident store.

    This context owns:
    - Read-only SQLite queries
    - No cache mutation authority
    - No write transaction methods

    For read-only operations, prefer using the store's public API which
    returns snapshot copies.
    """

    __slots__ = ("_conn", "_closed")

    def __init__(
        self,
        conn: sqlite3.Connection,
    ) -> None:
        """Initialize read context (store-internal, not for direct use)."""
        self._conn = conn
        self._closed = False

    def _ensure_open(self) -> None:
        """Ensure the context is open and raise if not."""
        if self._closed:
            raise ContextClosedError(
                "SQLite read context is closed. "
                "The context is only valid inside the store's read_context() block."
            )

    def execute_query(
        self,
        sql: str,
        params: tuple[Any, ...] | None = None,
    ) -> list[tuple[Any, ...]]:
        """Execute a read-only query.

        Args:
            sql: SQL query to execute
            params: Query parameters

        Returns:
            List of result rows

        Raises:
            ContextClosedError: If the context has been closed
        """
        self._ensure_open()
        cursor = self._conn.execute(sql, params or ())
        return list(cursor.fetchall())

    def close(self) -> None:
        """Close the context, marking it as no longer usable."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Return True if the context has been closed."""
        return self._closed


__all__ = [
    "SQLiteWriteContext",
    "SQLiteReadContext",
    "ContextClosedError",
    "ContextNotOpenError",
]
