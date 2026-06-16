"""Tests for incident status transitions.

Tests:
- mark_collecting_evidence
- mark_ready_for_review
- bundle_id/review_packet_id behavior
- missing incident returns None
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, make_candidate, make_store

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


class TestCollectingEvidenceTransition(unittest.TestCase):
    """Test collecting_evidence state transition."""

    def test_collecting_evidence_transition_updates_stored_incident(self) -> None:
        """mark_collecting_evidence must update the incident in the store."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_collecting_evidence(incident_id, "bundle-123")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(updated.snapshot_bundle_id, "bundle-123")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.COLLECTING_EVIDENCE)

    def test_collecting_evidence_returns_none_for_unknown(self) -> None:
        """mark_collecting_evidence must return None for unknown ID."""
        store = make_store()

        result = store.mark_collecting_evidence("unknown-id", "bundle-123")

        self.assertIsNone(result)


class TestReadyForReviewTransition(unittest.TestCase):
    """Test ready_for_review state transition."""

    def test_ready_for_review_transition_updates_stored_incident(self) -> None:
        """mark_ready_for_review must update the incident in the store."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_ready_for_review(incident_id, "review-456")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertEqual(updated.review_packet_id, "review-456")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.READY_FOR_REVIEW)

    def test_ready_for_review_without_packet_id(self) -> None:
        """mark_ready_for_review must work without review_packet_id."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_ready_for_review(incident_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)


if __name__ == "__main__":
    unittest.main()
