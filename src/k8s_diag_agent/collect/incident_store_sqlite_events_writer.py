"""SQLite event writer helpers for incident store.

This module provides low-level event appending functions used by lifecycle
operations. It handles the transaction mechanics for atomic event insertion
and projection updates.

R4 task 7 contract (SQLite transaction truth):

* ``append_event`` opens its own ``BEGIN IMMEDIATE`` transaction and
  commits on success. Each call is an independent durable event --
  callers must NOT assume consecutive ``append_event`` calls share one
  transaction.
* ``append_events_atomic`` is the explicit batch boundary. All events
  passed to a single ``append_events_atomic`` call commit atomically
  with their projection updates. Use this when the contract requires
  multiple events to land together (e.g. ``OPENED`` +
  ``COLLECTING_EVIDENCE_STARTED`` for an incident with a bundle).
* Tests assert both the independent (per-call) and atomic (batch)
  semantics so the truth is observable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .incident_store_sqlite_events import (
    EventBuilder,
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
)

if TYPE_CHECKING:
    import sqlite3

    from .incident_store_sqlite import SQLiteIncidentStore

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventAppendSpec:
    """Specification for one event to be appended atomically.

    Used by :func:`append_events_atomic` so callers do not have to pack
    the per-event arguments into positional tuples. The dataclass is
    frozen because the spec is shared with projection-update logic that
    relies on the values not mutating mid-transaction.
    """

    incident_id: str
    event_type: IncidentEventType
    actor: IncidentEventActor
    payload: dict[str, Any]
    occurred_at: datetime
    actor_id: str | None = None


def _append_event_in_transaction(
    cursor: sqlite3.Cursor,
    spec: EventAppendSpec,
) -> StoredEvent:
    """Append a single event using an existing open transaction cursor.

    No ``BEGIN`` / ``COMMIT`` is performed here. The caller owns the
    transaction boundaries; the helper inserts the event row and updates
    the projection so callers can stack multiple events into one
    durable batch.
    """
    cursor.execute(
        """
        SELECT aggregate_version, event_sha256
        FROM incident_events
        WHERE incident_id = ?
        ORDER BY aggregate_version DESC
        LIMIT 1
        """,
        (spec.incident_id,),
    )
    row = cursor.fetchone()
    prev_version = row[0] if row else 0
    prev_sha256 = row[1] if row else None

    builder = EventBuilder(
        incident_id=spec.incident_id,
        event_type=spec.event_type,
        actor=spec.actor,
        occurred_at=spec.occurred_at,
        actor_id=spec.actor_id,
        payload=spec.payload,
    )
    builder.with_previous_version(prev_version, prev_sha256)
    event, _ = builder.build()

    cursor.execute(
        """
        INSERT INTO incident_events (
            event_id, incident_id, aggregate_version, event_type,
            occurred_at, actor, actor_id, payload_json, payload_sha256,
            previous_event_sha256, event_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.incident_id,
            event.aggregate_version,
            event.event_type,
            event.occurred_at.isoformat(),
            event.actor,
            event.actor_id,
            event.payload_json,
            event.payload_sha256,
            event.previous_event_sha256,
            event.event_sha256,
            event.created_at.isoformat(),
        ),
    )

    event = StoredEvent(
        event_seq=cursor.lastrowid,
        event_id=event.event_id,
        incident_id=event.incident_id,
        aggregate_version=event.aggregate_version,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        actor=event.actor,
        actor_id=event.actor_id,
        payload_json=event.payload_json,
        payload_sha256=event.payload_sha256,
        previous_event_sha256=event.previous_event_sha256,
        event_sha256=event.event_sha256,
        created_at=event.created_at,
    )

    from .incident_store_sqlite_queries import update_projection_for_event

    update_projection_for_event(cursor.connection, event)
    return event


def append_event(
    store: SQLiteIncidentStore,
    conn: sqlite3.Connection,
    incident_id: str,
    event_type: IncidentEventType,
    actor: IncidentEventActor,
    payload: dict[str, Any],
    occurred_at: datetime,
    actor_id: str | None = None,
) -> StoredEvent:
    """Append an event to the incident events table atomically.

    R4 task 7 contract: this call opens its own ``BEGIN IMMEDIATE``
    transaction and commits on success. Multiple ``append_event`` calls
    are NOT shared across one transaction -- they each have their own
    durability boundary. Use :func:`append_events_atomic` to commit
    several events together.

    Uses BEGIN IMMEDIATE to acquire a write lock immediately, preventing
    race conditions where concurrent readers get the same previous version
    before either writer commits.
    """
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    try:
        event = _append_event_in_transaction(
            cursor,
            EventAppendSpec(
                incident_id=incident_id,
                event_type=event_type,
                actor=actor,
                payload=payload,
                occurred_at=occurred_at,
                actor_id=actor_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return event


def append_events_atomic(
    conn: sqlite3.Connection,
    specs: tuple[EventAppendSpec, ...],
) -> list[StoredEvent]:
    """Append multiple events into one atomic transaction.

    R4 task 7 contract: every spec in ``specs`` is appended under a
    single ``BEGIN IMMEDIATE`` transaction with its projection updates.
    Either all events commit together or none do. The function is the
    explicit batch boundary for callers who need ``OPENED`` plus
    ``COLLECTING_EVIDENCE_STARTED`` (or any other paired state) to land
    in one durable transaction.

    Returns:
        The list of stored events in the order they were appended. The
        ``event_seq`` field on each returned event reflects the actual
        insertion order on the auto-increment primary key.
    """
    if not specs:
        return []
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        events: list[StoredEvent] = []
        for spec in specs:
            events.append(_append_event_in_transaction(cursor, spec))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return events
