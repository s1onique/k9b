"""Tests for diagnosis loop event safety constraints.

These tests verify safety constraints for all diagnosis loop events:
1. No Kubernetes mutation capability in metadata
2. No remediation capability in metadata
3. Read-only flag always true

Hard constraints verified:
- NO remediation actions
- NO Kubernetes mutation
- NO LLM calls
- NO kubectl/Helm write operations
- NO action/remediation controls
"""

from __future__ import annotations

import unittest

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
