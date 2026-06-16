"""Tests for incident review packet generation.

These tests verify:
- Packet generation from incident bundles
- Self-contained k9b-only constraint inclusion
- Required packet contents (metadata, symptoms, failing pods, etc.)
- No sentinel patterns in generated packets
- Reviewer constraints inclusion
- Pod logs exclusion notice
"""

from __future__ import annotations

import unittest
from datetime import datetime

from k8s_diag_agent.collect.incident_models import (
    DeploymentSummary,
    EventSummary,
    IncidentBundleMetadata,
    IncidentEvidenceBundle,
    IncidentSymptom,
    PodHealthStatus,
    PodSummary,
)
from k8s_diag_agent.collect.incident_review_packet import (
    K9B_SELF_CONTAINED_CONSTRAINT,
    REVIEWER_CONSTRAINTS,
    generate_incident_review_packet,
    generate_incident_review_packet_from_dict,
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


def make_test_bundle() -> IncidentEvidenceBundle:
    """Create a test bundle matching FAKE_BUNDLE_DATA."""
    metadata = IncidentBundleMetadata(
        bundle_id="test-bundle-001",
        captured_at=datetime(2024, 1, 15, 12, 0, 0),
        namespace="default",
        since_hours=2,
        context=None,
        total_pods=5,
        total_events=3,
        total_deployments=2,
        failing_pods_count=2,
        symptoms_count=3,
    )

    pods = [
        PodSummary(
            name="healthy-pod",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.RUNNING,
            restart_count=0,
            node="node-1",
            image_refs=("nginx:1.21",),
            reason=None,
            message=None,
            is_failing=False,
        ),
        PodSummary(
            name="crashloop-pod",
            namespace="default",
            phase="Running",
            health_status=PodHealthStatus.CRASH_LOOP,
            restart_count=5,
            node="node-1",
            image_refs=("broken:v1",),
            reason="CrashLoopBackOff",
            message="Back-off 5m40s restarting",
            is_failing=True,
        ),
    ]

    events = [
        EventSummary(
            namespace="default",
            name="event-1",
            type="Warning",
            reason="BackOff",
            message="Back-off restarting container crashloop-pod",
            involved_object_kind="Pod",
            involved_object_name="crashloop-pod",
            count=3,
            last_timestamp="2024-01-15T12:00:00Z",
        ),
    ]

    deployments = [
        DeploymentSummary(
            name="nginx-deployment",
            namespace="default",
            replicas=3,
            available_replicas=3,
            ready_replicas=3,
            updated_replicas=3,
            available=True,
        ),
    ]

    symptoms = [
        IncidentSymptom(
            symptom_type="crash_loop",
            pod_name="crashloop-pod",
            message="Pod crashloop-pod in CrashLoopBackOff",
            severity="error",
        ),
    ]

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=(),
    )


# =============================================================================
# Test Cases
# =============================================================================


class TestGenerateIncidentReviewPacket(unittest.TestCase):
    """Test incident review packet generation from bundle objects."""

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

    def test_packet_includes_self_contained_constraint(self) -> None:
        """Packet must include self-contained k9b-only constraint."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Self-Contained k9b-Only Constraint", packet)
        self.assertIn("Cline", packet)

    def test_packet_states_pod_logs_not_included(self) -> None:
        """Packet must explicitly state pod logs are not included."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Pod logs are NOT included", packet)

    def test_packet_states_evidence_not_root_cause(self) -> None:
        """Packet must state that evidence is NOT root cause."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertIn("Evidence is NOT root cause", packet)

    def test_packet_no_sentinel_patterns(self) -> None:
        """Packet must not contain sentinel patterns."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        sentinels = [
            "KUBE_SECRET_TOKEN_abc123",
            "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "api_key=sk-abcdefghijk",
            "client_secret=super_secret_value",
            "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        ]

        for sentinel in sentinels:
            self.assertNotIn(
                sentinel,
                packet,
                f"Packet contains sentinel: {sentinel}",
            )

    def test_packet_no_undefined_or_object_object(self) -> None:
        """Packet must not contain 'undefined' or '[object Object]'."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        self.assertNotIn("undefined", packet.lower())
        self.assertNotIn("[object Object]", packet)

    def test_packet_format_is_markdown(self) -> None:
        """Packet should be valid markdown."""
        bundle = make_test_bundle()
        packet = generate_incident_review_packet(bundle)

        # Check for markdown formatting elements
        self.assertTrue(packet.startswith("# k9b Incident Review Packet"))
        self.assertIn("## ", packet)  # Section headers
        self.assertIn("|", packet)  # Tables


class TestGenerateIncidentReviewPacketFromDict(unittest.TestCase):
    """Test incident review packet generation from dict data."""

    def test_generates_valid_packet_from_dict(self) -> None:
        """Packet generator should work with dict input."""
        packet = generate_incident_review_packet_from_dict(FAKE_BUNDLE_DATA)

        self.assertIn("Metadata", packet)
        self.assertIn("test-bundle-001", packet)
        self.assertIn("Detected Symptoms", packet)

    def test_includes_all_required_sections_from_dict(self) -> None:
        """Dict input should produce complete packet."""
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


class TestConstants(unittest.TestCase):
    """Test that constraint constants are properly defined."""

    def test_self_contained_constraint_has_cline_mentions(self) -> None:
        """Self-contained constraint must mention no Cline required."""
        self.assertIn("Cline", K9B_SELF_CONTAINED_CONSTRAINT)
        self.assertIn("cline", K9B_SELF_CONTAINED_CONSTRAINT.lower())

    def test_reviewer_constraints_mentions_pod_logs(self) -> None:
        """Reviewer constraints must mention pod logs are not included."""
        self.assertIn("Pod logs are NOT included", REVIEWER_CONSTRAINTS)

    def test_reviewer_constraints_mentions_separate_facts(self) -> None:
        """Reviewer constraints must mention separating facts, hypotheses, unknowns."""
        self.assertIn("facts", REVIEWER_CONSTRAINTS.lower())
        self.assertIn("hypotheses", REVIEWER_CONSTRAINTS.lower())

    def test_reviewer_constraints_mentions_no_invent_evidence(self) -> None:
        """Reviewer constraints must mention not inventing missing evidence."""
        self.assertIn("invent missing evidence", REVIEWER_CONSTRAINTS.lower())


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
        from k8s_diag_agent.collect.incident_models import IncidentEvidenceBundle
        
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
