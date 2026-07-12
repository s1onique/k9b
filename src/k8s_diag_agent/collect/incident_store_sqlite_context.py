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

import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .incident_lifecycle import Incident
from .incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
)

if TYPE_CHECKING:
    import sqlite3

    from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
    from .incident_diagnosis_keyset_cursor import (
        DiagnosisPageLimit,
        IncidentDiagnosisCursor,
    )
    from .incident_store_sqlite import SQLiteIncidentStore
    from .incident_store_sqlite_events_writer import EventAppendSpec

import logging

_logger = logging.getLogger(__name__)


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
            raise ContextClosedError("SQLite write context is closed. The context is only valid inside the store's write_context() block.")

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

        R4 task 7 contract: each ``append_event`` call opens its own
        ``BEGIN IMMEDIATE`` transaction and commits on success. Two
        consecutive ``append_event`` calls are NOT one transaction.
        Use :meth:`append_events_atomic` for the multi-event batch
        boundary.

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

    def append_events_atomic(
        self,
        specs: tuple[EventAppendSpec, ...],
    ) -> list[StoredEvent]:
        """Append multiple events into one atomic transaction.

        R4 task 7 contract: callers requiring ``OPENED`` plus
        ``COLLECTING_EVIDENCE_STARTED`` (or any other paired state) to
        land in one durable transaction use this method. Either every
        spec commits together or none of them do.

        Args:
            specs: Iterable of :class:`EventAppendSpec` items. Pass a
                tuple / list to keep the input immutable.

        Returns:
            The list of stored events in input order. ``event_seq``
            reflects the actual insertion order on the auto-increment
            primary key.
        """
        self._ensure_open()
        from .incident_store_sqlite_events_writer import (
            EventAppendSpec,
        )
        from .incident_store_sqlite_events_writer import (
            append_events_atomic as _impl,
        )

        concrete_specs: tuple[EventAppendSpec, ...] = tuple(specs)
        if not all(isinstance(s, EventAppendSpec) for s in concrete_specs):
            raise TypeError(
                "append_events_atomic specs must be EventAppendSpec instances"
            )
        return _impl(self._conn, concrete_specs)

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
    # Projection Authority
    # -------------------------------------------------------------------------

    def rebuild_projection(self) -> int:
        """Rebuild the entire incident_current projection from events.

        This method rebuilds the projection cache from the append-only events
        table. It is only valid inside the store's _write_context() critical
        section where the write lock is held.

        Returns:
            Number of incidents rebuilt

        Raises:
            ContextClosedError: If the context has been closed
        """
        from .incident_store_sqlite_projection import rebuild_projection as _rebuild

        self._ensure_open()
        return _rebuild(self._conn)

    # -------------------------------------------------------------------------
    # Diagnosis-loop Lifecycle Authority (R3 canonical atomic operation)
    # -------------------------------------------------------------------------

    def apply_diagnosis_lifecycle_idempotently(
        self,
        *,
        transition: str,
        incident_id: str,
        run_id: str | None,
        collector_run_id: str,
        diagnosis_run_id: str | None,
        fingerprint: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically apply a diagnosis-loop lifecycle transition.

        R3 canonical path for the internal
        ``diagnosis-loop-transition`` endpoint. This method owns the
        full ``lookup → hash-chained event append → canonical
        projection update → idempotency record insert`` sequence in
        one ``BEGIN IMMEDIATE`` transaction, then commits and
        refreshes the in-memory cache from the canonical projector.

        Returns one of:

        * ``{"outcome": "applied", "idempotent_replay": False,
            "incident": Incident | None}``
        * ``{"outcome": "applied", "idempotent_replay": True}``
        * ``{"outcome": "replay_mismatch"}``
        * ``{"outcome": "incident_not_found"}``

        The caller is responsible for translating any raised
        exception into the ``persistence_failed`` outcome.

        Raises:
            ContextClosedError: If the context has been closed.
            ValueError: If ``transition`` is not one of
                ``started`` / ``failed`` / ``completed``.
            sqlite3.DatabaseError: On any SQL failure (the
                transaction is rolled back before the exception
                propagates).
        """
        self._ensure_open()
        from .incident_store_sqlite_events_writer import (
            EventAppendSpec,
            _append_event_in_transaction,
        )

        if transition not in _DIAGNOSIS_LIFECYCLE_EVENT_TYPE:
            raise ValueError(f"unsupported transition: {transition!r}")
        event_type = _DIAGNOSIS_LIFECYCLE_EVENT_TYPE[transition]

        event_payload = _build_diagnosis_lifecycle_payload(
            transition=transition,
            run_id=run_id,
            collector_run_id=collector_run_id,
            payload=payload,
        )

        cursor = self._conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            # 1. Idempotency lookup BEFORE applying the transition.
            existing_fp, _applied_at = _select_lifecycle_idempotency_row(
                cursor,
                incident_id=incident_id,
                transition=transition,
                collector_run_id=collector_run_id,
                diagnosis_run_id=diagnosis_run_id,
            )
            if existing_fp is not None:
                if existing_fp != fingerprint:
                    self._conn.rollback()
                    return {"outcome": "replay_mismatch"}
                # Commit the (empty) write transaction before refreshing
                # the cache so the local view matches the durable state
                # observed by any other process that runs against the
                # same database file.
                self._conn.commit()
                # R4-3: idempotent replay must heal this process's
                # in-memory cache so a stale local view cannot overrule
                # the canonical projection. ``BEGIN IMMEDIATE`` only
                # serializes writers across processes; it cannot make
                # ``self._cache`` authoritative. Refresh from the
                # projection row that the previous apply already
                # wrote so this process sees the same lifecycle state
                # as the durable record.
                self._refresh_cache_from_projection(incident_id)
                return {"outcome": "applied", "idempotent_replay": True}

            # 2. Confirm the incident exists in the canonical
            #    projection, NOT in the process-local cache.
            #
            #    R4-1 contract: ``self._cache`` is a per-process
            #    Python dict; it cannot prove absence across
            #    processes. A request landing on a store whose cache
            #    was loaded before another process promoted the
            #    incident would otherwise short-circuit to
            #    ``incident_not_found`` and leave the durable
            #    projection untouched, silently dropping the
            #    lifecycle request.
            #
            #    ``SELECT 1`` against ``incident_current`` runs in
            #    the same ``BEGIN IMMEDIATE`` transaction so the
            #    existence check observes the same write-time view
            #    as the event/projection/idempotency writes that
            #    follow.
            cursor.execute(
                """
                SELECT 1
                FROM incident_current
                WHERE incident_id = ?
                """,
                (incident_id,),
            )
            if cursor.fetchone() is None:
                self._conn.rollback()
                return {"outcome": "incident_not_found"}

            # 3. Append the canonical event with the hash chain.
            #    ``_append_event_in_transaction`` does NOT open its
            #    own ``BEGIN IMMEDIATE``; it reuses our cursor so
            #    the event insert + projection update commit
            #    atomically with the idempotency record below.
            _append_event_in_transaction(
                cursor,
                EventAppendSpec(
                    incident_id=incident_id,
                    event_type=event_type,
                    actor=IncidentEventActor.SYSTEM,
                    payload=event_payload,
                    occurred_at=occurred_at,
                ),
            )

            # 4. Insert the idempotency record. A fault here MUST
            #    roll back the event insert above. The helper is a
            #    module-level function so the rollback-on-idempotency
            #    failure test can patch it cleanly.
            _insert_lifecycle_idempotency_row(
                cursor,
                incident_id=incident_id,
                transition=transition,
                collector_run_id=collector_run_id,
                diagnosis_run_id=diagnosis_run_id,
                fingerprint=fingerprint,
                occurred_at=occurred_at,
            )

            # 5. Commit. After this point the event + projection +
            #    idempotency row are durable.
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except sqlite3.Error:
                pass
            raise

        # 6. Refresh the in-memory cache from the canonical
        #    projector row. The previous lifecycle write methods
        #    refreshed the cache directly, but the new canonical
        #    path lets the projector (the source of truth for the
        #    cache) own the update so the in-memory aggregate and
        #    the on-disk ``incident_current`` row cannot diverge.
        self._refresh_cache_from_projection(incident_id)

        return {
            "outcome": "applied",
            "idempotent_replay": False,
            "incident": self._cache.get(incident_id),
        }

    def _refresh_cache_from_projection(self, incident_id: str) -> None:
        """Reload the in-memory cache entry from ``incident_current``.

        Called after the canonical lifecycle apply commits so the
        cache reflects the projection row that the canonical event
        writer just updated. This keeps the cache authoritative
        without requiring the caller to manually rebuild the
        aggregate.

        Raises:
            ContextClosedError: If the context has been closed.
        """
        self._ensure_open()
        cursor = self._conn.execute(
            """
            SELECT current_state_json, last_event_seq
            FROM incident_current
            WHERE incident_id = ?
            """,
            (incident_id,),
        )
        row = cursor.fetchone()
        if row is None:
            # No projection row means the event writer did not
            # insert one (which would be a bug elsewhere). Leave
            # the cache untouched.
            return
        current_json = row[0]
        try:
            state = json.loads(current_json) if current_json else {}
        except (TypeError, ValueError):
            _logger.warning(
                "Failed to deserialize incident_current JSON for %s",
                incident_id,
            )
            return
        incident = self._store._state_to_incident(state)
        self._cache[incident_id] = incident

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
            raise ContextClosedError("SQLite read context is closed. The context is only valid inside the store's read_context() block.")

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

    def list_incidents_for_diagnosis_page(
        self,
        *,
        active_only: bool,
        limit: DiagnosisPageLimit,
        after_cursor: IncidentDiagnosisCursor | None,
    ) -> IncidentDiagnosisPage:
        """List incidents for diagnosis with keyset pagination using SQLite.

        This method executes the keyset pagination query directly against
        the SQLite connection, keeping all SQL within the persistence boundary.

        Args:
            active_only: If True, only return incidents in active status
            limit: Maximum number of incidents per page (DiagnosisPageLimit)
            after_cursor: Optional cursor to resume after

        Returns:
            IncidentDiagnosisPage with paginated results from SQLite
        """
        from .incident_diagnosis_dispatch_page import list_incidents_for_diagnosis_page_impl

        return list_incidents_for_diagnosis_page_impl(
            conn=self._conn,
            active_only=active_only,
            limit=limit,
            after=after_cursor,
        )

    def close(self) -> None:
        """Close the context, marking it as no longer usable."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Return True if the context has been closed."""
        return self._closed


# =============================================================================
# Canonical Lifecycle Idempotency Helpers
# =============================================================================


# Mapping from the diagnosis-loop-transition endpoint ``transition``
# string to the canonical event type used by the events writer. The
# mapping is intentionally module-level so the lookup is identical for
# in-memory and SQLite-backed stores.
_DIAGNOSIS_LIFECYCLE_EVENT_TYPE: dict[str, IncidentEventType] = {
    "started": IncidentEventType.DIAGNOSIS_LOOP_STARTED,
    "failed": IncidentEventType.DIAGNOSIS_LOOP_FAILED,
    "completed": IncidentEventType.DIAGNOSIS_LOOP_COMPLETED,
}


def _build_diagnosis_lifecycle_payload(
    *,
    transition: str,
    run_id: str | None,
    collector_run_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Project the diagnosis-loop request payload onto the canonical event payload.

    The shape mirrors the helpers in
    :mod:`incident_store_sqlite_lifecycle` so events appended through
    the lifecycle idempotency path are indistinguishable from events
    appended through the in-process lifecycle methods. That is what
    keeps the canonical projector
    (:func:`incident_store_sqlite_projection.apply_event_to_state`)
    working without an environment-specific branch.
    """
    if transition == "started":
        return {
            "run_id": run_id or "",
            "collector_run_id": collector_run_id or "",
        }
    if transition == "failed":
        return {
            "run_id": run_id or "",
            "collector_run_id": collector_run_id or "",
            "unavailable_reason": payload.get("unavailable_reason") or None,
        }
    if transition == "completed":
        return {
            "run_id": run_id or "",
            "collector_run_id": collector_run_id or "",
            "review_packet_name": (
                str(payload["review_packet_name"])
                if payload.get("review_packet_name") is not None
                else None
            ),
            "checks_requested": int(payload.get("checks_requested", 0) or 0),
            "checks_run": int(payload.get("checks_run", 0) or 0),
            "checks_rejected": int(payload.get("checks_rejected", 0) or 0),
            "decision": (
                str(payload["decision"])
                if payload.get("decision") is not None
                else None
            ),
        }
    raise ValueError(f"unsupported transition: {transition!r}")


def _select_lifecycle_idempotency_row(
    cursor: sqlite3.Cursor,
    *,
    incident_id: str,
    transition: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
) -> tuple[str | None, str | None]:
    """Return ``(fingerprint, applied_at)`` for the key, or ``(None, None)``.

    The lookup uses ``COALESCE(diagnosis_run_id, '') = ?`` so the
    comparison matches the unique index expression (see
    :data:`incident_store_sqlite_schema.CREATE_LIFECYCLE_IDEMPOTENCY_INDICES`).
    Without that, a row whose ``diagnosis_run_id`` is NULL would never
    be matched and the index would still treat NULL as distinct.
    """
    cursor.execute(
        """
        SELECT fingerprint, applied_at
        FROM lifecycle_idempotency
        WHERE incident_id = ?
          AND transition = ?
          AND collector_run_id = ?
          AND COALESCE(diagnosis_run_id, '') = ?
        """,
        (
            incident_id,
            transition,
            collector_run_id,
            diagnosis_run_id or "",
        ),
    )
    row = cursor.fetchone()
    if row is None:
        return (None, None)
    return (str(row[0]), str(row[1]))


def _insert_lifecycle_idempotency_row(
    cursor: sqlite3.Cursor,
    *,
    incident_id: str,
    transition: str,
    collector_run_id: str,
    diagnosis_run_id: str | None,
    fingerprint: str,
    occurred_at: datetime,
) -> None:
    """Insert one idempotency row inside an existing transaction cursor.

    No ``BEGIN`` / ``COMMIT`` is performed here. The caller owns the
    transaction. A unique-index conflict is surfaced as
    ``sqlite3.IntegrityError``; the caller catches it and translates
    it into the bounded ``replay_mismatch`` outcome when the
    fingerprint differs.

    This helper is a separate function (rather than inlined inside
    :meth:`SQLiteWriteContext.apply_diagnosis_lifecycle_idempotently`)
    so the rollback-on-idempotency-failure test can inject a fault
    here without monkey-patching the connection layer.
    """
    cursor.execute(
        """
        INSERT INTO lifecycle_idempotency (
            incident_id, transition, collector_run_id, diagnosis_run_id,
            fingerprint, occurred_at, applied_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            incident_id,
            transition,
            collector_run_id,
            diagnosis_run_id,
            fingerprint,
            occurred_at.isoformat(),
            datetime.now(UTC).isoformat(),
        ),
    )




__all__ = [
    "SQLiteWriteContext",
    "SQLiteReadContext",
    "ContextClosedError",
    "ContextNotOpenError",
    # apply_diagnosis_lifecycle_idempotently is a method on SQLiteWriteContext.
]
