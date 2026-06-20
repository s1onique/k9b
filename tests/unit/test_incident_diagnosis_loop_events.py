"""Tests for diagnosis loop incident timeline events.

These tests verify:
1. Event type enum values are correct
2. Transition functions create correct events
3. Events contain safe metadata only
4. Chronological ordering is preserved
5. No raw packet/artifact leakage

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
- NO raw artifact dumping
- NO action/remediation controls
- NO error_message in failed events (uses bounded reason codes only)
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_events import (
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident
from k8s_diag_agent.collect.incident_transitions import (
    mark_diagnosis_loop_completed,
    mark_diagnosis_loop_failed,
    mark_diagnosis_loop_started,
)
from k8s_diag_agent.ui.api_incident_reads import build_incident_event_payload

# Test timestamps
TEST_TIME_1 = datetime(2026, 6, 21, 0, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2026, 6, 21, 0, 1, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2026, 6, 21, 0, 2, 0, tzinfo=UTC)


def make_test_incident(
    incident_id: str = "test-incident",
    events: list[IncidentEvent] | None = None,
) -> Incident:
    """Create a minimal test incident."""
    return Incident(
        incident_id=incident_id,
        source_candidate_id="candidate-123",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status="open",
        first_observed_at=TEST_TIME_1,
        last_observed_at=TEST_TIME_1,
        events=events or [],
    )


class TestDiagnosisLoopEventTypes(unittest.TestCase):
    """Test that DIAGNOSIS_LOOP event types are correctly defined."""

    def test_diagnosis_loop_started_enum_value(self) -> None:
        """DIAGNOSIS_LOOP_STARTED must have correct string value."""
        self.assertEqual(IncidentEventType.DIAGNOSIS_LOOP_STARTED.value, "diagnosis_loop_started")

    def test_diagnosis_loop_completed_enum_value(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED must have correct string value."""
        self.assertEqual(IncidentEventType.DIAGNOSIS_LOOP_COMPLETED.value, "diagnosis_loop_completed")

    def test_diagnosis_loop_failed_enum_value(self) -> None:
        """DIAGNOSIS_LOOP_FAILED must have correct string value."""
        self.assertEqual(IncidentEventType.DIAGNOSIS_LOOP_FAILED.value, "diagnosis_loop_failed")

    def test_all_diagnosis_loop_types_in_enum(self) -> None:
        """All three diagnosis loop types must be in IncidentEventType enum."""
        types = [e.value for e in IncidentEventType]
        self.assertIn("diagnosis_loop_started", types)
        self.assertIn("diagnosis_loop_completed", types)
        self.assertIn("diagnosis_loop_failed", types)


