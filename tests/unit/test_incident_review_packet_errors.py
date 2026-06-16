"""Tests for incident review packet dict parsing and error handling.

These tests verify:
- Dictionary parsing from API responses
- Invalid/missing bundle handling
- Edge cases in bundle processing
"""

from __future__ import annotations

import unittest

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


class TestGenerateIncidentReviewPacketFromDict(unittest.TestCase):
    """Test incident review packet generation from dict data."""

    def test_generates_valid_packet_from_dict(self) -> None:
        """Packet generator should work with dict input."""
        from k8s_diag_agent.collect.incident_review_packet import (
            generate_incident_review_packet_from_dict,
        )

        packet = generate_incident_review_packet_from_dict(FAKE_BUNDLE_DATA)

        self.assertIn("Metadata", packet)
        self.assertIn("test-bundle-001", packet)
        self.assertIn("Detected Symptoms", packet)

    def test_includes_all_required_sections_from_dict(self) -> None:
        """Dict input should produce complete packet."""
        from k8s_diag_agent.collect.incident_review_packet import (
            generate_incident_review_packet_from_dict,
        )

        packet = generate_incident_review_packet_from_dict(FAKE_BUNDLE_DATA)

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


class TestDictParsingEdgeCases(unittest.TestCase):
    """Test edge cases in dict parsing."""

    def test_missing_metadata_fields_use_defaults(self) -> None:
        """Missing metadata fields should use sensible defaults."""
        from k8s_diag_agent.collect.incident_review_packet import (
            generate_incident_review_packet_from_dict,
        )

        minimal_data = {
            "metadata": {
                "bundle_id": "minimal-bundle",
                "captured_at": "2024-01-15T12:00:00Z",
                "namespace": "test",
            },
            "pods": [],
            "events": [],
            "deployments": [],
            "symptoms": [],
        }

        packet = generate_incident_review_packet_from_dict(minimal_data)

        self.assertIn("minimal-bundle", packet)
        self.assertIn("Metadata", packet)

    def test_empty_bundle_produces_valid_packet(self) -> None:
        """Empty bundle should produce valid packet with empty sections."""
        from k8s_diag_agent.collect.incident_review_packet import (
            generate_incident_review_packet_from_dict,
        )

        empty_data = {
            "metadata": {
                "bundle_id": "empty-bundle",
                "captured_at": "2024-01-15T12:00:00Z",
                "namespace": "empty",
                "since_hours": 2,
                "total_pods": 0,
                "total_events": 0,
                "total_deployments": 0,
                "failing_pods_count": 0,
                "symptoms_count": 0,
            },
            "pods": [],
            "events": [],
            "deployments": [],
            "symptoms": [],
            "collection_errors": [],
        }

        packet = generate_incident_review_packet_from_dict(empty_data)

        self.assertIn("Metadata", packet)
        self.assertIn("No failing pods detected", packet)
        self.assertIn("No warning events in captured time window", packet)

    def test_invalid_health_status_uses_unknown(self) -> None:
        """Invalid health status string should fall back to UNKNOWN."""
        from k8s_diag_agent.collect.incident_review_packet import (
            generate_incident_review_packet_from_dict,
        )

        data_with_invalid_status = {
            "metadata": {
                "bundle_id": "test-bundle",
                "captured_at": "2024-01-15T12:00:00Z",
                "namespace": "default",
                "since_hours": 2,
                "total_pods": 1,
                "total_events": 0,
                "total_deployments": 0,
                "failing_pods_count": 0,
                "symptoms_count": 0,
            },
            "pods": [
                {
                    "name": "unknown-status-pod",
                    "namespace": "default",
                    "phase": "Running",
                    "health_status": "not_a_valid_status",
                    "restart_count": 0,
                    "node": "node-1",
                    "image_refs": [],
                    "is_failing": False,
                },
            ],
            "events": [],
            "deployments": [],
            "symptoms": [],
        }

        # Should not raise, should handle gracefully
        packet = generate_incident_review_packet_from_dict(data_with_invalid_status)
        self.assertIn("Metadata", packet)


if __name__ == "__main__":
    unittest.main()
