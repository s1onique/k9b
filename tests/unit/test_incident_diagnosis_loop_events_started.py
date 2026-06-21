"""Tests for DIAGNOSIS_LOOP_STARTED event creation.

These tests verify:
1. mark_diagnosis_loop_started creates correct event
2. Event contains safe metadata only
3. No raw packet/artifact content leakage

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
from k8s_diag_agent.collect.incident_transitions import mark_diagnosis_loop_started
from tests.unit.incident_diagnosis_loop_event_fixtures import (
    TEST_TIME_1,
    make_test_incident,
)


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


if __name__ == "__main__":
    unittest.main()
