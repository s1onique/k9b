"""Tests for candidate → incident opening and merge behavior.

Covers:
- candidate → incident creation
- merge behavior (no new identity)
- signal inheritance
- evidence_needed inheritance
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_candidates import CandidateClass
from k8s_diag_agent.collect.incident_lifecycle import (
    IncidentStatus,
    merge_candidate_into_incident,
    open_incident_from_candidate,
)
from tests.unit.incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate


class TestCandidateToOpenTransition(unittest.TestCase):
    """Test candidate → open transition."""

    def test_opens_incident_from_crashloop_candidate(self) -> None:
        """A crash_loop candidate must produce an incident in OPEN state."""
        candidate = make_candidate(
            name="crashloop-pod",
            namespace="default",
            candidate_class=CandidateClass.CRASH_LOOP,
        )
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(incident.status, IncidentStatus.OPEN)
        self.assertEqual(incident.severity, "error")
        self.assertEqual(incident.candidate_class, "crash_loop")
        self.assertEqual(incident.namespace, "default")
        self.assertEqual(incident.object_name, "crashloop-pod")
        self.assertEqual(incident.first_observed_at, observed_at)
        self.assertEqual(incident.last_observed_at, observed_at)

    def test_incident_inherits_signals_from_candidate(self) -> None:
        """Incident must include signals from the candidate."""
        candidate = make_candidate(name="test-pod")
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(len(incident.signals), 1)
        self.assertEqual(incident.signals[0].source, "pod")
        self.assertEqual(incident.signals[0].reason, "CrashLoopBackOff")

    def test_incident_inherits_evidence_needed_from_candidate(self) -> None:
        """Incident must include evidence_needed from the candidate."""
        candidate = make_candidate(name="test-pod")
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(incident.evidence_needed, ["pod_logs", "pod_describe"])


class TestMergeBehavior(unittest.TestCase):
    """Test that repeated same candidate updates last_observed_at, does not create new identity."""

    def test_merge_updates_last_observed_at(self) -> None:
        """Merging must update last_observed_at."""
        candidate = make_candidate(name="crashloop-pod")

        incident1 = open_incident_from_candidate(candidate, TEST_TIME_1)
        incident2 = merge_candidate_into_incident(incident1, candidate, TEST_TIME_2)

        self.assertEqual(incident2.last_observed_at, TEST_TIME_2)
        self.assertEqual(incident2.first_observed_at, TEST_TIME_1)

    def test_merge_does_not_change_incident_id(self) -> None:
        """Merging must NOT create a new incident identity."""
        candidate = make_candidate(name="crashloop-pod")

        incident1 = open_incident_from_candidate(candidate, TEST_TIME_1)
        incident2 = merge_candidate_into_incident(incident1, candidate, TEST_TIME_2)

        self.assertEqual(incident2.incident_id, incident1.incident_id)

    def test_merge_appends_signals(self) -> None:
        """Merging must append new signals."""
        candidate = make_candidate(name="crashloop-pod")

        incident1 = open_incident_from_candidate(candidate, TEST_TIME_1)
        incident2 = merge_candidate_into_incident(incident1, candidate, TEST_TIME_2)

        self.assertEqual(len(incident2.signals), 2)
        self.assertEqual(incident1.signals[0].captured_at, TEST_TIME_1)
        self.assertEqual(incident2.signals[1].captured_at, TEST_TIME_2)


if __name__ == "__main__":
    unittest.main()
