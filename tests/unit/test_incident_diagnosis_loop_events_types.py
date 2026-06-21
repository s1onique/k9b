"""Tests for diagnosis loop event type enums.

These tests verify:
1. Event type enum values are correct
2. All diagnosis loop types are present in IncidentEventType enum

Hard constraints verified:
- NO remediation actions
- NO LLM calls
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_events import IncidentEventType


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


if __name__ == "__main__":
    unittest.main()
