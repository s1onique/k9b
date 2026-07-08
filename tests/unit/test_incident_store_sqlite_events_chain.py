"""Tests for SQLite incident store events - hash chain verification.

This module tests:
- verify_hash_chain function with valid/invalid chains
- Event hash chain integrity
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    StoredEvent,
    compute_event_sha256,
    compute_payload_sha256,
    verify_hash_chain,
)


class TestVerifyHashChain(unittest.TestCase):
    """Tests for verify_hash_chain function."""

    def setUp(self) -> None:
        self.test_incident_id = "test-incident-verify"

    def _create_valid_event_chain(self, count: int = 3) -> list[StoredEvent]:
        """Helper to create a valid event chain."""
        events = []
        prev_sha256 = None

        for i in range(count):
            event_time = datetime(2024, 1, 15, 10 + i, 0, 0, tzinfo=UTC)
            payload = {"version": i + 1}
            payload_sha256 = compute_payload_sha256(payload)

            event_id = f"evt-{i + 1}"
            event_type = "incident.opened" if i == 0 else "incident.updated"
            actor = "system" if i == 0 else "user"

            event_sha256 = compute_event_sha256(
                event_id=event_id,
                incident_id=self.test_incident_id,
                aggregate_version=i + 1,
                event_type=event_type,
                occurred_at=event_time,
                actor=actor,
                actor_id=None,
                payload_sha256=payload_sha256,
                previous_event_sha256=prev_sha256,
            )

            event = StoredEvent(
                event_id=event_id,
                incident_id=self.test_incident_id,
                aggregate_version=i + 1,
                event_type=event_type,
                occurred_at=event_time,
                actor=actor,
                actor_id=None,
                payload_json=json.dumps(payload),
                payload_sha256=payload_sha256,
                previous_event_sha256=prev_sha256,
                event_sha256=event_sha256,
                created_at=event_time,
            )
            events.append(event)
            prev_sha256 = event_sha256

        return events

    def test_valid_single_event_chain(self) -> None:
        """Single valid event passes verification."""
        events = self._create_valid_event_chain(1)
        self.assertTrue(verify_hash_chain(events))

    def test_valid_multi_event_chain(self) -> None:
        """Valid chain of multiple events passes verification."""
        events = self._create_valid_event_chain(5)
        self.assertTrue(verify_hash_chain(events))

    def test_empty_chain(self) -> None:
        """Empty chain passes verification (edge case)."""
        self.assertTrue(verify_hash_chain([]))

    def test_invalid_event_hash(self) -> None:
        """Modified event hash fails verification."""
        events = self._create_valid_event_chain(2)
        # Tamper with the event hash
        events[0] = StoredEvent(
            event_id=events[0].event_id,
            incident_id=events[0].incident_id,
            aggregate_version=events[0].aggregate_version,
            event_type=events[0].event_type,
            occurred_at=events[0].occurred_at,
            actor=events[0].actor,
            actor_id=events[0].actor_id,
            payload_json=events[0].payload_json,
            payload_sha256=events[0].payload_sha256,
            previous_event_sha256=events[0].previous_event_sha256,
            event_sha256="tampered_hash_value_123456789",
            created_at=events[0].created_at,
        )
        self.assertFalse(verify_hash_chain(events))

    def test_broken_sequence_version(self) -> None:
        """Non-sequential versions fail verification."""
        events = self._create_valid_event_chain(2)
        # Modify second event to have wrong version
        events[1] = StoredEvent(
            event_id=events[1].event_id,
            incident_id=events[1].incident_id,
            aggregate_version=5,  # Wrong version
            event_type=events[1].event_type,
            occurred_at=events[1].occurred_at,
            actor=events[1].actor,
            actor_id=events[1].actor_id,
            payload_json=events[1].payload_json,
            payload_sha256=events[1].payload_sha256,
            previous_event_sha256=events[1].previous_event_sha256,
            event_sha256=events[1].event_sha256,
            created_at=events[1].created_at,
        )
        self.assertFalse(verify_hash_chain(events))

    def test_broken_hash_chain(self) -> None:
        """Broken previous hash reference fails verification."""
        events = self._create_valid_event_chain(2)
        # Modify second event to have wrong previous hash
        events[1] = StoredEvent(
            event_id=events[1].event_id,
            incident_id=events[1].incident_id,
            aggregate_version=events[1].aggregate_version,
            event_type=events[1].event_type,
            occurred_at=events[1].occurred_at,
            actor=events[1].actor,
            actor_id=events[1].actor_id,
            payload_json=events[1].payload_json,
            payload_sha256=events[1].payload_sha256,
            previous_event_sha256="wrong_previous_hash",
            event_sha256=events[1].event_sha256,
            created_at=events[1].created_at,
        )
        self.assertFalse(verify_hash_chain(events))

    def test_tampered_payload(self) -> None:
        """Tampered payload fails verification."""
        events = self._create_valid_event_chain(2)
        # Modify payload and recompute hashes
        tampered_payload = {"version": 99}  # Changed!
        tampered_payload_sha256 = compute_payload_sha256(tampered_payload)

        events[0] = StoredEvent(
            event_id=events[0].event_id,
            incident_id=events[0].incident_id,
            aggregate_version=events[0].aggregate_version,
            event_type=events[0].event_type,
            occurred_at=events[0].occurred_at,
            actor=events[0].actor,
            actor_id=events[0].actor_id,
            payload_json=json.dumps(tampered_payload),  # Tampered!
            payload_sha256=tampered_payload_sha256,
            previous_event_sha256=events[0].previous_event_sha256,
            event_sha256=events[0].event_sha256,  # Hash won't match
            created_at=events[0].created_at,
        )
        self.assertFalse(verify_hash_chain(events))


if __name__ == "__main__":
    unittest.main()