class TestDiagnosisLoopStartedEvent(unittest.TestCase):
    """Test mark_diagnosis_loop_started transition."""

    def test_creates_started_event(self) -> None:
        """mark_diagnosis_loop_started creates DIAGNOSIS_LOOP_STARTED event."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            occurred_at=TEST_TIME_1,
        )

        self.assertEqual(len(updated.events), 1)
        event = updated.events[0]
        self.assertEqual(event.event_type, IncidentEventType.DIAGNOSIS_LOOP_STARTED)
        self.assertEqual(event.actor, IncidentEventActor.SYSTEM)
        self.assertEqual(event.message, "Automatic diagnosis loop started")

    def test_started_event_contains_safe_metadata(self) -> None:
        """DIAGNOSIS_LOOP_STARTED event contains safe metadata only."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            occurred_at=TEST_TIME_1,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertIn("run_id", event.data)
        self.assertIn("collector_run_id", event.data)
        self.assertIn("read_only", event.data)
        self.assertIn("review_required_before_any_action", event.data)
        self.assertIn("no_remediation_attempted", event.data)
        self.assertTrue(event.data["read_only"])
        self.assertTrue(event.data["review_required_before_any_action"])
        self.assertTrue(event.data["no_remediation_attempted"])

    def test_started_event_no_raw_content(self) -> None:
        """DIAGNOSIS_LOOP_STARTED event must not contain raw packet/artifact content."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            occurred_at=TEST_TIME_1,
        )

        event = updated.events[0]
        self.assertNotIn("packet_content", event.data or {})
        self.assertNotIn("artifact_payload", event.data or {})
        self.assertNotIn("logs", event.data or {})
        self.assertNotIn("stdout", event.data or {})
        self.assertNotIn("stderr", event.data or {})
        self.assertNotIn("stack_trace", event.data or {})
        self.assertNotIn("prompt", event.data or {})


class TestDiagnosisLoopCompletedEvent(unittest.TestCase):
    """Test mark_diagnosis_loop_completed transition."""

    def test_creates_completed_event(self) -> None:
        """mark_diagnosis_loop_completed creates DIAGNOSIS_LOOP_COMPLETED event."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            checks_requested=3,
            checks_run=2,
            checks_rejected=1,
            occurred_at=TEST_TIME_2,
        )

        self.assertEqual(len(updated.events), 1)
        event = updated.events[0]
        self.assertEqual(event.event_type, IncidentEventType.DIAGNOSIS_LOOP_COMPLETED)
        self.assertEqual(event.actor, IncidentEventActor.SYSTEM)
        self.assertEqual(event.message, "Automatic diagnosis loop completed")

    def test_completed_event_contains_check_counts(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED event contains check counts."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            checks_requested=5,
            checks_run=3,
            checks_rejected=2,
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertEqual(event.data["checks_requested"], 5)
        self.assertEqual(event.data["checks_run"], 3)
        self.assertEqual(event.data["checks_rejected"], 2)

    def test_completed_event_with_review_packet_name(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED event can include review packet name."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            review_packet_name="auto-inc-123-20260621000000-review-packet.json",
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertIn("review_packet_id", event.data)
        self.assertEqual(event.data["review_packet_id"], "auto-inc-123-20260621000000-review-packet.json")

    def test_completed_event_contains_safety_metadata(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED event contains safety metadata."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="auto-diagnosis-20260621000000-abc123",
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertTrue(event.data["read_only"])
        self.assertTrue(event.data["review_required_before_any_action"])
        self.assertTrue(event.data["no_remediation_attempted"])


class TestDiagnosisLoopFailedEvent(unittest.TestCase):
    """Test mark_diagnosis_loop_failed transition.

    Safe reason codes used by this transition:
        - unsafe_run_id: Generated run_id failed safety validation
        - case_file_error: Failed to build case file
        - case_file_none: Case file returned None
        - orchestrator_error: Orchestrator raised an exception
        - not_eligible: Incident not eligible for diagnosis loop
    """

    def test_creates_failed_event(self) -> None:
        """mark_diagnosis_loop_failed creates DIAGNOSIS_LOOP_FAILED event."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            unavailable_reason="not_eligible",
            occurred_at=TEST_TIME_3,
        )

        self.assertEqual(len(updated.events), 1)
        event = updated.events[0]
        self.assertEqual(event.event_type, IncidentEventType.DIAGNOSIS_LOOP_FAILED)
        self.assertEqual(event.actor, IncidentEventActor.SYSTEM)
        self.assertEqual(event.message, "Automatic diagnosis loop failed or unavailable")

    def test_failed_event_contains_reason(self) -> None:
        """DIAGNOSIS_LOOP_FAILED event contains unavailable_reason."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            unavailable_reason="case_file_error",
            occurred_at=TEST_TIME_3,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertEqual(event.data["unavailable_reason"], "case_file_error")

    def test_failed_event_with_run_id(self) -> None:
        """DIAGNOSIS_LOOP_FAILED event can include run_id."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            run_id="auto-inc-123-20260621000000",
            unavailable_reason="orchestrator_error",
            occurred_at=TEST_TIME_3,
        )

        event = updated.events[0]
        self.assertIsNotNone(event.data)
        self.assertEqual(event.data["run_id"], "auto-inc-123-20260621000000")
        self.assertEqual(event.data["unavailable_reason"], "orchestrator_error")

    def test_failed_event_no_error_message(self) -> None:
        """DIAGNOSIS_LOOP_FAILED event must NOT contain error_message field."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            run_id="auto-inc-123-20260621000000",
            unavailable_reason="orchestrator_error",
            occurred_at=TEST_TIME_3,
        )

        event = updated.events[0]
        self.assertNotIn("error_message", event.data or {})

    def test_failed_event_no_raw_content(self) -> None:
        """DIAGNOSIS_LOOP_FAILED event must not contain raw packet/artifact content."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            run_id="auto-inc-123-20260621000000",
            unavailable_reason="orchestrator_error",
            occurred_at=TEST_TIME_3,
        )

        event = updated.events[0]
        self.assertNotIn("packet_content", event.data or {})
        self.assertNotIn("artifact_payload", event.data or {})
        self.assertNotIn("logs", event.data or {})
        self.assertNotIn("stdout", event.data or {})
        self.assertNotIn("stderr", event.data or {})
        self.assertNotIn("stack_trace", event.data or {})
        self.assertNotIn("prompt", event.data or {})


class TestDiagnosisLoopEventOrdering(unittest.TestCase):
    """Test that diagnosis loop events are ordered correctly in timeline."""

    def test_started_then_completed_ordering(self) -> None:
        """DIAGNOSIS_LOOP_STARTED should come before DIAGNOSIS_LOOP_COMPLETED."""
        incident = make_test_incident()

        updated1 = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_1,
        )

        updated2 = mark_diagnosis_loop_completed(
            updated1,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_2,
        )

        self.assertEqual(len(updated2.events), 2)
        self.assertEqual(updated2.events[0].event_type, IncidentEventType.DIAGNOSIS_LOOP_STARTED)
        self.assertEqual(updated2.events[1].event_type, IncidentEventType.DIAGNOSIS_LOOP_COMPLETED)

    def test_started_then_failed_ordering(self) -> None:
        """DIAGNOSIS_LOOP_STARTED should come before DIAGNOSIS_LOOP_FAILED."""
        incident = make_test_incident()

        updated1 = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_1,
        )

        updated2 = mark_diagnosis_loop_failed(
            updated1,
            run_id="auto-inc-123-20260621000000",
            unavailable_reason="case_file_error",
            occurred_at=TEST_TIME_2,
        )

        self.assertEqual(len(updated2.events), 2)
        self.assertEqual(updated2.events[0].event_type, IncidentEventType.DIAGNOSIS_LOOP_STARTED)
        self.assertEqual(updated2.events[1].event_type, IncidentEventType.DIAGNOSIS_LOOP_FAILED)

    def test_events_sorted_by_time(self) -> None:
        """Events should be sorted by occurred_at timestamp."""
        incident = make_test_incident()

        updated1 = mark_diagnosis_loop_failed(
            incident,
            unavailable_reason="ineligible",
            occurred_at=TEST_TIME_3,
        )

        updated2 = mark_diagnosis_loop_started(
            updated1,
            run_id="run-3",
            collector_run_id="collector-003",
            occurred_at=TEST_TIME_1,
        )

        updated3 = mark_diagnosis_loop_completed(
            updated2,
            run_id="run-3",
            collector_run_id="collector-003",
            occurred_at=TEST_TIME_2,
        )

        timeline = sorted(updated3.events, key=lambda e: e.occurred_at)

        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0].event_type, IncidentEventType.DIAGNOSIS_LOOP_STARTED)
        self.assertEqual(timeline[1].event_type, IncidentEventType.DIAGNOSIS_LOOP_COMPLETED)
        self.assertEqual(timeline[2].event_type, IncidentEventType.DIAGNOSIS_LOOP_FAILED)


class TestDiagnosisLoopEventSerialization(unittest.TestCase):
    """Test that diagnosis loop events serialize correctly for API."""

    def test_started_event_serializes(self) -> None:
        """DIAGNOSIS_LOOP_STARTED event serializes to correct payload."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_started(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_1,
        )

        event = updated.events[0]
        payload = build_incident_event_payload(event)

        self.assertEqual(payload["event_type"], "diagnosis_loop_started")
        self.assertEqual(payload["actor"], "system")
        self.assertEqual(payload["message"], "Automatic diagnosis loop started")
        self.assertIsNotNone(payload["data"])
        self.assertEqual(payload["data"]["run_id"], "auto-inc-123-20260621000000")
        self.assertEqual(payload["data"]["collector_run_id"], "collector-001")

    def test_completed_event_serializes(self) -> None:
        """DIAGNOSIS_LOOP_COMPLETED event serializes to correct payload."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            checks_requested=3,
            checks_run=2,
            checks_rejected=1,
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        payload = build_incident_event_payload(event)

        self.assertEqual(payload["event_type"], "diagnosis_loop_completed")
        self.assertEqual(payload["data"]["checks_requested"], 3)
        self.assertEqual(payload["data"]["checks_run"], 2)
        self.assertEqual(payload["data"]["checks_rejected"], 1)

    def test_failed_event_serializes(self) -> None:
        """DIAGNOSIS_LOOP_FAILED event serializes to correct payload."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_failed(
            incident,
            run_id="auto-inc-123-20260621000000",
            unavailable_reason="not_eligible",
            occurred_at=TEST_TIME_3,
        )

        event = updated.events[0]
        payload = build_incident_event_payload(event)

        self.assertEqual(payload["event_type"], "diagnosis_loop_failed")
        self.assertEqual(payload["data"]["unavailable_reason"], "not_eligible")


