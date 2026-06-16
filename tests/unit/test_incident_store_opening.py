"""Tests for creating new incidents from candidates.

Tests:
- New candidate → new incident
- Incident fields populated correctly
- Signal capture timestamp behavior
- Multiple distinct candidates create distinct incidents
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, make_candidate, make_store

from k8s_diag_agent.collect.incident_candidates import CandidateClass
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


class TestPromoteOneCandidate(unittest.TestCase):
    """Test promoting a single candidate to an open incident."""

    def test_promotes_one_candidate_to_open_incident(self) -> None:
        """A single candidate must produce an incident in OPEN state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.OPEN)
        self.assertEqual(incidents[0].namespace, "default")
        self.assertEqual(incidents[0].object_name, "crashloop-pod")
        self.assertEqual(incidents[0].first_observed_at, TEST_TIME_1)
        self.assertEqual(incidents[0].last_observed_at, TEST_TIME_1)

    def test_promoted_incident_has_signals(self) -> None:
        """Promoted incident must include signals from the candidate."""
        store = make_store()
        candidate = make_candidate(name="test-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        self.assertEqual(len(incidents[0].signals), 1)
        self.assertEqual(incidents[0].signals[0].source, "pod")


class TestMultipleDistinctCandidates(unittest.TestCase):
    """Test that multiple distinct candidates create multiple incidents."""

    def test_multiple_distinct_candidates_create_multiple_incidents(self) -> None:
        """Distinct candidates must produce distinct incidents."""
        store = make_store()
        candidate1 = make_candidate(name="crashloop-pod-1", namespace="default")
        candidate2 = make_candidate(name="crashloop-pod-2", namespace="default")

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)

    def test_different_namespace_creates_different_incident(self) -> None:
        """Different namespaces must create different incidents."""
        store = make_store()
        candidate1 = make_candidate(name="myapp", namespace="default")
        candidate2 = make_candidate(name="myapp", namespace="k9b")

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)

    def test_different_candidate_class_creates_different_incident(self) -> None:
        """Different candidate classes must create different incidents."""
        store = make_store()
        candidate1 = make_candidate(
            name="myapp",
            candidate_class=CandidateClass.CRASH_LOOP,
        )
        candidate2 = make_candidate(
            name="myapp",
            candidate_class=CandidateClass.IMAGE_PULL_ERROR,
        )

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)


if __name__ == "__main__":
    unittest.main()
