"""Tests for incident detail payload serialization.

These tests verify:
1. Detail payload includes signals, evidence_links, and events
2. Events are serialized in timeline order
3. Detail payload shape and field coverage
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.collect.incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from k8s_diag_agent.collect.incident_evidence import EvidenceLink, EvidenceRole
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store
from k8s_diag_agent.ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_event_payload,
    build_incident_evidence_link_payload,
    build_incident_signal_payload,
)

from .incident_lifecycle_fixtures import (
    make_candidate,
    make_full_incident,
    make_incident_with_events,
    make_incident_with_evidence_links,
)
from .api_incident_reads_serializer_fixtures import TEST_TIME_1, TEST_TIME_2, TEST_TIME_3


class TestBuildIncidentDetailPayload(unittest.TestCase):
    """Test detail payload serialization."""

    def test_detail_includes_signals(self) -> None:
        """Detail payload must include signals list."""
        incident = make_incident_with_events()
        result = build_incident_detail_payload(incident)

        self.assertIn("signals", result)
        self.assertIsInstance(result["signals"], list)

    def test_detail_includes_evidence_links(self) -> None:
        """Detail payload must include evidence_links list."""
        incident = make_incident_with_evidence_links()
        result = build_incident_detail_payload(incident)

        self.assertIn("evidence_links", result)
        self.assertIsInstance(result["evidence_links"], list)

    def test_detail_includes_events(self) -> None:
        """Detail payload must include events list."""
        incident = make_incident_with_events()
        result = build_incident_detail_payload(incident)

        self.assertIn("events", result)
        self.assertIsInstance(result["events"], list)

    def test_detail_includes_source_candidate_id(self) -> None:
        """Detail payload must include source_candidate_id."""
        incident = make_incident_with_events()
        result = build_incident_detail_payload(incident)

        self.assertIn("source_candidate_id", result)

    def test_events_are_serialized_in_timeline_order(self) -> None:
        """Events must be serialized in timeline order (sorted by occurred_at)."""
        # Create incident with multiple events at different times
        incident_id = "test-timeline-order"

        event1 = IncidentEvent(
            event_id=make_event_id(incident_id, "first", TEST_TIME_1),
            incident_id=incident_id,
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="First event",
        )
        event2 = IncidentEvent(
            event_id=make_event_id(incident_id, "second", TEST_TIME_2),
            incident_id=incident_id,
            event_type=IncidentEventType.STATUS_CHANGED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_2,
            message="Second event",
        )
        event3 = IncidentEvent(
            event_id=make_event_id(incident_id, "third", TEST_TIME_3),
            incident_id=incident_id,
            event_type=IncidentEventType.CLOSED,
            actor=IncidentEventActor.USER,
            occurred_at=TEST_TIME_3,
            message="Third event",
        )

        # Add events in non-sorted order
        incident = make_full_incident()
        incident.events = [event3, event1, event2]

        result = build_incident_detail_payload(incident)

        # Events should be sorted by occurred_at
        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(result["events"][0]["event_id"], event1.event_id)
        self.assertEqual(result["events"][1]["event_id"], event2.event_id)
        self.assertEqual(result["events"][2]["event_id"], event3.event_id)


class TestBuildIncidentSignalPayload(unittest.TestCase):
    """Test signal serialization."""

    def test_signal_serialization(self) -> None:
        """Signal must be serialized correctly."""
        from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="back-off restarting",
            captured_at=TEST_TIME_1,
            run_id="run-123",
        )
        result = build_incident_signal_payload(signal)

        self.assertEqual(result["source"], "pod")
        self.assertEqual(result["reason"], "CrashLoopBackOff")
        self.assertEqual(result["message"], "back-off restarting")
        self.assertIn("captured_at", result)
        self.assertEqual(result["run_id"], "run-123")


class TestBuildIncidentEvidenceLinkPayload(unittest.TestCase):
    """Test evidence link serialization."""

    def test_evidence_link_serialization(self) -> None:
        """Evidence link must be serialized correctly."""
        link = EvidenceLink(
            incident_id="inc-123",
            artifact_id="bundle-abc",
            role=EvidenceRole.SNAPSHOT,
            attached_at=TEST_TIME_1,
        )
        result = build_incident_evidence_link_payload(link)

        self.assertEqual(result["incident_id"], "inc-123")
        self.assertEqual(result["artifact_id"], "bundle-abc")
        self.assertEqual(result["role"], "snapshot")
        self.assertIn("attached_at", result)


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


class TestHandleGetIncidentPayloadShape(unittest.TestCase):
    """Test that handle_get_incident returns correct payload shape."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_get_returns_detail_payload_shape(self) -> None:
        """handle_get_incident must return detail payload shape."""
        # Add incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id)

        self.assertIsNotNone(result)

        # Check all summary fields present
        summary_fields = [
            "incident_id",
            "namespace",
            "object_kind",
            "object_name",
            "candidate_class",
            "severity",
            "status",
            "signal_count",
            "evidence_count",
            "latest_snapshot_bundle_id",
            "review_packet",
        ]
        for field in summary_fields:
            self.assertIn(field, result, f"Missing summary field: {field}")

        # Check detail-only fields present
        self.assertIn("source_candidate_id", result)
        self.assertIn("signals", result)
        self.assertIn("evidence_needed", result)
        self.assertIn("evidence_links", result)
        self.assertIn("events", result)

        # Check forbidden fields absent
        self.assertNotIn("review_packet_available", result)
        self.assertNotIn("review_packet_id", result)
        self.assertNotIn("snapshot_bundle_id", result)

    def test_detail_includes_suggested_checks_field(self) -> None:
        """Detail payload must include suggested_checks field."""
        # Add incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id)

        self.assertIsNotNone(result)
        self.assertIn("suggested_checks", result)
        self.assertIsInstance(result["suggested_checks"], list)

    def test_detail_suggested_checks_is_empty_by_default(self) -> None:
        """Detail payload suggested_checks must be empty when no mapping exists."""
        # Add incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id)

        self.assertIsNotNone(result)
        self.assertIn("suggested_checks", result)
        self.assertEqual(result["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