class TestDiagnosisLoopEventSafety(unittest.TestCase):
    """Test safety constraints for diagnosis loop events."""

    def test_no_kubernetes_mutation_in_metadata(self) -> None:
        """Event metadata must not indicate Kubernetes mutation capability."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        data = event.data or {}

        self.assertNotIn("kubectl", data)
        self.assertNotIn("helm", data)
        self.assertNotIn("mutation", data)
        self.assertNotIn("apply", data)
        self.assertNotIn("delete", data)
        self.assertNotIn("patch", data)

    def test_no_remediation_in_metadata(self) -> None:
        """Event metadata must not indicate remediation capability."""
        incident = make_test_incident()

        updated = mark_diagnosis_loop_completed(
            incident,
            run_id="auto-inc-123-20260621000000",
            collector_run_id="collector-001",
            occurred_at=TEST_TIME_2,
        )

        event = updated.events[0]
        data = event.data or {}

        self.assertTrue(data.get("no_remediation_attempted", False))

    def test_read_only_flag_always_true(self) -> None:
        """All diagnosis loop events must have read_only=True."""
        incident = make_test_incident()

        updated1 = mark_diagnosis_loop_started(
            incident,
            run_id="run-1",
            collector_run_id="collector-1",
            occurred_at=TEST_TIME_1,
        )
        self.assertTrue(updated1.events[0].data["read_only"])

        updated2 = mark_diagnosis_loop_completed(
            updated1,
            run_id="run-2",
            collector_run_id="collector-2",
            occurred_at=TEST_TIME_2,
        )
        self.assertTrue(updated2.events[1].data["read_only"])

        updated3 = mark_diagnosis_loop_failed(
            updated2,
            run_id="run-3",
            unavailable_reason="test",
            occurred_at=TEST_TIME_3,
        )
        self.assertTrue(updated3.events[2].data["read_only"])


if __name__ == "__main__":
    unittest.main()
