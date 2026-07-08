"""SQLite event writer helpers for incident store.

This module provides low-level event appending functions used by lifecycle
operations. It handles the transaction mechanics for atomic event insertion
and projection updates.
"""

from __future__ import annotations

import logging
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

    Uses BEGIN IMMEDIATE to acquire a write lock immediately, preventing
    race conditions where concurrent readers get the same previous version
    before either writer commits.
    """
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    try:
        # Get previous version info for hash chain (inside transaction)
        cursor.execute(
            """
            SELECT aggregate_version, event_sha256
            FROM incident_events
            WHERE incident_id = ?
            ORDER BY aggregate_version DESC
            LIMIT 1
            """,
            (incident_id,),
        )
        row = cursor.fetchone()
        prev_version = row[0] if row else 0
        prev_sha256 = row[1] if row else None

        # Build event
        builder = EventBuilder(
            incident_id=incident_id,
            event_type=event_type,
            actor=actor,
            occurred_at=occurred_at,
            actor_id=actor_id,
            payload=payload,
        )
        builder.with_previous_version(prev_version, prev_sha256)
        event, _ = builder.build()

        # Insert event
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

        # Update event with seq
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

        # Update projection using canonical path (same transaction)
        from .incident_store_sqlite_queries import update_projection_for_event
        update_projection_for_event(conn, event)

        # Commit transaction
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    return event
