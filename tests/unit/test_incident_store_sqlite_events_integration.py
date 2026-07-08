"""Tests for SQLite incident store events - SQLite integration.

This module tests:
- parse_stored_event function
- event_to_dict function
- Integration with actual SQLite database
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    EventBuilder,
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
    event_to_dict,
    parse_stored_event,
    verify_hash_chain,
)


class TestParseStoredEvent(unittest.TestCase):
    """Tests for parse_stored_event function."""

    def test_parse_valid_row(self) -> None:
        """Valid database row parses correctly."""
        row = (
            1,  # event_seq
            "evt-123",  # event_id
            "inc-456",  # incident_id
            2,  # aggregate_version
            "incident.updated",  # event_type
            "2024-01-15T10:30:00+00:00",  # occurred_at
            "user",  # actor
            "user-789",  # actor_id
            '{"key": "value"}',  # payload_json
            "abc123",  # payload_sha256
            "prev-hash",  # previous_event_sha256
            "def456",  # event_sha256
            "2024-01-15T10:30:05+00:00",  # created_at
        )
        event = parse_stored_event(row)

        self.assertEqual(event.event_seq, 1)
        self.assertEqual(event.event_id, "evt-123")
        self.assertEqual(event.incident_id, "inc-456")
        self.assertEqual(event.aggregate_version, 2)
        self.assertEqual(event.event_type, "incident.updated")
        self.assertEqual(event.actor, "user")
        self.assertEqual(event.actor_id, "user-789")
        self.assertEqual(event.payload_json, '{"key": "value"}')
        self.assertEqual(event.payload_sha256, "abc123")
        self.assertEqual(event.previous_event_sha256, "prev-hash")
        self.assertEqual(event.event_sha256, "def456")


class TestEventToDict(unittest.TestCase):
    """Tests for event_to_dict function."""

    def setUp(self) -> None:
        self.test_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_event_to_dict_complete(self) -> None:
        """Complete event converts to dict correctly."""
        event = StoredEvent(
            event_id="evt-123",
            incident_id="inc-456",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id="sys-001",
            payload_json='{"key": "value"}',
            payload_sha256="abc123",
            previous_event_sha256="prev-hash",
            event_sha256="def456",
            created_at=self.test_time,
            event_seq=1,
        )

        result = event_to_dict(event)

        self.assertEqual(result["event_id"], "evt-123")
        self.assertEqual(result["incident_id"], "inc-456")
        self.assertEqual(result["aggregate_version"], 1)
        self.assertEqual(result["event_type"], "incident.opened")
        self.assertEqual(result["actor"], "system")
        self.assertEqual(result["actor_id"], "sys-001")
        self.assertEqual(result["payload"], {"key": "value"})
        self.assertEqual(result["previous_event_sha256"], "prev-hash")
        self.assertEqual(result["event_sha256"], "def456")
        self.assertEqual(result["event_seq"], 1)

    def test_event_to_dict_without_optional(self) -> None:
        """Event without optional fields converts correctly."""
        event = StoredEvent(
            event_id="evt-123",
            incident_id="inc-456",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_json="{}",
            payload_sha256="abc123",
            previous_event_sha256=None,
            event_sha256="def456",
            created_at=self.test_time,
            event_seq=None,
        )

        result = event_to_dict(event)

        self.assertNotIn("actor_id", result)
        self.assertNotIn("previous_event_sha256", result)


class TestIntegrationWithSQLite(unittest.TestCase):
    """Integration tests with actual SQLite database."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_incident_events.db"

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_roundtrip_through_sqlite(self) -> None:
        """Events can be stored and retrieved from SQLite."""
        # Create table
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE incident_events (
                event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                aggregate_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_id TEXT,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Build and store event
        test_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        builder = EventBuilder(
            incident_id="inc-sqlite-test",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=test_time,
            payload={"test": "data"},
        )
        event, _ = builder.build()

        conn.execute(
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
        conn.commit()

        # Retrieve and verify
        cursor = conn.execute("SELECT * FROM incident_events WHERE event_id = ?", (event.event_id,))
        row = cursor.fetchone()
        self.assertIsNotNone(row)

        retrieved_event = parse_stored_event(row)
        self.assertEqual(retrieved_event.event_id, event.event_id)
        self.assertEqual(retrieved_event.incident_id, event.incident_id)
        self.assertEqual(retrieved_event.event_sha256, event.event_sha256)

        # Verify hash chain with retrieved event
        self.assertTrue(verify_hash_chain([retrieved_event]))

        conn.close()

    def test_event_chain_persistence(self) -> None:
        """Event chain is correctly persisted and retrieved."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE incident_events (
                event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                aggregate_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_id TEXT,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                event_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        incident_id = "inc-chain-test"
        events: list[StoredEvent] = []

        # Create chain
        for i in range(3):
            event_time = datetime(2024, 1, 15, 10 + i, 0, 0, tzinfo=UTC)
            builder = EventBuilder(
                incident_id=incident_id,
                event_type=IncidentEventType.OPENED if i == 0 else IncidentEventType.UPDATED,
                actor=IncidentEventActor.SYSTEM if i == 0 else IncidentEventActor.USER,
                occurred_at=event_time,
                payload={"step": i + 1},
            )

            if events:
                prev = events[-1]
                builder.with_previous_version(prev.aggregate_version, prev.event_sha256)

            event, _ = builder.build()
            events.append(event)

            conn.execute(
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
        conn.commit()

        # Retrieve all events for incident
        cursor = conn.execute(
            "SELECT * FROM incident_events WHERE incident_id = ? ORDER BY aggregate_version",
            (incident_id,),
        )
        rows = cursor.fetchall()

        self.assertEqual(len(rows), 3)
        retrieved_events = [parse_stored_event(row) for row in rows]

        # Verify chain
        self.assertTrue(verify_hash_chain(retrieved_events))

        # Verify original events
        self.assertTrue(verify_hash_chain(events))
        self.assertTrue(verify_hash_chain(retrieved_events))

        conn.close()


if __name__ == "__main__":
    unittest.main()
