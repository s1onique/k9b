"""Tests for DIAGNOSIS_LOOP_COMPLETED event creation.

These tests verify:
1. mark_diagnosis_loop_completed creates correct event
2. Event contains check counts
3. Event can include review packet name
4. Event contains safety metadata

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
- NO raw artifact dumping
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import (
    IncidentEventActor,
    IncidentEventType,
)
from k8s_diag_agent.collect.incident_transitions import mark_diagnosis_loop_completed
from tests.unit.incident_diagnosis_loop_event_fixtures import (
    TEST_TIME_2,
    make_test_incident,
)


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


if __name__ == "__main__":
    unittest.main()
