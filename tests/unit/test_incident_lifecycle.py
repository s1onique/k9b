"""Tests for incident lifecycle module.

Covers:
- incident record schema and serialization
- deterministic ID generation
- candidate → open transition
- merge behavior (no new identity)
- state transitions: open → collecting_evidence → ready_for_review
- open → suppressed
- open → duplicate
- no remediation fields/actions
- no Kubernetes mutation functions
- dedupe key enforcement (same candidate = same incident)
- distinct object kinds remain separate incidents
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
    incident_id_from_candidate,
    make_incident_id,
    mark_collecting_evidence,
    mark_duplicate,
    mark_ready_for_review,
    merge_candidate_into_incident,
    open_incident_from_candidate,
    suppress_incident,
)


def make_candidate(
    name: str,
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
    object_kind: ObjectKind = ObjectKind.POD,
    raw_object_kind: str | None = None,
) -> IncidentCandidate:
    """Helper to create test candidates."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-{object_kind.value.lower()}-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=object_kind,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
        raw_object_kind=raw_object_kind,
    )


class TestIncidentRecordSchema(unittest.TestCase):
    """Test incident record schema and serialization."""

    def test_incident_serialization_matches_required_schema(self) -> None:
        """Incident.to_dict() must include all required fields."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        incident = Incident(
            incident_id="test-incident",
            source_candidate_id="test-candidate",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=now,
            last_observed_at=now,
            signals=[
                IncidentSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="back-off",
                    captured_at=now,
                ),
            ],
            evidence_needed=["pod_logs", "pod_describe"],
            snapshot_bundle_id=None,
            review_packet_available=False,
        )

        d = incident.to_dict()

        # Required fields from schema
        self.assertIn("incident_id", d)
        self.assertIn("source_candidate_id", d)
        self.assertIn("namespace", d)
        self.assertIn("object_kind", d)
        self.assertIn("object_name", d)
        self.assertIn("raw_object_kind", d)
        self.assertIn("class", d)  # Note: field is 'candidate_class' but serialized as 'class'
        self.assertIn("severity", d)
        self.assertIn("status", d)
        self.assertIn("first_observed_at", d)
        self.assertIn("last_observed_at", d)
        self.assertIn("signals", d)
        self.assertIn("evidence_needed", d)
        self.assertIn("snapshot_bundle_id", d)
        self.assertIn("review_packet_available", d)

    def test_signal_serialization(self) -> None:
        """IncidentSignal.to_dict() must include captured_at."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        sig = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="back-off",
            captured_at=now,
        )
        d = sig.to_dict()
        self.assertEqual(d["source"], "pod")
        self.assertEqual(d["reason"], "CrashLoopBackOff")
        self.assertEqual(d["message"], "back-off")
        self.assertEqual(d["captured_at"], now.isoformat())


