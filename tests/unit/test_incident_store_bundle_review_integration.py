"""Tests for incident store bundle-to-review-packet integration.

Tests:
- find_incidents_by_bundle_id returns matching incidents
- find_incidents_by_bundle_id excludes protected statuses (SUPPRESSED, DUPLICATE, RESOLVED)
- mark_ready_for_review_by_bundle_id updates matching incidents
- mark_ready_for_review_by_bundle_id excludes protected statuses
- review packet generation marks incident ready_for_review
- review packet generation stores review_packet_id
- review packet generation does not affect suppressed/duplicate/resolved incidents
- review packet generation failure does not mutate incident state
- no matching incident is harmless
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.api_incident_review_packet import (
    IncidentReviewPacketRequest,
    handle_incident_review_packet,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus, ReviewPacketStatus
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_store_fixtures import TEST_TIME_1, make_candidate


class TestFindIncidentsByBundleId(unittest.TestCase):
    """Test find_incidents_by_bundle_id method."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_find_incidents_by_bundle_id_returns_matching(self) -> None:
        """find_incidents_by_bundle_id must return incidents with matching bundle_id."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )

        matching = self._test_store.find_incidents_by_bundle_id("bundle-123")

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].incident_id, self._test_store.list_incidents()[0].incident_id)

    def test_find_incidents_by_bundle_id_excludes_suppressed(self) -> None:
        """find_incidents_by_bundle_id must not return SUPPRESSED incidents."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )
        incident_id = self._test_store.list_incidents()[0].incident_id
        self._test_store.suppress(incident_id, "known issue")

        matching = self._test_store.find_incidents_by_bundle_id("bundle-123")

        self.assertEqual(len(matching), 0)

    def test_find_incidents_by_bundle_id_excludes_duplicate(self) -> None:
        """find_incidents_by_bundle_id must not return DUPLICATE incidents."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )
        incident_id = self._test_store.list_incidents()[0].incident_id
        self._test_store.mark_duplicate(incident_id, "primary-incident")

        matching = self._test_store.find_incidents_by_bundle_id("bundle-123")

        self.assertEqual(len(matching), 0)

    def test_find_incidents_by_bundle_id_no_match_returns_empty(self) -> None:
        """find_incidents_by_bundle_id returns empty tuple when no match."""
        matching = self._test_store.find_incidents_by_bundle_id("nonexistent-bundle")

        self.assertEqual(len(matching), 0)


class TestMarkReadyForReviewByBundleId(unittest.TestCase):
    """Test mark_ready_for_review_by_bundle_id method."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_mark_ready_for_review_by_bundle_id_updates_matching(self) -> None:
        """mark_ready_for_review_by_bundle_id must update incidents with matching bundle_id."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )
        incident_id = self._test_store.list_incidents()[0].incident_id

        updated = self._test_store.mark_ready_for_review_by_bundle_id(
            "bundle-123", "review-456"
        )

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0].status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated[0].review_packet.status == ReviewPacketStatus.AVAILABLE)
        self.assertEqual(updated[0].review_packet.id, "review-456")

        # Verify stored incident is updated
        stored = self._test_store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(stored.review_packet.status == ReviewPacketStatus.AVAILABLE)

    def test_mark_ready_for_review_by_bundle_id_excludes_suppressed(self) -> None:
        """mark_ready_for_review_by_bundle_id must not update SUPPRESSED incidents."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )
        incident_id = self._test_store.list_incidents()[0].incident_id
        self._test_store.suppress(incident_id, "known issue")

        updated = self._test_store.mark_ready_for_review_by_bundle_id(
            "bundle-123", "review-456"
        )

        self.assertEqual(len(updated), 0)

        # Verify suppressed incident is unchanged
        stored = self._test_store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.SUPPRESSED)
        self.assertFalse(stored.review_packet.status == ReviewPacketStatus.AVAILABLE)

    def test_mark_ready_for_review_by_bundle_id_excludes_duplicate(self) -> None:
        """mark_ready_for_review_by_bundle_id must not update DUPLICATE incidents."""
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id="bundle-123"
        )
        incident_id = self._test_store.list_incidents()[0].incident_id
        self._test_store.mark_duplicate(incident_id, "primary-incident")

        updated = self._test_store.mark_ready_for_review_by_bundle_id(
            "bundle-123", "review-456"
        )

        self.assertEqual(len(updated), 0)

        # Verify duplicate incident is unchanged
        stored = self._test_store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.DUPLICATE)
        self.assertFalse(stored.review_packet.status == ReviewPacketStatus.AVAILABLE)

    def test_mark_ready_for_review_by_bundle_id_no_match_returns_empty(self) -> None:
        """mark_ready_for_review_by_bundle_id returns empty tuple when no match."""
        updated = self._test_store.mark_ready_for_review_by_bundle_id(
            "nonexistent-bundle", "review-456"
        )

        self.assertEqual(len(updated), 0)


