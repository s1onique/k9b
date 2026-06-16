"""Tests for incident review packet API endpoint.

These tests verify:
- API route success with mock bundle data
- API route validation
- API response format
- No sentinel patterns in API response
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.api_incident_review_packet import (
    IncidentReviewPacketRequest,
    handle_incident_review_packet,
)

# =============================================================================
# Test Fixtures
# =============================================================================

FAKE_BUNDLE_DATA = {
    "metadata": {
        "bundle_id": "test-bundle-001",
        "captured_at": "2024-01-15T12:00:00+00:00",
        "namespace": "default",
        "since_hours": 2,
        "context": None,
        "total_pods": 5,
        "total_events": 3,
        "total_deployments": 2,
        "failing_pods_count": 2,
        "symptoms_count": 3,
    },
    "pods": [
        {
            "name": "healthy-pod",
            "namespace": "default",
            "phase": "Running",
            "health_status": "running",
            "restart_count": 0,
            "node": "node-1",
            "image_refs": ["nginx:1.21"],
            "reason": None,
            "message": None,
            "is_failing": False,
        },
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


# =============================================================================
# Test Cases
# =============================================================================


class TestHandleIncidentReviewPacket(unittest.TestCase):
    """Test the incident review packet handler with mock data."""

    def test_success_returns_packet(self) -> None:
        """Test that successful request returns a review packet."""
        request = IncidentReviewPacketRequest(
            bundle=FAKE_BUNDLE_DATA,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        self.assertEqual(response.bundle_id, "test-bundle-001")
        self.assertEqual(response.format, "markdown")
        self.assertIsNotNone(response.packet)
        self.assertTrue(len(response.packet) > 0)

    def test_packet_includes_required_sections(self) -> None:
        """Response packet must include all required sections."""
        request = IncidentReviewPacketRequest(
            bundle=FAKE_BUNDLE_DATA,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        packet = response.packet
        required_sections = [
            "Metadata",
            "Evidence Summary",
            "Detected Symptoms",
            "Failing Pods",
            "Deployment Health",
            "Warning Events",
            "Collection Errors",
            "Known Limitations",
            "Reviewer Constraints",
            "Questions for Next Evidence Collection",
            "Raw Evidence Index",
        ]

        for section in required_sections:
            self.assertIn(section, packet, f"Missing section: {section}")

    def test_packet_includes_self_contained_constraint(self) -> None:
        """Packet must include self-contained k9b-only constraint."""
        request = IncidentReviewPacketRequest(
            bundle=FAKE_BUNDLE_DATA,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        self.assertIn("Self-Contained k9b-Only Constraint", response.packet)
        self.assertIn("Cline", response.packet)

    def test_packet_states_pod_logs_not_included(self) -> None:
        """Packet must explicitly state pod logs are not included."""
        request = IncidentReviewPacketRequest(
            bundle=FAKE_BUNDLE_DATA,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        self.assertIn("Pod logs are NOT included", response.packet)

    def test_response_to_dict(self) -> None:
        """Test that IncidentReviewPacketResponse.to_dict() works correctly."""
        request = IncidentReviewPacketRequest(
            bundle=FAKE_BUNDLE_DATA,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        data = response.to_dict()

        self.assertEqual(data["bundle_id"], "test-bundle-001")
        self.assertEqual(data["format"], "markdown")
        self.assertIn("packet", data)
        self.assertTrue(len(data["packet"]) > 0)


class TestHandleIncidentReviewPacketValidation(unittest.TestCase):
    """Test validation and error handling in the handler."""

    def test_missing_metadata_returns_error_response(self) -> None:
        """Request with missing metadata should return error response."""
        invalid_bundle = {"pods": []}  # No metadata
        request = IncidentReviewPacketRequest(
            bundle=invalid_bundle,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        # Should still return a response (with empty packet or error message)
        self.assertEqual(response.bundle_id, "unknown")

    def test_empty_bundle_returns_response(self) -> None:
        """Request with empty bundle should return response."""
        empty_bundle = {}
        request = IncidentReviewPacketRequest(
            bundle=empty_bundle,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        self.assertEqual(response.bundle_id, "unknown")


class TestSentinelPatternsInPacket(unittest.TestCase):
    """Test that sensitive sentinel patterns do not appear in generated packets."""

    _SENTINEL_PATTERNS = (
        "KUBE_SECRET_TOKEN_abc123",
        "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "api_key=sk-abcdefghijk",
        "client_secret=super_secret_value",
        "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "Authorization: Bearer sk-abc123",
    )

    def _contains_sentinel(self, value: str | None) -> bool:
        """Check if a string contains any sentinel test patterns."""
        if not value:
            return False
        return any(sentinel in value for sentinel in self._SENTINEL_PATTERNS)

    def test_packet_no_sentinels(self) -> None:
        """Generated packet should not contain sentinel patterns."""
        # Add sentinel data to bundle to test sanitization
        leaky_bundle = FAKE_BUNDLE_DATA.copy()
        leaky_bundle["pods"] = [
            {
                "name": "leaky-pod",
                "namespace": "default",
                "phase": "Running",
                "health_status": "running",
                "restart_count": 0,
                "node": "node-1",
                "image_refs": ["nginx:v1"],
                "reason": "api_key=sk-abcdefghijk",
                "message": "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "is_failing": False,
            },
        ]

        request = IncidentReviewPacketRequest(
            bundle=leaky_bundle,
            format="markdown",
        )
        response = handle_incident_review_packet(request)

        # The packet should not contain the sentinel values
        self.assertNotIn("api_key=sk-abcdefghijk", response.packet)
        self.assertNotIn("token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", response.packet)


if __name__ == "__main__":
    unittest.main()
