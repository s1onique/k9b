"""Tests for suppression and duplicate transitions.

Tests:
- suppress
- mark_duplicate
- reason/duplicate_of behavior
- missing incident returns None
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, make_candidate, make_store

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


class TestSuppressTransition(unittest.TestCase):
    """Test suppress state transition."""

    def test_suppress_transition_updates_stored_incident(self) -> None:
        """suppress must update the incident in the store."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.suppress(incident_id, "known issue during maintenance")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.SUPPRESSED)
        self.assertEqual(updated.suppressed_reason, "known issue during maintenance")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.SUPPRESSED)

    def test_suppress_returns_none_for_unknown(self) -> None:
        """suppress must return None for unknown ID."""
        store = make_store()

        result = store.suppress("unknown-id", "test")

        self.assertIsNone(result)


class TestDuplicateTransition(unittest.TestCase):
    """Test duplicate state transition."""

    def test_duplicate_transition_updates_stored_incident(self) -> None:
        """mark_duplicate must update the incident in the store."""
        store = make_store()
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)
        incidents = store.list_incidents()

        # Mark incident 2 as duplicate of incident 1
        incident2_id = incidents[1].incident_id
        incident1_id = incidents[0].incident_id

        updated = store.mark_duplicate(incident2_id, incident1_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.DUPLICATE)
        self.assertEqual(updated.duplicate_of, incident1_id)

        # Verify stored incident is updated
        stored = store.get_incident(incident2_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.DUPLICATE)

    def test_duplicate_returns_none_for_unknown(self) -> None:
        """mark_duplicate must return None for unknown ID."""
        store = make_store()

        result = store.mark_duplicate("unknown-id", "primary-incident")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
