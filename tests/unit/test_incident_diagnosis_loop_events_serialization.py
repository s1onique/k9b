"""Tests for diagnosis loop event API serialization.

These tests verify that diagnosis loop events serialize correctly for API consumption.

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_transitions import (
    mark_diagnosis_loop_completed,
    mark_diagnosis_loop_failed,
    mark_diagnosis_loop_started,
)
from k8s_diag_agent.ui.api_incident_reads import build_incident_event_payload
from tests.unit.incident_diagnosis_loop_event_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    TEST_TIME_3,
    make_test_incident,
)


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


if __name__ == "__main__":
    unittest.main()