class TestDeterministicIDGeneration(unittest.TestCase):
    """Test deterministic incident ID generation from candidates."""

    def test_same_candidate_produces_same_id(self) -> None:
        """Same candidate must produce same incident_id across calls."""
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        id1 = incident_id_from_candidate(candidate)
        id2 = incident_id_from_candidate(candidate)

        self.assertEqual(id1, id2)

    def test_different_names_produce_different_ids(self) -> None:
        """Different object names must produce different incident IDs."""
        cand1 = make_candidate(name="pod-a")
        cand2 = make_candidate(name="pod-b")

        self.assertNotEqual(
            incident_id_from_candidate(cand1),
            incident_id_from_candidate(cand2),
        )

    def test_different_namespaces_produce_different_ids(self) -> None:
        """Different namespaces must produce different incident IDs."""
        cand1 = make_candidate(name="pod", namespace="default")
        cand2 = make_candidate(name="pod", namespace="k9b")

        self.assertNotEqual(
            incident_id_from_candidate(cand1),
            incident_id_from_candidate(cand2),
        )

    def test_different_candidate_classes_produce_different_ids(self) -> None:
        """Different candidate classes must produce different incident IDs."""
        cand1 = make_candidate(name="pod", candidate_class=CandidateClass.CRASH_LOOP)
        cand2 = make_candidate(name="pod", candidate_class=CandidateClass.IMAGE_PULL_ERROR)

        self.assertNotEqual(
            incident_id_from_candidate(cand1),
            incident_id_from_candidate(cand2),
        )

    def test_replicaset_and_statefulset_remain_distinct(self) -> None:
        """ReplicaSet/foo and StatefulSet/foo must remain distinct incidents.

        This tests the dedupe key with raw_object_kind for UNKNOWN object kinds.
        """
        rs_candidate = IncidentCandidate(
            candidate_id="ns-replicaset-foo-crash_loop",
            namespace="ns",
            object_kind=ObjectKind.UNKNOWN,
            object_name="foo",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=(),
            raw_object_kind="ReplicaSet",
        )
        sts_candidate = IncidentCandidate(
            candidate_id="ns-statefulset-foo-crash_loop",
            namespace="ns",
            object_kind=ObjectKind.UNKNOWN,
            object_name="foo",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=(),
            raw_object_kind="StatefulSet",
        )

        rs_id = incident_id_from_candidate(rs_candidate)
        sts_id = incident_id_from_candidate(sts_candidate)

        self.assertNotEqual(rs_id, sts_id)
        self.assertIn("replicaset", rs_id)
        self.assertIn("statefulset", sts_id)

    def test_make_incident_id_format(self) -> None:
        """make_incident_id must produce format: namespace-kind-name-class."""
        incident_id = make_incident_id(
            namespace="default",
            object_kind="pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        self.assertEqual(incident_id, "default-pod-test-pod-crash_loop")

    def test_id_is_lowercase(self) -> None:
        """Incident IDs must be lowercase."""
        incident_id = make_incident_id(
            namespace="NAMESPACE",
            object_kind="Pod",
            object_name="TestPod",
            candidate_class="CRASH_LOOP",
        )
        self.assertEqual(incident_id, "namespace-pod-testpod-crash_loop")


class TestCandidateToOpenTransition(unittest.TestCase):
    """Test candidate → open transition."""

    def test_opens_incident_from_crashloop_candidate(self) -> None:
        """A crash_loop candidate must produce an incident in OPEN state."""
        candidate = make_candidate(
            name="crashloop-pod",
            namespace="default",
            candidate_class=CandidateClass.CRASH_LOOP,
        )
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(incident.status, IncidentStatus.OPEN)
        self.assertEqual(incident.severity, "error")
        self.assertEqual(incident.candidate_class, "crash_loop")
        self.assertEqual(incident.namespace, "default")
        self.assertEqual(incident.object_name, "crashloop-pod")
        self.assertEqual(incident.first_observed_at, observed_at)
        self.assertEqual(incident.last_observed_at, observed_at)

    def test_incident_inherits_signals_from_candidate(self) -> None:
        """Incident must include signals from the candidate."""
        candidate = make_candidate(name="test-pod")
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(len(incident.signals), 1)
        self.assertEqual(incident.signals[0].source, "pod")
        self.assertEqual(incident.signals[0].reason, "CrashLoopBackOff")

    def test_incident_inherits_evidence_needed_from_candidate(self) -> None:
        """Incident must include evidence_needed from the candidate."""
        candidate = make_candidate(name="test-pod")
        observed_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        incident = open_incident_from_candidate(candidate, observed_at)

        self.assertEqual(incident.evidence_needed, ["pod_logs", "pod_describe"])


class TestMergeBehavior(unittest.TestCase):
    """Test that repeated same candidate updates last_observed_at, does not create new identity."""

    def test_merge_updates_last_observed_at(self) -> None:
        """Merging must update last_observed_at."""
        candidate = make_candidate(name="crashloop-pod")
        first_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        second_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        incident1 = open_incident_from_candidate(candidate, first_time)
        incident2 = merge_candidate_into_incident(incident1, candidate, second_time)

        self.assertEqual(incident2.last_observed_at, second_time)
        self.assertEqual(incident2.first_observed_at, first_time)

    def test_merge_does_not_change_incident_id(self) -> None:
        """Merging must NOT create a new incident identity."""
        candidate = make_candidate(name="crashloop-pod")
        first_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        second_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        incident1 = open_incident_from_candidate(candidate, first_time)
        incident2 = merge_candidate_into_incident(incident1, candidate, second_time)

        self.assertEqual(incident2.incident_id, incident1.incident_id)

    def test_merge_appends_signals(self) -> None:
        """Merging must append new signals."""
        candidate = make_candidate(name="crashloop-pod")
        first_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        second_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)

        incident1 = open_incident_from_candidate(candidate, first_time)
        incident2 = merge_candidate_into_incident(incident1, candidate, second_time)

        self.assertEqual(len(incident2.signals), 2)
        self.assertEqual(incident1.signals[0].captured_at, first_time)
        self.assertEqual(incident2.signals[1].captured_at, second_time)


class TestStateTransitions(unittest.TestCase):
    """Test state transition functions."""

    def test_collecting_evidence_attaches_snapshot_bundle_id(self) -> None:
        """mark_collecting_evidence must set snapshot_bundle_id."""
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        updated = mark_collecting_evidence(incident, "bundle-123")

        self.assertEqual(updated.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(updated.snapshot_bundle_id, "bundle-123")

    def test_ready_for_review_marks_packet_availability(self) -> None:
        """mark_ready_for_review must set review_packet_available."""
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.COLLECTING_EVIDENCE,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
            snapshot_bundle_id="bundle-123",
        )

        updated = mark_ready_for_review(incident, "review-packet-456")

        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertEqual(updated.review_packet_id, "review-packet-456")

    def test_ready_for_review_with_default_id(self) -> None:
        """mark_ready_for_review must work without review_packet_id."""
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.COLLECTING_EVIDENCE,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        updated = mark_ready_for_review(incident)

        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertIsNone(updated.review_packet_id)

    def test_suppress_incident_records_reason(self) -> None:
        """suppress_incident must record suppression reason."""
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        updated = suppress_incident(incident, "known issue in maintenance window")

        self.assertEqual(updated.status, IncidentStatus.SUPPRESSED)
        self.assertEqual(updated.suppressed_reason, "known issue in maintenance window")

    def test_mark_duplicate_records_duplicate_target(self) -> None:
        """mark_duplicate must record the duplicate target."""
        incident = Incident(
            incident_id="duplicate-incident",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime.now(UTC),
            last_observed_at=datetime.now(UTC),
        )

        updated = mark_duplicate(incident, "primary-incident-123")

        self.assertEqual(updated.status, IncidentStatus.DUPLICATE)
        self.assertEqual(updated.duplicate_of, "primary-incident-123")


