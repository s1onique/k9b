"""Tests for incident state transitions.

Covers:
- collecting evidence
- ready for review
- investigating (placeholder)
- resolved (placeholder)
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentStatus,
    mark_collecting_evidence,
    mark_ready_for_review,
)


def make_transition_incident(
    status: IncidentStatus = IncidentStatus.OPEN,
    snapshot_bundle_id: str | None = None,
) -> Incident:
    """Create an incident ready for transition testing."""
    now = datetime.now(UTC)
    return Incident(
        incident_id="test",
        source_candidate_id="test",
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="crash_loop",
        severity="error",
        status=status,
        first_observed_at=now,
        last_observed_at=now,
        snapshot_bundle_id=snapshot_bundle_id,
    )


class TestCollectingEvidenceTransition(unittest.TestCase):
    """Test collecting_evidence state transition."""

    def test_collecting_evidence_attaches_snapshot_bundle_id(self) -> None:
        """mark_collecting_evidence must set snapshot_bundle_id."""
        incident = make_transition_incident(status=IncidentStatus.OPEN)

        updated = mark_collecting_evidence(incident, "bundle-123")

        self.assertEqual(updated.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(updated.snapshot_bundle_id, "bundle-123")


class TestReadyForReviewTransition(unittest.TestCase):
    """Test ready_for_review state transition."""

    def test_ready_for_review_marks_packet_availability(self) -> None:
        """mark_ready_for_review must set review_packet_available."""
        incident = make_transition_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
            snapshot_bundle_id="bundle-123",
        )

        updated = mark_ready_for_review(incident, "review-packet-456")

        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertEqual(updated.review_packet_id, "review-packet-456")

    def test_ready_for_review_with_default_id(self) -> None:
        """mark_ready_for_review must work without review_packet_id."""
        incident = make_transition_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
        )

        updated = mark_ready_for_review(incident)

        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertIsNone(updated.review_packet_id)


if __name__ == "__main__":
    unittest.main()
