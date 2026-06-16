"""Tests for listing and retrieving incidents.

Tests:
- list_incidents returns deterministic ordering
- list_incidents with status filters
- get_incident existing/missing
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, make_candidate, make_store

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


class TestListIncidentsOrdering(unittest.TestCase):
    """Test deterministic ordering of list_incidents."""

    def test_list_incidents_returns_deterministic_ordering(self) -> None:
        """list_incidents must return incidents sorted by incident_id."""
        store = make_store()
        # Add incidents in non-sorted order
        cand_z = make_candidate(name="z-pod", namespace="default")
        cand_a = make_candidate(name="a-pod", namespace="default")
        cand_m = make_candidate(name="m-pod", namespace="default")

        store.promote_candidates([cand_z, cand_a, cand_m], TEST_TIME_1)

        incidents = store.list_incidents()

        # Should be sorted alphabetically by incident_id
        incident_ids = [i.incident_id for i in incidents]
        self.assertEqual(incident_ids, sorted(incident_ids))

    def test_list_incidents_with_status_filter(self) -> None:
        """list_incidents must filter by status correctly."""
        store = make_store()
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        # Mark one as suppressed
        incidents = store.list_incidents()
        store.suppress(incidents[0].incident_id, "known issue")

        # Filter by OPEN status
        open_incidents = store.list_incidents(status=IncidentStatus.OPEN)
        self.assertEqual(len(open_incidents), 1)

        # Filter by SUPPRESSED status
        suppressed_incidents = store.list_incidents(status=IncidentStatus.SUPPRESSED)
        self.assertEqual(len(suppressed_incidents), 1)

        # Filter by non-matching status
        investigating_incidents = store.list_incidents(status=IncidentStatus.INVESTIGATING)
        self.assertEqual(len(investigating_incidents), 0)


class TestGetIncident(unittest.TestCase):
    """Test get_incident retrieval."""

    def test_get_incident_returns_expected_record(self) -> None:
        """get_incident must return the correct incident."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        retrieved = store.get_incident(incident_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.incident_id, incident_id)
        self.assertEqual(retrieved.namespace, "default")
        self.assertEqual(retrieved.object_name, "crashloop-pod")

    def test_get_incident_returns_none_for_unknown_id(self) -> None:
        """get_incident must return None for unknown ID."""
        store = make_store()

        retrieved = store.get_incident("unknown-id")

        self.assertIsNone(retrieved)


if __name__ == "__main__":
    unittest.main()
