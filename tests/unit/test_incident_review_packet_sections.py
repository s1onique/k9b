"""Tests for incident review packet section builders.

These tests verify:
- Individual section builder outputs
- Section content correctness
- Dynamic section behavior based on bundle data
"""

from __future__ import annotations

import unittest
from datetime import datetime

from k8s_diag_agent.collect.incident_models import (
    DeploymentSummary,
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    PodHealthStatus,
    PodSummary,
)
from k8s_diag_agent.collect.incident_review_packet import (
    generate_incident_review_packet,
)

from .incident_review_packet_fixtures import make_test_bundle


class TestPacketSections(unittest.TestCase):
    """Test incident review packet sections."""

    def test_packet_includes_metadata(self) -> None:
        """Packet must include metadata section."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Metadata", packet)
        self.assertIn("test-bundle-001", packet)
        self.assertIn("default", packet)

    def test_packet_includes_evidence_summary(self) -> None:
        """Packet must include evidence summary."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Evidence Summary", packet)
        self.assertIn("Total Pods", packet)
        self.assertIn("Failing Pods", packet)

    def test_packet_includes_symptoms(self) -> None:
        """Packet must include detected symptoms."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Detected Symptoms", packet)
        self.assertIn("crash_loop", packet)

    def test_packet_includes_failing_pods(self) -> None:
        """Packet must include failing pods section."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Failing Pods", packet)
        self.assertIn("crashloop-pod", packet)

    def test_packet_includes_deployment_health(self) -> None:
        """Packet must include deployment health section."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Deployment Health", packet)
        self.assertIn("nginx-deployment", packet)

    def test_packet_includes_warning_events(self) -> None:
        """Packet must include warning events section."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Warning Events", packet)

    def test_packet_includes_collection_errors(self) -> None:
        """Packet must include collection errors section."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Collection Errors", packet)

    def test_packet_includes_known_limitations(self) -> None:
        """Packet must include known limitations."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Known Limitations", packet)

    def test_packet_includes_reviewer_instructions(self) -> None:
        """Packet must include reviewer instructions."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Reviewer Constraints", packet)

    def test_packet_includes_next_evidence_questions(self) -> None:
        """Packet must include questions for next evidence collection."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Questions for Next Evidence Collection", packet)

    def test_packet_includes_raw_evidence_index(self) -> None:
        """Packet must include raw evidence index."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Raw Evidence Index", packet)


class TestPacketDynamicContent(unittest.TestCase):
    """Test that packet generates dynamic content based on bundle data."""

    def test_crashloop_pod_triggers_log_investigation(self) -> None:
        """CrashLoop pods should trigger log investigation question."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("CrashLoop investigation", packet)
        self.assertIn("container logs", packet.lower())

    def test_no_failing_pods_shows_empty_state(self) -> None:
        """Bundle with no failing pods should show empty state."""
        metadata = IncidentBundleMetadata(
            bundle_id="clean-bundle",
            captured_at=datetime.now(),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=3,
            total_events=0,
            total_deployments=1,
            failing_pods_count=0,
            symptoms_count=0,
        )

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[
                PodSummary(
                    name="healthy-pod",
                    namespace="default",
                    phase="Running",
                    health_status=PodHealthStatus.RUNNING,
                    restart_count=0,
                    node="node-1",
                    image_refs=("nginx:latest",),
                    reason=None,
                    message=None,
                    is_failing=False,
                ),
            ],
            events=[],
            deployments=[
                DeploymentSummary(
                    name="web",
                    namespace="default",
                    replicas=2,
                    available_replicas=2,
                    ready_replicas=2,
                    updated_replicas=2,
                    available=True,
                ),
            ],
            symptoms=[],
            collection_errors=(),
        )

        packet = generate_incident_review_packet(bundle)

        self.assertIn("No failing pods detected", packet)

    def test_collection_errors_shows_errors(self) -> None:
        """Bundle with collection errors should display them."""
        # Create a bundle with collection errors
        metadata = make_test_bundle().metadata
        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=make_test_bundle().pods,
            events=make_test_bundle().events,
            deployments=make_test_bundle().deployments,
            symptoms=make_test_bundle().symptoms,
            collection_errors=("pods_collection: connection refused",),
        )

        packet = generate_incident_review_packet(bundle)

        self.assertIn("connection refused", packet)

    def test_unhealthy_deployments_highlighted(self) -> None:
        """Unhealthy deployments should be explicitly highlighted."""
        metadata = IncidentBundleMetadata(
            bundle_id="unhealthy-bundle",
            captured_at=datetime.now(),
            namespace="default",
            since_hours=2,
            context=None,
            total_pods=1,
            total_events=0,
            total_deployments=1,
            failing_pods_count=0,
            symptoms_count=0,
        )

        bundle = IncidentEvidenceBundle(
            metadata=metadata,
            pods=[],
            events=[],
            deployments=[
                DeploymentSummary(
                    name="broken-deployment",
                    namespace="default",
                    replicas=3,
                    available_replicas=1,
                    ready_replicas=1,
                    updated_replicas=3,
                    available=False,
                ),
            ],
            symptoms=[],
            collection_errors=(),
        )

        packet = generate_incident_review_packet(bundle)

        self.assertIn("Unhealthy Deployments", packet)
        self.assertIn("replica(s) unavailable", packet)


if __name__ == "__main__":
    unittest.main()
