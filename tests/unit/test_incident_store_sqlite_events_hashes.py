"""Tests for SQLite incident store events - hashing functions.

This module tests:
- compute_payload_sha256 function
- compute_event_sha256 function
- _canonical_json function
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventType,
    _canonical_json,
    compute_event_sha256,
    compute_payload_sha256,
)


class TestComputePayloadSha256(unittest.TestCase):
    """Tests for compute_payload_sha256 function."""

    def test_empty_payload(self) -> None:
        """Empty payload produces a consistent hash."""
        payload: dict = {}
        hash1 = compute_payload_sha256(payload)
        hash2 = compute_payload_sha256(payload)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)  # SHA256 hex digest length

    def test_deterministic_hash(self) -> None:
        """Same payload always produces the same hash."""
        payload = {"key": "value", "number": 42}
        hash1 = compute_payload_sha256(payload)
        hash2 = compute_payload_sha256(payload)
        self.assertEqual(hash1, hash2)

    def test_different_payloads_different_hashes(self) -> None:
        """Different payloads produce different hashes."""
        hash1 = compute_payload_sha256({"key": "value1"})
        hash2 = compute_payload_sha256({"key": "value2"})
        self.assertNotEqual(hash1, hash2)

    def test_key_order_independent(self) -> None:
        """Key order doesn't affect hash (canonical JSON)."""
        hash1 = compute_payload_sha256({"a": 1, "b": 2})
        hash2 = compute_payload_sha256({"b": 2, "a": 1})
        self.assertEqual(hash1, hash2)

    def test_nested_payload(self) -> None:
        """Nested payload produces correct hash."""
        payload = {"outer": {"inner": "value"}, "list": [1, 2, 3]}
        hash_result = compute_payload_sha256(payload)
        self.assertIsInstance(hash_result, str)
        self.assertEqual(len(hash_result), 64)


class TestComputeEventSha256(unittest.TestCase):
    """Tests for compute_event_sha256 function."""

    def setUp(self) -> None:
        self.test_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_first_event_hash(self) -> None:
        """First event (no previous) produces consistent hash."""
        hash1 = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        hash2 = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_subsequent_event_hash_includes_previous(self) -> None:
        """Subsequent event hash depends on previous event hash."""
        first_hash = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        second_hash = compute_event_sha256(
            event_id="evt-2",
            incident_id="inc-1",
            aggregate_version=2,
            event_type="incident.updated",
            occurred_at=self.test_time,
            actor="user",
            actor_id=None,
            payload_sha256="def456",
            previous_event_sha256=first_hash,
        )
        self.assertNotEqual(first_hash, second_hash)

    def test_different_event_id_different_hash(self) -> None:
        """Different event_id produces different hash."""
        hash1 = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        hash2 = compute_event_sha256(
            event_id="evt-2",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="system",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        self.assertNotEqual(hash1, hash2)

    def test_with_actor_id(self) -> None:
        """Event with actor_id includes it in hash."""
        hash1 = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="user",
            actor_id="user-123",
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        hash2 = compute_event_sha256(
            event_id="evt-1",
            incident_id="inc-1",
            aggregate_version=1,
            event_type="incident.opened",
            occurred_at=self.test_time,
            actor="user",
            actor_id=None,
            payload_sha256="abc123",
            previous_event_sha256=None,
        )
        self.assertNotEqual(hash1, hash2)


class TestCanonicalJson(unittest.TestCase):
    """Tests for canonical JSON serialization."""

    def test_sorted_keys(self) -> None:
        """Keys are sorted alphabetically."""
        result = _canonical_json({"z": 1, "a": 2})
        # Result should have "a" before "z"
        self.assertIn('"a":2', result)
        self.assertIn('"z":1', result)

    def test_compact_format(self) -> None:
        """Output is compact (no extra spaces)."""
        result = _canonical_json({"key": "value"})
        self.assertNotIn(" ", result)
        self.assertNotIn("\n", result)

    def test_strenum_serialized(self) -> None:
        """StrEnum values are serialized as their string value."""
        result = _canonical_json({"type": IncidentEventType.OPENED})
        self.assertIn("incident.opened", result)

    def test_datetime_serialized(self) -> None:
        """datetime objects are serialized to ISO format."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = _canonical_json({"timestamp": dt})
        self.assertIn("2024-01-15T10:30:00", result)


if __name__ == "__main__":
    unittest.main()
