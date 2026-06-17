"""Tests for incident read-model serializers.

Tests:
1. summary payload uses review_packet object
2. summary payload omits review_packet_available and review_packet_id
3. summary payload uses latest_snapshot_bundle_id and omits snapshot_bundle_id
4. not_generated review packet serializes without id
5. available review packet serializes with id
6. detail payload includes signals, evidence_links, and events
7. events are serialized in timeline order if get_timeline() provides sorted order
8. collect handle_list_incidents returns summary payload shape
9. collect handle_get_incident returns detail payload shape
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.api_incident_reads import (
    handle_get_incident,
    handle_list_incidents,
)
from k8s_diag_agent.collect.incident_events import IncidentEvent, IncidentEventActor, IncidentEventType, make_event_id
from k8s_diag_agent.collect.incident_evidence import EvidenceLink, EvidenceRole
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketState, ReviewPacketStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store
from k8s_diag_agent.ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_event_payload,
    build_incident_evidence_link_payload,
    build_incident_review_packet_payload,
    build_incident_signal_payload,
    build_incident_summary_payload,
)

from .incident_lifecycle_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    TEST_TIME_3,
    make_candidate,
    make_full_incident,
    make_incident_with_events,
    make_incident_with_evidence_links,
)


class TestBuildIncidentReviewPacketPayload(unittest.TestCase):
    """Test review packet serialization."""

    def test_not_generated_serializes_without_id(self) -> None:
        """Not-generated review packet must not include id."""
        state = ReviewPacketState.not_generated()
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "not_generated")
        self.assertNotIn("id", result)
        self.assertNotIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_available_review_packet_serializes_with_id(self) -> None:
        """Available review packet must include id and generated_at."""
        generated_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = ReviewPacketState.available(id="packet-123", generated_at=generated_at)
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["id"], "packet-123")
        self.assertIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_generating_review_packet_serializes_with_id(self) -> None:
        """Generating review packet must include id."""
        state = ReviewPacketState.generating(id="packet-456")
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "generating")
        self.assertEqual(result["id"], "packet-456")
        self.assertNotIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_failed_review_packet_serializes_error_message(self) -> None:
        """Failed review packet must include error_message."""
        state = ReviewPacketState.failed(error_message="LLM unavailable")
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("id", result)
        self.assertNotIn("generated_at", result)
        self.assertEqual(result["error_message"], "LLM unavailable")


class TestBuildIncidentSummaryPayload(unittest.TestCase):
    """Test summary payload serialization."""

    def test_summary_uses_review_packet_object(self) -> None:
        """Summary payload must use review_packet object."""
        incident = make_full_incident(
            review_packet_status=ReviewPacketStatus.AVAILABLE,
            review_packet_id="packet-abc",
        )
        result = build_incident_summary_payload(incident)

        self.assertIn("review_packet", result)
        self.assertIsInstance(result["review_packet"], dict)
        self.assertEqual(result["review_packet"]["status"], "available")
        self.assertEqual(result["review_packet"]["id"], "packet-abc")

    def test_summary_omits_review_packet_available(self) -> None:
        """Summary payload must NOT include review_packet_available."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("review_packet_available", result)

    def test_summary_omits_review_packet_id(self) -> None:
        """Summary payload must NOT include review_packet_id as top-level field."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("review_packet_id", result)

    def test_summary_uses_latest_snapshot_bundle_id(self) -> None:
        """Summary payload must use latest_snapshot_bundle_id."""
        incident = make_full_incident(
            latest_snapshot_bundle_id="bundle-xyz",
        )
        result = build_incident_summary_payload(incident)

        self.assertIn("latest_snapshot_bundle_id", result)
        self.assertEqual(result["latest_snapshot_bundle_id"], "bundle-xyz")

    def test_summary_omits_snapshot_bundle_id(self) -> None:
        """Summary payload must NOT include snapshot_bundle_id."""
        incident = make_full_incident(
            latest_snapshot_bundle_id="bundle-xyz",
        )
        result = build_incident_summary_payload(incident)

        self.assertNotIn("snapshot_bundle_id", result)

    def test_summary_includes_required_fields(self) -> None:
        """Summary payload must include all required fields."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        required_fields = [
            "incident_id",
            "namespace",
            "object_kind",
            "object_name",
            "raw_object_kind",
            "candidate_class",
            "severity",
            "status",
            "first_observed_at",
            "last_observed_at",
            "signal_count",
            "evidence_count",
            "latest_snapshot_bundle_id",
            "review_packet",
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing required field: {field}")

    def test_summary_includes_candidate_class(self) -> None:
        """Summary payload must include candidate_class field."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertIn("candidate_class", result)
        self.assertEqual(result["candidate_class"], "crash_loop")


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


class TestHandleListIncidentsPayloadShape(unittest.TestCase):
    """Test that handle_list_incidents returns correct payload shape."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_list_returns_summary_payload_shape(self) -> None:
        """handle_list_incidents must return summary payload shape."""
        # Add incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)

        result = handle_list_incidents()

        self.assertIn("incidents", result)
        self.assertIn("total", result)
        self.assertEqual(result["total"], 1)

        incident = result["incidents"][0]

        # Check summary fields present
        self.assertIn("incident_id", incident)
        self.assertIn("namespace", incident)
        self.assertIn("object_kind", incident)
        self.assertIn("object_name", incident)
        self.assertIn("candidate_class", incident)
        self.assertIn("severity", incident)
        self.assertIn("status", incident)
        self.assertIn("signal_count", incident)
        self.assertIn("evidence_count", incident)
        self.assertIn("latest_snapshot_bundle_id", incident)
        self.assertIn("review_packet", incident)

        # Check forbidden fields absent
        self.assertNotIn("review_packet_available", incident)
        self.assertNotIn("review_packet_id", incident)
        self.assertNotIn("snapshot_bundle_id", incident)

        # Check no detail-only fields
        self.assertNotIn("source_candidate_id", incident)
        self.assertNotIn("signals", incident)
        self.assertNotIn("evidence_needed", incident)
        self.assertNotIn("evidence_links", incident)
        self.assertNotIn("events", incident)


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

    def test_detail_includes_suggested_checks(self) -> None:
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


class TestBuildIncidentDetailPayloadSuggestedChecks(unittest.TestCase):
    """Test suggested_checks field in detail payload."""

    def test_detail_suggested_checks_field_present(self) -> None:
        """Detail payload must include suggested_checks field."""
        incident = make_full_incident()
        result = build_incident_detail_payload(incident)

        self.assertIn("suggested_checks", result)
        self.assertIsInstance(result["suggested_checks"], list)

    def test_detail_suggested_checks_empty_by_default(self) -> None:
        """Detail payload suggested_checks must be empty when no mapping exists."""
        incident = make_full_incident()
        result = build_incident_detail_payload(incident)

        self.assertEqual(result["suggested_checks"], [])

    def test_summary_does_not_include_suggested_checks(self) -> None:
        """Summary payload must NOT include suggested_checks (detail-only field)."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("suggested_checks", result)


if __name__ == "__main__":
    unittest.main()