class TestNoRemediationFields(unittest.TestCase):
    """Verify no remediation fields/actions exist in the lifecycle module."""

    def test_no_remediation_action_fields(self) -> None:
        """Incident must not have remediation action fields."""
        now = datetime.now(UTC)
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=now,
            last_observed_at=now,
        )
        d = incident.to_dict()

        # Remediation-related fields that should NOT exist
        self.assertNotIn("remediation_action", d)
        self.assertNotIn("remediation_command", d)
        self.assertNotIn("remediation_applied", d)
        self.assertNotIn("auto_remediation", d)
        self.assertNotIn("kubectl_action", d)

    def test_no_remediation_functions_in_module(self) -> None:
        """Module must not expose remediation functions."""
        import k8s_diag_agent.collect.incident_lifecycle as lifecycle_module

        module_attrs = dir(lifecycle_module)
        remediation_keywords = ["remediat", "kubectl", "apply", "patch", "delete", "scale"]

        for attr in module_attrs:
            for keyword in remediation_keywords:
                self.assertNotIn(
                    keyword,
                    attr.lower(),
                    f"Module contains remediation-related function: {attr}",
                )


class TestNoKubernetesMutation(unittest.TestCase):
    """Verify no Kubernetes mutation functions are called or exposed."""

    def test_transition_functions_are_pure(self) -> None:
        """All transition functions must be pure (no side effects)."""
        # Create a minimal incident
        now = datetime.now(UTC)
        incident = Incident(
            incident_id="test",
            source_candidate_id="test",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            raw_object_kind=None,
            candidate_class="crash_loop",
            severity="error",
            status=IncidentStatus.OPEN,
            first_observed_at=now,
            last_observed_at=now,
        )

        # Apply transitions - they should return new objects, not mutate
        result1 = mark_collecting_evidence(incident, "bundle-1")
        result2 = mark_ready_for_review(result1, "review-1")
        result3 = suppress_incident(result2, "test")

        # Original incident should be unchanged
        self.assertEqual(incident.status, IncidentStatus.OPEN)
        self.assertIsNone(incident.snapshot_bundle_id)

        # Results should be new objects
        self.assertIsNot(result1, incident)
        self.assertIsNot(result2, incident)
        self.assertIsNot(result3, incident)


class TestIncidentStatusEnum(unittest.TestCase):
    """Test IncidentStatus enum has correct values."""

    def test_required_states_exist(self) -> None:
        """All required state values must exist."""
        self.assertEqual(IncidentStatus.OPEN.value, "open")
        self.assertEqual(IncidentStatus.COLLECTING_EVIDENCE.value, "collecting_evidence")
        self.assertEqual(IncidentStatus.READY_FOR_REVIEW.value, "ready_for_review")
        self.assertEqual(IncidentStatus.INVESTIGATING.value, "investigating")
        self.assertEqual(IncidentStatus.SUPPRESSED.value, "suppressed")
        self.assertEqual(IncidentStatus.DUPLICATE.value, "duplicate")

    def test_resolved_exists_for_future(self) -> None:
        """RESOLVED state must exist for future implementation."""
        self.assertEqual(IncidentStatus.RESOLVED.value, "resolved")


class TestDedupKeyEnforcement(unittest.TestCase):
    """Test dedupe key enforcement across scenarios."""

    def test_same_dedupe_key_same_incident_id(self) -> None:
        """Same dedupe key must produce same incident ID."""
        candidate1 = make_candidate(name="pod", namespace="default")
        candidate2 = make_candidate(name="pod", namespace="default")

        id1 = incident_id_from_candidate(candidate1)
        id2 = incident_id_from_candidate(candidate2)

        self.assertEqual(id1, id2)

    def test_pod_vs_deployment_same_name_different_ids(self) -> None:
        """Pod/foo and Deployment/foo must have different incident IDs."""
        pod_candidate = make_candidate(
            name="myapp",
            object_kind=ObjectKind.POD,
            candidate_class=CandidateClass.CRASH_LOOP,
        )
        deploy_candidate = make_candidate(
            name="myapp",
            object_kind=ObjectKind.DEPLOYMENT,
            candidate_class=CandidateClass.DEPLOYMENT_UNAVAILABLE,
        )

        pod_id = incident_id_from_candidate(pod_candidate)
        deploy_id = incident_id_from_candidate(deploy_candidate)

        self.assertNotEqual(pod_id, deploy_id)
        self.assertIn("pod", pod_id)
        self.assertIn("deployment", deploy_id)


if __name__ == "__main__":
    unittest.main()