class TestReviewPacketGenerationUpdatesIncidentState(unittest.TestCase):
    """Test that review packet generation updates incident state."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def _make_bundle_with_bundle_id(self, bundle_id: str) -> dict:
        """Create a valid test bundle with given bundle_id."""
        return {
            "metadata": {
                "bundle_id": bundle_id,
                "captured_at": "2024-01-15T12:00:00+00:00",
                "namespace": "default",
                "since_hours": 2,
                "context": None,
                "total_pods": 5,
                "total_events": 3,
                "total_deployments": 2,
                "failing_pods_count": 2,
                "symptoms_count": 3,
                "candidates_count": 1,
            },
            "pods": [
                {
                    "name": "crashloop-pod",
                    "namespace": "default",
                    "phase": "Running",
                    "health_status": "crash_loop",
                    "restart_count": 5,
                    "node": "node-1",
                    "image_refs": ["broken:v1"],
                    "reason": "CrashLoopBackOff",
                    "message": "Back-off 5m40s restarting",
                    "is_failing": True,
                },
            ],
            "events": [
                {
                    "namespace": "default",
                    "name": "event-1",
                    "type": "Warning",
                    "reason": "BackOff",
                    "message": "Back-off restarting container crashloop-pod",
                    "involved_object_kind": "Pod",
                    "involved_object_name": "crashloop-pod",
                    "count": 3,
                    "last_timestamp": "2024-01-15T12:00:00Z",
                },
            ],
            "deployments": [
                {
                    "name": "nginx-deployment",
                    "namespace": "default",
                    "replicas": 3,
                    "available_replicas": 3,
                    "ready_replicas": 3,
                    "updated_replicas": 3,
                    "available": True,
                },
            ],
            "symptoms": [
                {
                    "symptom_type": "crash_loop",
                    "pod_name": "crashloop-pod",
                    "message": "Pod crashloop-pod in CrashLoopBackOff",
                    "severity": "error",
                },
            ],
            "collection_errors": [],
        }

    def test_review_packet_generation_marks_incident_ready_for_review(self) -> None:
        """Review packet generation must mark matching incident ready_for_review."""
        bundle_id = "test-bundle-001"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        # Add incident with matching bundle_id
        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )

        # Generate review packet
        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        response = handle_incident_review_packet(request)

        # Verify response includes incident updates
        self.assertIsNotNone(response.incident_updates)
        self.assertEqual(response.incident_updates["ready_for_review_count"], 1)
        self.assertEqual(len(response.incident_updates["incident_ids"]), 1)

        # Verify incident state is updated
        incident_id = response.incident_updates["incident_ids"][0]
        incident = self._test_store.get_incident(incident_id)
        self.assertIsNotNone(incident)
        self.assertEqual(incident.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(incident.review_packet.status == ReviewPacketStatus.AVAILABLE)
        self.assertEqual(incident.review_packet.id, bundle_id)

    def test_review_packet_generation_stores_review_packet_id(self) -> None:
        """Review packet generation must store review_packet_id on incident."""
        bundle_id = "test-bundle-002"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )

        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        response = handle_incident_review_packet(request)

        self.assertIsNotNone(response.incident_updates)
        incident_id = response.incident_updates["incident_ids"][0]
        incident = self._test_store.get_incident(incident_id)

        # review_packet_id should be set to bundle_id
        self.assertEqual(incident.review_packet.id, bundle_id)

    def test_incident_list_api_returns_review_packet_available_true(self) -> None:
        """Incident list API must return review_packet_available=true after review packet generation."""
        from k8s_diag_agent.collect.api_incident_reads import handle_list_incidents

        bundle_id = "test-bundle-003"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )

        # Generate review packet
        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        handle_incident_review_packet(request)

        # List incidents via API
        result = handle_list_incidents()

        self.assertEqual(len(result["incidents"]), 1)
        incident = result["incidents"][0]
        self.assertTrue(incident["review_packet"]["status"] == "available")
        self.assertEqual(incident["review_packet"]["id"], bundle_id)
        self.assertEqual(incident["status"], IncidentStatus.READY_FOR_REVIEW.value)

    def test_no_matching_incident_is_harmless(self) -> None:
        """Review packet generation with no matching incident must still succeed."""
        bundle_id = "test-bundle-004"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        # Do NOT add any incident with this bundle_id

        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        response = handle_incident_review_packet(request)

        # Should still return success with empty incident_updates
        self.assertEqual(response.bundle_id, bundle_id)
        self.assertNotEqual(response.packet, "")
        self.assertIsNotNone(response.incident_updates)
        self.assertEqual(response.incident_updates["ready_for_review_count"], 0)
        self.assertEqual(response.incident_updates["incident_ids"], [])

    def test_suppressed_incident_not_reactivated(self) -> None:
        """Review packet generation must not reactivate SUPPRESSED incidents."""
        bundle_id = "test-bundle-005"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )
        incident_id = self._test_store.list_incidents()[0].incident_id

        # Mark as suppressed before review packet generation
        self._test_store.suppress(incident_id, "known issue")

        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        response = handle_incident_review_packet(request)

        # Verify incident is still suppressed
        incident = self._test_store.get_incident(incident_id)
        self.assertEqual(incident.status, IncidentStatus.SUPPRESSED)
        self.assertFalse(incident.review_packet.status == ReviewPacketStatus.AVAILABLE)

        # Verify incident_updates does not include suppressed incidents
        self.assertEqual(response.incident_updates["ready_for_review_count"], 0)

    def test_duplicate_incident_not_reactivated(self) -> None:
        """Review packet generation must not reactivate DUPLICATE incidents."""
        bundle_id = "test-bundle-006"
        bundle = self._make_bundle_with_bundle_id(bundle_id)

        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )
        incident_id = self._test_store.list_incidents()[0].incident_id

        # Mark as duplicate before review packet generation
        self._test_store.mark_duplicate(incident_id, "primary-incident")

        request = IncidentReviewPacketRequest(bundle=bundle, format="markdown")
        _response = handle_incident_review_packet(request)

        # Verify incident is still duplicate
        # Verify incident_updates does not include duplicate incidents
        self.assertEqual(_response.incident_updates["ready_for_review_count"], 0)
        incident = self._test_store.get_incident(incident_id)
        self.assertEqual(incident.status, IncidentStatus.DUPLICATE)
        self.assertFalse(incident.review_packet.status == ReviewPacketStatus.AVAILABLE)

    def test_review_packet_generation_failure_does_not_mutate_state(self) -> None:
        """Review packet generation failure must not mutate incident state."""
        bundle_id = "test-bundle-007"
        invalid_bundle = {"pods": []}  # Missing metadata, will fail validation

        candidate = make_candidate(name="crashloop-pod")
        self._test_store.promote_candidates(
            [candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id
        )

        # Store original state
        incident_id = self._test_store.list_incidents()[0].incident_id
        original_status = self._test_store.get_incident(incident_id).status

        request = IncidentReviewPacketRequest(bundle=invalid_bundle, format="markdown")
        response = handle_incident_review_packet(request)

        # Verify response is an error
        self.assertIsNotNone(response.error)

        # Verify incident state is unchanged
        incident = self._test_store.get_incident(incident_id)
        self.assertEqual(incident.status, original_status)
        self.assertFalse(incident.review_packet.status == ReviewPacketStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()