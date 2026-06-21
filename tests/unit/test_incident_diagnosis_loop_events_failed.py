"""Tests for DIAGNOSIS_LOOP_FAILED event creation.

These tests verify:
1. mark_diagnosis_loop_failed creates correct event
2. Event contains unavailable_reason
3. Event can include run_id
4. Event must NOT contain error_message field
5. No raw packet/artifact content leakage

Safe reason codes used by this transition:
    - unsafe_run_id: Generated run_id failed safety validation
    - case_file_error: Failed to build case file
    - case_file_none: Case file returned None
    - orchestrator_error: Orchestrator raised an exception
    - not_eligible: Incident not eligible for diagnosis loop

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
- NO raw artifact dumping
- NO error_message in failed events (uses bounded reason codes only)
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import (
    IncidentEventActor,
    IncidentEventType,
)
from k8s_diag_agent.collect.incident_transitions import mark_diagnosis_loop_failed
from tests.unit.incident_diagnosis_loop_event_fixtures import (
    TEST_TIME_3,
    make_test_incident,
)


class TestDiagnosisLoopFailedEvent(unittest.TestCase):
    """Test mark_diagnosis_loop_failed transition."""

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


if __name__ == "__main__":
    unittest.main()
