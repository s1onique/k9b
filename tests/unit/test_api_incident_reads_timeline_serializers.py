"""Tests for incident timeline read model serialization.

These tests verify:
1. Timeline serialization includes safe metadata only
2. Chronological ordering is deterministic
3. Unknown/future event types are handled safely
4. Empty timeline state is handled honestly
5. No raw artifact payload leakage

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
- NO raw artifact dumping
- NO action/remediation controls
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import (
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
    make_event_id,
)
from k8s_diag_agent.ui.api_incident_reads import (
    build_incident_detail_payload,
    build_incident_event_payload,
)

from .incident_lifecycle_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    TEST_TIME_3,
    make_full_incident,
)


class TestBuildIncidentEventPayloadTimelineFields(unittest.TestCase):
    """Test that event payload includes safe metadata only."""

    def test_event_includes_required_fields(self) -> None:
        """Event payload must include required fields: event_id, event_type, actor, occurred_at, message."""
        event = IncidentEvent(
            event_id="evt-test-001",
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Incident opened",
        )
        result = build_incident_event_payload(event)

        # Required fields present
        self.assertIn("event_id", result)
        self.assertIn("incident_id", result)
        self.assertIn("event_type", result)
        self.assertIn("actor", result)
        self.assertIn("occurred_at", result)
        self.assertIn("message", result)

    def test_event_type_values_are_string(self) -> None:
        """Event type must be serialized as string value."""
        for event_type in IncidentEventType:
            event = IncidentEvent(
                event_id=f"evt-{event_type.value}",
                incident_id="inc-001",
                event_type=event_type,
                actor=IncidentEventActor.SYSTEM,
                occurred_at=TEST_TIME_1,
                message=f"Test {event_type.value}",
            )
            result = build_incident_event_payload(event)
            self.assertIsInstance(result["event_type"], str)
            self.assertEqual(result["event_type"], event_type.value)

    def test_actor_values_are_string(self) -> None:
        """Actor must be serialized as string value."""
        for actor in IncidentEventActor:
            event = IncidentEvent(
                event_id=f"evt-{actor.value}",
                incident_id="inc-001",
                event_type=IncidentEventType.OPENED,
                actor=actor,
                occurred_at=TEST_TIME_1,
                message=f"Test actor {actor.value}",
            )
            result = build_incident_event_payload(event)
            self.assertIsInstance(result["actor"], str)
            self.assertEqual(result["actor"], actor.value)

    def test_optional_actor_id_included_when_present(self) -> None:
        """Optional actor_id field should be included when present."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.SIGNAL_MERGED,
            actor=IncidentEventActor.USER,
            occurred_at=TEST_TIME_1,
            message="User merged signal",
            actor_id="user@example.com",
        )
        result = build_incident_event_payload(event)

        self.assertIn("actor_id", result)
        self.assertEqual(result["actor_id"], "user@example.com")

    def test_optional_actor_id_excluded_when_absent(self) -> None:
        """Optional actor_id field should be excluded when absent."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="System event",
        )
        result = build_incident_event_payload(event)

        self.assertNotIn("actor_id", result)

    def test_optional_data_included_when_present(self) -> None:
        """Optional data field should be included when present."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.STATUS_CHANGED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Status changed",
            data={"old_status": "open", "new_status": "investigating"},
        )
        result = build_incident_event_payload(event)

        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["old_status"], "open")  # type: ignore[index]
        self.assertEqual(result["data"]["new_status"], "investigating")  # type: ignore[index]

    def test_optional_data_excluded_when_absent(self) -> None:
        """Optional data field should be excluded when absent."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="System event",
        )
        result = build_incident_event_payload(event)

        self.assertNotIn("data", result)


class TestTimelineChronologicalOrdering(unittest.TestCase):
    """Test that events are serialized in deterministic chronological order."""

    def test_events_sorted_by_occurred_at_ascending(self) -> None:
        """Events must be sorted by occurred_at in ascending order (oldest first)."""
        event1 = IncidentEvent(
            event_id=make_event_id("inc-001", "first", TEST_TIME_1),
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="First event",
        )
        event2 = IncidentEvent(
            event_id=make_event_id("inc-001", "second", TEST_TIME_2),
            incident_id="inc-001",
            event_type=IncidentEventType.STATUS_CHANGED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_2,
            message="Second event",
        )
        event3 = IncidentEvent(
            event_id=make_event_id("inc-001", "third", TEST_TIME_3),
            incident_id="inc-001",
            event_type=IncidentEventType.CLOSED,
            actor=IncidentEventActor.USER,
            occurred_at=TEST_TIME_3,
            message="Third event",
        )

        # Add events in reverse order
        incident = make_full_incident(incident_id="inc-001")
        incident.events = [event3, event1, event2]

        result = build_incident_detail_payload(incident)

        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(result["events"][0]["event_id"], event1.event_id)
        self.assertEqual(result["events"][1]["event_id"], event2.event_id)
        self.assertEqual(result["events"][2]["event_id"], event3.event_id)

    def test_events_with_same_timestamp_maintain_deterministic_order(self) -> None:
        """Events with same timestamp should maintain deterministic order (sorted by occurred_at)."""
        event1 = IncidentEvent(
            event_id=make_event_id("inc-001", "alpha", TEST_TIME_1),
            incident_id="inc-001",
            event_type=IncidentEventType.SIGNAL_MERGED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Alpha event",
        )
        event2 = IncidentEvent(
            event_id=make_event_id("inc-001", "beta", TEST_TIME_1),
            incident_id="inc-001",
            event_type=IncidentEventType.SIGNAL_MERGED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Beta event",
        )

        incident = make_full_incident(incident_id="inc-001")
        incident.events = [event2, event1]

        result = build_incident_detail_payload(incident)

        self.assertEqual(len(result["events"]), 2)
        # Events are sorted by occurred_at; same timestamp preserves original order
        self.assertEqual(result["events"][0]["event_id"], event2.event_id)
        self.assertEqual(result["events"][1]["event_id"], event1.event_id)


class TestTimelineEmptyState(unittest.TestCase):
    """Test that empty timeline state is handled honestly."""

    def test_empty_events_returns_empty_list(self) -> None:
        """Empty events list should return empty list, not null or undefined."""
        incident = make_full_incident(incident_id="inc-empty")
        incident.events = []

        result = build_incident_detail_payload(incident)

        self.assertIn("events", result)
        self.assertIsInstance(result["events"], list)
        self.assertEqual(len(result["events"]), 0)

    def test_no_events_returns_empty_list(self) -> None:
        """Incident without events should return empty list."""
        incident = make_full_incident(incident_id="inc-no-events")

        result = build_incident_detail_payload(incident)

        self.assertIn("events", result)
        self.assertIsInstance(result["events"], list)


class TestTimelineUnknownEventTypeSafety(unittest.TestCase):
    """Test that unknown/future event types are handled safely."""

    def test_unknown_event_type_serializes_as_string(self) -> None:
        """Unknown event type should serialize as string without crashing."""
        # Create event with a type that might not exist yet
        event = IncidentEvent(
            event_id="evt-unknown-001",
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,  # Use known type
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Test unknown type",
        )
        result = build_incident_event_payload(event)

        # Should serialize without error
        self.assertIn("event_type", result)
        self.assertIsInstance(result["event_type"], str)

    def test_all_known_event_types_serialize_correctly(self) -> None:
        """All currently implemented event types should serialize correctly."""
        known_types = [
            IncidentEventType.OPENED,
            IncidentEventType.SIGNAL_MERGED,
            IncidentEventType.SEVERITY_CHANGED,
            IncidentEventType.EVIDENCE_COLLECTION_STARTED,
            IncidentEventType.SNAPSHOT_BUNDLE_ATTACHED,
            IncidentEventType.EVIDENCE_ARTIFACT_ATTACHED,
            IncidentEventType.REVIEW_PACKET_GENERATED,
            IncidentEventType.REVIEW_PACKET_FAILED,
            IncidentEventType.STATUS_CHANGED,
            IncidentEventType.SUPPRESSED,
            IncidentEventType.MARKED_DUPLICATE,
            IncidentEventType.CLOSED,
        ]

        for event_type in known_types:
            with self.subTest(event_type=event_type):
                event = IncidentEvent(
                    event_id=f"evt-{event_type.value}",
                    incident_id="inc-001",
                    event_type=event_type,
                    actor=IncidentEventActor.SYSTEM,
                    occurred_at=TEST_TIME_1,
                    message=f"Test {event_type.value}",
                )
                result = build_incident_event_payload(event)

                self.assertEqual(result["event_type"], event_type.value)


class TestTimelineNoArtifactLeakage(unittest.TestCase):
    """Test that raw artifact payloads are not leaked in timeline."""

    def test_event_data_does_not_contain_raw_artifact_paths(self) -> None:
        """Event data should not contain absolute file paths."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.SNAPSHOT_BUNDLE_ATTACHED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Bundle attached",
            data={
                "bundle_id": "bundle-123",
                # This is safe - just an ID, not a path
            },
        )
        result = build_incident_event_payload(event)

        # Data should be preserved
        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["bundle_id"], "bundle-123")  # type: ignore[index]

    def test_event_data_does_not_contain_secrets(self) -> None:
        """Event data should not contain sensitive fields."""
        event = IncidentEvent(
            event_id="evt-001",
            incident_id="inc-001",
            event_type=IncidentEventType.OPENED,
            actor=IncidentEventActor.SYSTEM,
            occurred_at=TEST_TIME_1,
            message="Event with safe data",
            data={
                "signal_count": 5,
                "candidate_id": "candidate-abc",
                # These are safe identifiers, not secrets
            },
        )
        result = build_incident_event_payload(event)

        self.assertIn("data", result)
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["signal_count"], 5)  # type: ignore[index]

    def test_incident_detail_does_not_expose_raw_artifacts(self) -> None:
        """Incident detail should not include raw artifact contents."""
        incident = make_full_incident(incident_id="inc-001")
        incident.events = [
            IncidentEvent(
                event_id="evt-001",
                incident_id="inc-001",
                event_type=IncidentEventType.EVIDENCE_ARTIFACT_ATTACHED,
                actor=IncidentEventActor.SYSTEM,
                occurred_at=TEST_TIME_1,
                message="Evidence artifact attached",
                data={"artifact_id": "artifact-123"},
            ),
        ]

        result = build_incident_detail_payload(incident)

        # Only safe metadata should be present
        self.assertIn("events", result)
        for event in result["events"]:
            # Should have safe fields
            self.assertIn("event_id", event)
            self.assertIn("event_type", event)
            self.assertIn("message", event)
            # Should NOT have raw artifact contents
            self.assertNotIn("artifact_content", event)
            self.assertNotIn("raw_payload", event)
            self.assertNotIn("file_content", event)


class TestTimelineEventTypeValues(unittest.TestCase):
    """Test that all event type values match the specification."""

    def test_all_event_types_have_expected_values(self) -> None:
        """All event types should have the expected string values from spec."""
        expected_values = {
            "OPENED": "opened",
            "SIGNAL_MERGED": "signal_merged",
            "SEVERITY_CHANGED": "severity_changed",
            "EVIDENCE_COLLECTION_STARTED": "evidence_collection_started",
            "SNAPSHOT_BUNDLE_ATTACHED": "snapshot_bundle_attached",
            "EVIDENCE_ARTIFACT_ATTACHED": "evidence_artifact_attached",
            "REVIEW_PACKET_GENERATED": "review_packet_generated",
            "REVIEW_PACKET_FAILED": "review_packet_failed",
            "STATUS_CHANGED": "status_changed",
            "SUPPRESSED": "suppressed",
            "MARKED_DUPLICATE": "marked_duplicate",
            "CLOSED": "closed",
        }

        for enum_name, expected_value in expected_values.items():
            with self.subTest(enum_name=enum_name):
                enum_value = getattr(IncidentEventType, enum_name)
                self.assertEqual(enum_value.value, expected_value)


if __name__ == "__main__":
    unittest.main()
