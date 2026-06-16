"""Tests for incident review packet integration.

Covers:
- snapshot_bundle_id availability
- review_packet_id availability
- review_packet_available flag
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


def make_review_packet_incident(
    status: IncidentStatus = IncidentStatus.OPEN,
    snapshot_bundle_id: str | None = None,
    review_packet_id: str | None = None,
    review_packet_available: bool = False,
) -> Incident:
    """Create an incident for review packet testing."""
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
        review_packet_id=review_packet_id,
        review_packet_available=review_packet_available,
    )


class TestSnapshotBundleId(unittest.TestCase):
    """Test snapshot_bundle_id attachment and preservation."""

    def test_collecting_evidence_sets_snapshot_bundle_id(self) -> None:
        """mark_collecting_evidence must set snapshot_bundle_id."""
        incident = make_review_packet_incident(status=IncidentStatus.OPEN)

        updated = mark_collecting_evidence(incident, "bundle-abc")

        self.assertEqual(updated.snapshot_bundle_id, "bundle-abc")

    def test_snapshot_bundle_id_preserved_after_ready_for_review(self) -> None:
        """Snapshot bundle ID must be preserved through ready_for_review."""
        incident = make_review_packet_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
            snapshot_bundle_id="bundle-xyz",
        )

        updated = mark_ready_for_review(incident, "review-123")

        self.assertEqual(updated.snapshot_bundle_id, "bundle-xyz")


class TestReviewPacketAvailability(unittest.TestCase):
    """Test review_packet availability flags."""

    def test_ready_for_review_sets_review_packet_available(self) -> None:
        """mark_ready_for_review must set review_packet_available to True."""
        incident = make_review_packet_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
            snapshot_bundle_id="bundle-123",
        )

        updated = mark_ready_for_review(incident, "review-packet-456")

        self.assertTrue(updated.review_packet_available)

    def test_review_packet_id_set_when_provided(self) -> None:
        """review_packet_id must be set when provided."""
        incident = make_review_packet_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
            snapshot_bundle_id="bundle-123",
        )

        updated = mark_ready_for_review(incident, "review-packet-456")

        self.assertEqual(updated.review_packet_id, "review-packet-456")

    def test_review_packet_id_none_when_not_provided(self) -> None:
        """review_packet_id must be None when not provided."""
        incident = make_review_packet_incident(
            status=IncidentStatus.COLLECTING_EVIDENCE,
        )

        updated = mark_ready_for_review(incident)

        self.assertIsNone(updated.review_packet_id)


if __name__ == "__main__":
    unittest.main()
