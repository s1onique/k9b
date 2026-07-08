"""Tests for SQLite incident store events - StoredEvent and EventBuilder.

This module tests:
- StoredEvent dataclass creation
- EventBuilder.build() method for each event type
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    EventBuilder,
    IncidentEventActor,
    IncidentEventType,
    StoredEvent,
)


class TestStoredEvent(unittest.TestCase):
    """Tests for StoredEvent dataclass."""

    def test_stored_event_creation(self) -> None:
        """StoredEvent can be created with all required fields."""
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        event = StoredEvent(
            event_id="evt-123",
            incident_id="inc-456",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=now,
            actor="system",
            actor_id=None,
            payload_json="{}",
            payload_sha256="abc123",
            previous_event_sha256=None,
            event_sha256="def456",
            created_at=now,
        )

        self.assertEqual(event.event_id, "evt-123")
        self.assertEqual(event.incident_id, "inc-456")
        self.assertEqual(event.aggregate_version, 1)
        self.assertEqual(event.event_type, "incident.opened")
        self.assertEqual(event.occurred_at, now)
        self.assertEqual(event.actor, "system")
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.payload_json, "{}")
        self.assertEqual(event.payload_sha256, "abc123")
        self.assertIsNone(event.previous_event_sha256)
        self.assertEqual(event.event_sha256, "def456")
        self.assertEqual(event.created_at, now)
        self.assertIsNone(event.event_seq)

    def test_stored_event_with_optional_fields(self) -> None:
        """StoredEvent can be created with optional fields."""
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        event = StoredEvent(
            event_id="evt-123",
            incident_id="inc-456",
            aggregate_version=2,
            event_type="incident.updated",
            occurred_at=now,
            actor="user",
            actor_id="user-789",
            payload_json='{"key": "value"}',
            payload_sha256="abc123",
            previous_event_sha256="prev-hash",
            event_sha256="def456",
            created_at=now,
            event_seq=42,
        )

        self.assertEqual(event.actor, "user")
        self.assertEqual(event.actor_id, "user-789")
        self.assertEqual(event.previous_event_sha256, "prev-hash")
        self.assertEqual(event.event_seq, 42)

    def test_stored_event_is_frozen(self) -> None:
        """StoredEvent is a frozen dataclass and cannot be modified."""
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        event = StoredEvent(
            event_id="evt-123",
            incident_id="inc-456",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=now,
            actor="system",
            actor_id=None,
            payload_json="{}",
            payload_sha256="abc123",
            previous_event_sha256=None,
            event_sha256="def456",
            created_at=now,
        )

        with self.assertRaises(AttributeError):
            event.event_id = "modified"


class TestEventBuilder(unittest.TestCase):
    """Tests for EventBuilder class."""

    def setUp(self) -> None:
        self.test_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        self.test_incident_id = "test-incident-123"

    def test_build_first_event(self) -> None:
        """Build first event for an incident (no previous events)."""
        builder = EventBuilder(
            incident_id=self.test_incident_id,
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=self.test_time,
            payload={"severity": "error"},
        )

        event, payload = builder.build()

        self.assertIsNotNone(event.event_id)
        self.assertIn(self.test_incident_id, event.event_id)
        self.assertEqual(event.incident_id, self.test_incident_id)
        self.assertEqual(event.aggregate_version, 1)  # First event
        self.assertEqual(event.event_type, "incident.opened")
        self.assertEqual(event.actor, "system")
        self.assertIsNone(event.actor_id)
        self.assertIsNone(event.previous_event_sha256)  # First event
        self.assertIsNotNone(event.payload_sha256)
        self.assertIsNotNone(event.event_sha256)
        self.assertIsNotNone(event.created_at)
        self.assertEqual(payload, {"severity": "error"})

    def test_build_event_with_actor_id(self) -> None:
        """Build event with an actor_id."""
        builder = EventBuilder(
            incident_id=self.test_incident_id,
            event_type=IncidentEventType.UPDATED,
            actor=IncidentEventActor.USER,
            occurred_at=self.test_time,
            actor_id="user-456",
            payload={"note": "Updated"},
        )

        event, _ = builder.build()

        self.assertEqual(event.actor, "user")
        self.assertEqual(event.actor_id, "user-456")

    def test_build_subsequent_event(self) -> None:
        """Build subsequent event with hash chain."""
        # Build first event
        first_builder = EventBuilder(
            incident_id=self.test_incident_id,
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=self.test_time,
            payload={},
        )
        first_event, _ = first_builder.build()

        # Build second event
        second_builder = EventBuilder(
            incident_id=self.test_incident_id,
            event_type=IncidentEventType.UPDATED,
            actor=IncidentEventActor.USER,
            occurred_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            payload={"updated": True},
        )
        second_builder.with_previous_version(
            version=first_event.aggregate_version,
            previous_sha256=first_event.event_sha256,
        )
        second_event, _ = second_builder.build()

        self.assertEqual(second_event.aggregate_version, 2)
        self.assertEqual(second_event.previous_event_sha256, first_event.event_sha256)

    def test_build_all_event_types(self) -> None:
        """Build events for all event types."""
        for event_type in IncidentEventType:
            with self.subTest(event_type=event_type):
                builder = EventBuilder(
                    incident_id=f"{self.test_incident_id}-{event_type.value}",
                    event_type=event_type,
                    actor=IncidentEventActor.SYSTEM,
                    occurred_at=self.test_time,
                    payload={"type": event_type.value},
                )
                event, _ = builder.build()
                self.assertEqual(event.event_type, event_type.value)
                self.assertIsNotNone(event.event_sha256)

    def test_build_with_different_actors(self) -> None:
        """Build events with different actors."""
        for actor in IncidentEventActor:
            with self.subTest(actor=actor):
                builder = EventBuilder(
                    incident_id=f"{self.test_incident_id}-{actor.value}",
                    event_type=IncidentEventType.OPENED,
                    actor=actor,
                    occurred_at=self.test_time,
                    payload={},
                )
                event, _ = builder.build()
                self.assertEqual(event.actor, actor.value)


if __name__ == "__main__":
    unittest.main()
