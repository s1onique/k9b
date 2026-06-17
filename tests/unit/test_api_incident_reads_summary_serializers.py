"""Tests for incident summary payload serialization.

These tests verify:
1. Summary payload uses review_packet object
2. Summary payload omits review_packet_available and review_packet_id
3. Summary payload uses latest_snapshot_bundle_id and omits snapshot_bundle_id
4. Count/status/listing serialization tests
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store
from k8s_diag_agent.ui.api_incident_reads import (
    build_incident_summary_payload,
)

from .api_incident_reads_serializer_fixtures import TEST_TIME_1
from .incident_lifecycle_fixtures import (
    make_candidate,
    make_full_incident,
)


class TestBuildIncidentReviewPacketPayload(unittest.TestCase):
    """Test review packet serialization."""

    def test_not_generated_serializes_without_id(self) -> None:
        """Not-generated review packet must not include id."""
        from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketState
        from k8s_diag_agent.ui.api_incident_reads import build_incident_review_packet_payload

        state = ReviewPacketState.not_generated()
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "not_generated")
        self.assertNotIn("id", result)
        self.assertNotIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_available_review_packet_serializes_with_id(self) -> None:
        """Available review packet must include id and generated_at."""
        from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketState
        from k8s_diag_agent.ui.api_incident_reads import build_incident_review_packet_payload

        generated_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = ReviewPacketState.available(id="packet-123", generated_at=generated_at)
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["id"], "packet-123")
        self.assertIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_generating_review_packet_serializes_with_id(self) -> None:
        """Generating review packet must include id."""
        from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketState
        from k8s_diag_agent.ui.api_incident_reads import build_incident_review_packet_payload

        state = ReviewPacketState.generating(id="packet-456")
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "generating")
        self.assertEqual(result["id"], "packet-456")
        self.assertNotIn("generated_at", result)
        self.assertNotIn("error_message", result)

    def test_failed_review_packet_serializes_error_message(self) -> None:
        """Failed review packet must include error_message."""
        from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketState
        from k8s_diag_agent.ui.api_incident_reads import build_incident_review_packet_payload

        state = ReviewPacketState.failed(error_message="LLM unavailable")
        result = build_incident_review_packet_payload(state)

        self.assertEqual(result["status"], "failed")
        self.assertNotIn("id", result)
        self.assertNotIn("generated_at", result)
        self.assertEqual(result["error_message"], "LLM unavailable")


class TestBuildIncidentSummaryPayload(unittest.TestCase):
    """Test summary payload serialization."""

    def test_summary_uses_review_packet_object(self) -> None:
        """Summary payload must use review_packet object."""
        from k8s_diag_agent.collect.incident_review_packet_state import ReviewPacketStatus

        incident = make_full_incident(
            review_packet_status=ReviewPacketStatus.AVAILABLE,
            review_packet_id="packet-abc",
        )
        result = build_incident_summary_payload(incident)

        self.assertIn("review_packet", result)
        self.assertIsInstance(result["review_packet"], dict)
        self.assertEqual(result["review_packet"]["status"], "available")
        self.assertEqual(result["review_packet"]["id"], "packet-abc")

    def test_summary_omits_review_packet_available(self) -> None:
        """Summary payload must NOT include review_packet_available."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("review_packet_available", result)

    def test_summary_omits_review_packet_id(self) -> None:
        """Summary payload must NOT include review_packet_id as top-level field."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("review_packet_id", result)

    def test_summary_uses_latest_snapshot_bundle_id(self) -> None:
        """Summary payload must use latest_snapshot_bundle_id."""
        incident = make_full_incident(
            latest_snapshot_bundle_id="bundle-xyz",
        )
        result = build_incident_summary_payload(incident)

        self.assertIn("latest_snapshot_bundle_id", result)
        self.assertEqual(result["latest_snapshot_bundle_id"], "bundle-xyz")

    def test_summary_omits_snapshot_bundle_id(self) -> None:
        """Summary payload must NOT include snapshot_bundle_id."""
        incident = make_full_incident(
            latest_snapshot_bundle_id="bundle-xyz",
        )
        result = build_incident_summary_payload(incident)

        self.assertNotIn("snapshot_bundle_id", result)

    def test_summary_includes_required_fields(self) -> None:
        """Summary payload must include all required fields."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        required_fields = [
            "incident_id",
            "namespace",
            "object_kind",
            "object_name",
            "raw_object_kind",
            "candidate_class",
            "severity",
            "status",
            "first_observed_at",
            "last_observed_at",
            "signal_count",
            "evidence_count",
            "latest_snapshot_bundle_id",
            "review_packet",
        ]
        for field in required_fields:
            self.assertIn(field, result, f"Missing required field: {field}")

    def test_summary_includes_candidate_class(self) -> None:
        """Summary payload must include candidate_class field."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertIn("candidate_class", result)
        self.assertEqual(result["candidate_class"], "crash_loop")

    def test_summary_does_not_include_suggested_checks(self) -> None:
        """Summary payload must NOT include suggested_checks (detail-only field)."""
        incident = make_full_incident()
        result = build_incident_summary_payload(incident)

        self.assertNotIn("suggested_checks", result)


class TestHandleListIncidentsPayloadShape(unittest.TestCase):
    """Test that handle_list_incidents returns correct payload shape."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Reset incident store after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_list_returns_summary_payload_shape(self) -> None:
        """handle_list_incidents must return summary payload shape."""
        from k8s_diag_agent.collect.api_incident_reads import handle_list_incidents

        # Add incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)

        result = handle_list_incidents()

        self.assertIn("incidents", result)
        self.assertIn("total", result)
        self.assertEqual(result["total"], 1)

        incident = result["incidents"][0]

        # Check summary fields present
        summary_fields = [
            "incident_id",
            "namespace",
            "object_kind",
            "object_name",
            "candidate_class",
            "severity",
            "status",
            "signal_count",
            "evidence_count",
            "latest_snapshot_bundle_id",
            "review_packet",
        ]
        for field in summary_fields:
            self.assertIn(field, incident, f"Missing summary field: {field}")

        # Check forbidden fields absent
        self.assertNotIn("review_packet_available", incident)
        self.assertNotIn("review_packet_id", incident)
        self.assertNotIn("snapshot_bundle_id", incident)

        # Check no detail-only fields
        self.assertNotIn("source_candidate_id", incident)
        self.assertNotIn("signals", incident)
        self.assertNotIn("evidence_needed", incident)
        self.assertNotIn("evidence_links", incident)
        self.assertNotIn("events", incident)


if __name__ == "__main__":
    unittest.main()
