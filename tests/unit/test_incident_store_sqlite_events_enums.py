"""Tests for SQLite incident store events - enum types.

This module tests:
- IncidentEventType enum values
- IncidentEventActor enum values
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_store_sqlite_events import (
    IncidentEventActor,
    IncidentEventType,
)


class TestIncidentEventType(unittest.TestCase):
    """Tests for IncidentEventType enum."""

    def test_all_event_types_are_strings(self) -> None:
        """All event type values should be strings."""
        for event_type in IncidentEventType:
            self.assertIsInstance(event_type.value, str)

    def test_event_type_values(self) -> None:
        """Event type values match expected strings."""
        self.assertEqual(IncidentEventType.OPENED, "incident.opened")
        self.assertEqual(IncidentEventType.SIGNAL_OBSERVED, "incident.signal_observed")
        self.assertEqual(IncidentEventType.UPDATED, "incident.updated")
        self.assertEqual(
            IncidentEventType.COLLECTING_EVIDENCE_STARTED, "incident.collecting_evidence_started"
        )
        self.assertEqual(IncidentEventType.READY_FOR_REVIEW, "incident.ready_for_review")
        self.assertEqual(IncidentEventType.INVESTIGATION_STARTED, "incident.investigation_started")
        self.assertEqual(IncidentEventType.SUPPRESSED, "incident.suppressed")
        self.assertEqual(IncidentEventType.MARKED_DUPLICATE, "incident.marked_duplicate")
        self.assertEqual(IncidentEventType.RESOLVED, "incident.resolved")
        self.assertEqual(IncidentEventType.EVIDENCE_ATTACHED, "incident.evidence_attached")
        self.assertEqual(IncidentEventType.DIAGNOSIS_LOOP_STARTED, "incident.diagnosis_loop_started")
        self.assertEqual(
            IncidentEventType.DIAGNOSIS_LOOP_COMPLETED, "incident.diagnosis_loop_completed"
        )
        self.assertEqual(IncidentEventType.DIAGNOSIS_LOOP_FAILED, "incident.diagnosis_loop_failed")
        self.assertEqual(IncidentEventType.IMPORTED, "incident.imported")

    def test_event_type_count(self) -> None:
        """All expected event types are present."""
        expected_types = [
            "incident.opened",
            "incident.signal_observed",
            "incident.updated",
            "incident.collecting_evidence_started",
            "incident.ready_for_review",
            "incident.investigation_started",
            "incident.suppressed",
            "incident.marked_duplicate",
            "incident.resolved",
            "incident.evidence_attached",
            "incident.diagnosis_loop_started",
            "incident.diagnosis_loop_completed",
            "incident.diagnosis_loop_failed",
            "incident.imported",
        ]
        self.assertEqual(len(IncidentEventType), len(expected_types))
        actual_values = {et.value for et in IncidentEventType}
        self.assertEqual(actual_values, set(expected_types))


class TestIncidentEventActor(unittest.TestCase):
    """Tests for IncidentEventActor enum."""

    def test_all_actors_are_strings(self) -> None:
        """All actor values should be strings."""
        for actor in IncidentEventActor:
            self.assertIsInstance(actor.value, str)

    def test_actor_values(self) -> None:
        """Actor values match expected strings."""
        self.assertEqual(IncidentEventActor.SYSTEM, "system")
        self.assertEqual(IncidentEventActor.USER, "user")
        self.assertEqual(IncidentEventActor.SCHEDULER, "scheduler")
        self.assertEqual(IncidentEventActor.ALERT, "alert")
        self.assertEqual(IncidentEventActor.COLLECTOR, "collector")

    def test_actor_count(self) -> None:
        """All expected actors are present."""
        expected_actors = ["system", "user", "scheduler", "alert", "collector"]
        self.assertEqual(len(IncidentEventActor), len(expected_actors))
        actual_values = {a.value for a in IncidentEventActor}
        self.assertEqual(actual_values, set(expected_actors))


if __name__ == "__main__":
    unittest.main()
