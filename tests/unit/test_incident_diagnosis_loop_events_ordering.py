"""Tests for diagnosis loop event chronological ordering.

These tests verify:
1. DIAGNOSIS_LOOP_STARTED should come before DIAGNOSIS_LOOP_COMPLETED
2. DIAGNOSIS_LOOP_STARTED should come before DIAGNOSIS_LOOP_FAILED
3. Events should be sorted by occurred_at timestamp

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import IncidentEventType
from k8s_diag_agent.collect.incident_transitions import (
    mark_diagnosis_loop_completed,
    mark_diagnosis_loop_failed,
    mark_diagnosis_loop_started,
)
from tests.unit.incident_diagnosis_loop_event_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    TEST_TIME_3,
    make_test_incident,
)


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


if __name__ == "__main__":
    unittest.main()
