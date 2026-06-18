"""Tests for event serialization in incident detail payloads."""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import IncidentEvent, IncidentEventActor, IncidentEventType
from k8s_diag_agent.ui.api_incident_reads import build_incident_event_payload

from .incident_lifecycle_fixtures import TEST_TIME_1


class TestBuildIncidentEventPayload(unittest.TestCase):
    """Test event serialization."""

    def test_event_serialization(self) -> None:
        """Event must be serialized correctly."""
        event = IncidentEvent(
            event_id="evt-123",
            incident_id="inc-456",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Incident opened",
            data={"key": "value"},
        )
        result = build_incident_event_payload(event)

        self.assertEqual(result["event_id"], "evt-123")
        self.assertEqual(result["incident_id"], "inc-456")
        self.assertEqual(result["event_type"], "opened")
        self.assertEqual(result["actor"], "system")
        self.assertEqual(result["message"], "Incident opened")
        self.assertIn("occurred_at", result)
        self.assertEqual(result["data"], {"key": "value"})


if __name__ == "__main__":
    unittest.main()
