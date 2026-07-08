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

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus, ReviewPacketStatus


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
        self.assertEqual(updated.latest_snapshot_bundle_id, "bundle-123")

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
        """mark_ready_for_review must update the incident in the store.

        Requires COLLECTING_EVIDENCE state first per domain invariant:
        open -> collecting_evidence -> ready_for_review
        """
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        # First transition: OPEN -> COLLECTING_EVIDENCE
        incident = store.mark_collecting_evidence(incident_id, bundle_id)
        self.assertIsNotNone(incident)
        self.assertEqual(incident.status, IncidentStatus.COLLECTING_EVIDENCE)

        # Second transition: COLLECTING_EVIDENCE -> READY_FOR_REVIEW
        updated = store.mark_ready_for_review(incident_id, "review-456")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertEqual(updated.review_packet.status, ReviewPacketStatus.AVAILABLE)
        self.assertEqual(updated.review_packet.id, "review-456")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.READY_FOR_REVIEW)

    def test_ready_for_review_without_packet_id(self) -> None:
        """mark_ready_for_review must work without review_packet_id.

        Requires COLLECTING_EVIDENCE state first per domain invariant:
        open -> collecting_evidence -> ready_for_review
        """
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        # First transition: OPEN -> COLLECTING_EVIDENCE
        incident = store.mark_collecting_evidence(incident_id, bundle_id)
        self.assertIsNotNone(incident)
        self.assertEqual(incident.status, IncidentStatus.COLLECTING_EVIDENCE)

        # Second transition: COLLECTING_EVIDENCE -> READY_FOR_REVIEW (without packet_id)
        updated = store.mark_ready_for_review(incident_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        # Without explicit packet ID, review_packet stays not-generated
        self.assertEqual(updated.review_packet.status, ReviewPacketStatus.NOT_GENERATED)


if __name__ == "__main__":
    unittest.main()
