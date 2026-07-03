"""Regression tests for P4c unschedulable-shipping diagnosis root-cause.

Tests the fix for the regression where deployment_unavailable incident
candidates did not include pod_describe and pod_events in evidence_needed,
causing the automatic diagnosis loop to miss scheduling failure evidence
(FailedScheduling, Unschedulable, nodeSelector).

Bug: P4c root-cause validation fails because diagnosis/review artifacts
do not mention the actual scheduling root cause (shipping, nodeSelector,
k9b.dev/otel-lab-node, FailedScheduling, Unschedulable).

Root cause: evidence_needed only had deployment_describe, replica_status -
missing pod_describe, pod_events for scheduling discovery.

Fix: Add pod_describe and pod_events to evidence_needed for deployment_unavailable.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    detect_incident_candidates,
)
from k8s_diag_agent.collect.incident_models import (
    DeploymentSummary,
    EventSummary,
    PodHealthStatus,
    PodSummary,
)


def make_deployment(
    name: str,
    namespace: str = "default",
    replicas: int = 1,
    available_replicas: int = 0,
    ready_replicas: int = 0,
    updated_replicas: int = 0,
    available: bool = False,
) -> DeploymentSummary:
    """Helper to create test deployment summaries."""
    return DeploymentSummary(
        name=name,
        namespace=namespace,
        replicas=replicas,
        available_replicas=available_replicas,
        ready_replicas=ready_replicas,
        updated_replicas=updated_replicas,
        available=available,
    )


def make_pod(
    name: str,
    namespace: str,
    phase: str = "Pending",
    health_status: PodHealthStatus = PodHealthStatus.PENDING,
    reason: str | None = None,
    message: str | None = None,
    node: str | None = None,
) -> PodSummary:
    """Helper to create test pod summaries."""
    return PodSummary(
        name=name,
        namespace=namespace,
        phase=phase,
        health_status=health_status,
        restart_count=0,
        node=node,
        image_refs=(),
        reason=reason,
        message=message,
        is_failing=True,
    )


def make_event(
    namespace: str,
    reason: str,
    message: str,
    type: str = "Warning",
    involved_object_kind: str | None = None,
    involved_object_name: str | None = None,
) -> EventSummary:
    """Helper to create test event summaries."""
    return EventSummary(
        namespace=namespace,
        name=f"{involved_object_name or 'unknown'}-{reason.lower()}",
        type=type,
        reason=reason,
        message=message,
        involved_object_kind=involved_object_kind,
        involved_object_name=involved_object_name,
        count=1,
        last_timestamp=None,
    )


class TestDeploymentUnavailableSchedulingEvidenceNeeded(unittest.TestCase):
    """Test that deployment_unavailable includes scheduling evidence types."""

    def test_deployment_unavailable_includes_pod_evidence(self) -> None:
        """deployment_unavailable must include pod_describe and pod_events in evidence_needed.

        This is required for diagnosing scheduling failures where:
        - The scheduling failure events (FailedScheduling) are on the Pods
        - The nodeSelector is in the Pod spec
        - Without pod-level evidence, the diagnosis cannot find the root cause
        """
        deployment = make_deployment(
            name="shipping",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        self.assertEqual(candidate.candidate_class, CandidateClass.DEPLOYMENT_UNAVAILABLE)
        self.assertEqual(candidate.object_name, "shipping")
        self.assertEqual(candidate.namespace, "otel-demo")

        # Critical: evidence_needed must include pod-level evidence
        evidence_needed = set(candidate.evidence_needed)
        self.assertIn("pod_describe", evidence_needed,
                     "evidence_needed must include pod_describe for scheduling diagnosis")
        self.assertIn("pod_events", evidence_needed,
                      "evidence_needed must include pod_events for FailedScheduling detection")
        # Original evidence types should still be present
        self.assertIn("deployment_describe", evidence_needed)
        self.assertIn("replica_status", evidence_needed)

    def test_deployment_unavailable_with_pending_pod_and_scheduling_event(self) -> None:
        """Integration test: deployment unavailable with Pending pod and FailedScheduling event.

        This tests the full flow:
        1. Deployment becomes unavailable
        2. Pod is stuck in Pending (due to nodeSelector mismatch)
        3. FailedScheduling event contains the root cause evidence
        """
        deployment = make_deployment(
            name="shipping",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )
        pod = make_pod(
            name="shipping-abc123",
            namespace="otel-demo",
            phase="Pending",
            health_status=PodHealthStatus.PENDING,
            reason="FailedScheduling",
            message="0/8 nodes are available: didn't match Pod's node affinity/selector. "
                    "Label: k9b.dev/otel-lab-node=missing",
        )
        event = make_event(
            namespace="otel-demo",
            reason="FailedScheduling",
            message="0/8 nodes are available: 1 node(s) had taints that the pod didn't tolerate, "
                    "7 nodes didn't match Pod's node affinity/selector. didn't match Pod's node "
                    "affinity/selector. Label: k9b.dev/otel-lab-node=missing",
            type="Warning",
            involved_object_kind="Pod",
            involved_object_name="shipping-abc123",
        )

        candidates = detect_incident_candidates(
            pods=[pod],
            deployments=[deployment],
            events=[event],
        )

        # Should have both deployment_unavailable and pending_pod candidates
        # The deployment_unavailable candidate now includes pod-level evidence
        deployment_candidates = [c for c in candidates if c.candidate_class == CandidateClass.DEPLOYMENT_UNAVAILABLE]
        self.assertEqual(len(deployment_candidates), 1)

        evidence_needed = set(deployment_candidates[0].evidence_needed)
        self.assertIn("pod_describe", evidence_needed)
        self.assertIn("pod_events", evidence_needed)


class TestSchedulingEvidenceExtraction(unittest.TestCase):
    """Test that scheduling evidence can be extracted from events."""

    def test_extract_failed_scheduling_event(self) -> None:
        """FailedScheduling events contain scheduling root cause evidence."""
        from k8s_diag_agent.collect.incident_scheduling_evidence import (
            extract_scheduling_evidence,
        )

        events = [
            {
                "type": "Warning",
                "reason": "FailedScheduling",
                "message": "0/8 nodes are available: didn't match Pod's node affinity/selector. "
                          "Label: k9b.dev/otel-lab-node=missing",
                "involved_object_kind": "Pod",
                "involved_object_name": "shipping-abc123",
            }
        ]

        scheduling_evidence = extract_scheduling_evidence(events)

        self.assertIsNotNone(scheduling_evidence)
        self.assertGreater(len(scheduling_evidence), 0)

        # Verify evidence contains key terms
        evidence_entry = scheduling_evidence[0]
        self.assertEqual(evidence_entry["reason"], "FailedScheduling")
        self.assertIn("k9b.dev/otel-lab-node", evidence_entry["message"])
        self.assertIn("node", evidence_entry["message"].lower())
        self.assertEqual(evidence_entry["involved_object_name"], "shipping-abc123")

    def test_extract_unschedulable_condition(self) -> None:
        """Unschedulable conditions contain scheduling root cause evidence."""
        from k8s_diag_agent.collect.incident_scheduling_evidence import (
            extract_scheduling_evidence,
        )

        events = [
            {
                "type": "Warning",
                "reason": "Unschedulable",
                "message": "Pod cannot be scheduled due to nodeSelector mismatch: "
                          "k9b.dev/otel-lab-node=missing",
                "involved_object_kind": "Pod",
                "involved_object_name": "shipping-xyz789",
            }
        ]

        scheduling_evidence = extract_scheduling_evidence(events)

        self.assertIsNotNone(scheduling_evidence)
        self.assertGreater(len(scheduling_evidence), 0)
        self.assertEqual(scheduling_evidence[0]["reason"], "Unschedulable")

    def test_no_scheduling_evidence_returns_none(self) -> None:
        """Non-scheduling events should not be included."""
        from k8s_diag_agent.collect.incident_scheduling_evidence import (
            extract_scheduling_evidence,
        )

        events = [
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned default/pod-xyz to node-1",
            }
        ]

        scheduling_evidence = extract_scheduling_evidence(events)

        self.assertIsNone(scheduling_evidence)


class TestStopNoChecksAcceptableWithSchedulingEvidence(unittest.TestCase):
    """Test that stop_no_checks_proposed is acceptable with complete scheduling evidence."""

    def test_stop_acceptable_with_complete_scheduling_terms(self) -> None:
        """stop_no_checks_proposed should be acceptable when scheduling terms are present."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_stops import (
            check_root_cause_has_required_terms,
            check_root_cause_has_scheduling_evidence,
        )

        # Simulate diagnosis text with complete scheduling evidence
        diagnosis_text = (
            "The shipping deployment in namespace otel-demo is unavailable because its Pod "
            "template requires nodeSelector k9b.dev/otel-lab-node=missing. The pending shipping "
            "Pod has Warning FailedScheduling / Unschedulable events. No node matched the Pod's "
            "node affinity/selector."
        )

        # Check required terms
        terms_present = check_root_cause_has_required_terms(diagnosis_text)
        self.assertTrue(terms_present,
                       "Diagnosis should contain required terms: shipping, nodeSelector, k9b.dev/otel-lab-node")

        # Check scheduling evidence
        scheduling_present = check_root_cause_has_scheduling_evidence(diagnosis_text)
        self.assertTrue(scheduling_present,
                       "Diagnosis should contain scheduling evidence: FailedScheduling, Unschedulable")

    def test_stop_not_acceptable_without_scheduling_terms(self) -> None:
        """stop_no_checks_proposed should NOT be acceptable without scheduling terms."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_stops import (
            check_root_cause_has_required_terms,
        )

        # Generic deployment unavailable text - missing scheduling evidence
        diagnosis_text = "The shipping deployment is unavailable because it has 0/1 replicas available."

        terms_present = check_root_cause_has_required_terms(diagnosis_text)
        self.assertFalse(terms_present,
                        "Diagnosis should NOT contain required terms without scheduling evidence")


class TestComputeP4cOutcomeWithSchedulingEvidence(unittest.TestCase):
    """Test compute_p4c_outcome with scheduling evidence scenarios."""

    def test_p4c_outcome_fails_with_incomplete_scheduling_evidence(self) -> None:
        """compute_p4c_outcome should fail when scheduling evidence is incomplete in lab-strict mode."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Evidence missing scheduling root cause terms
        evidence = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
            "pass_count": 2,
            "pass_run_ids": ["pass-a", "pass-b"],
            "terminal_decision_reached": "stop_no_checks_proposed",
            "root_cause_summary": "The shipping deployment is unavailable because it has 0/1 replicas available.",
            "read_only": True,
            "read_only_violations": [],
            "real_pass_artifacts_found": True,
            "terminal_no_checks_accepted": True,
        }

        # Lab-strict mode (require_root_cause_terms=True) should fail
        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=False, require_root_cause_terms=True)

        self.assertFalse(outcome.success,
                       "P4c outcome should FAIL with incomplete scheduling evidence in lab-strict mode")
        failure_reasons_str = " ".join(outcome.failure_reasons)
        self.assertIn("missing_root_cause_term", failure_reasons_str,
                     "Failure should mention missing root cause terms")

    def test_p4c_outcome_succeeds_with_complete_scheduling_evidence(self) -> None:
        """compute_p4c_outcome should succeed when scheduling evidence is complete."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Evidence with complete scheduling root cause
        evidence = {
            "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
            "pass_count": 2,
            "pass_run_ids": ["pass-a", "pass-b"],
            "terminal_decision_reached": "stop_no_checks_proposed",
            "root_cause_summary": (
                "The shipping deployment in namespace otel-demo is unavailable because its Pod "
                "template requires nodeSelector k9b.dev/otel-lab-node=missing. The pending shipping "
                "Pod has Warning FailedScheduling / Unschedulable events. No node matched the Pod's "
                "node affinity/selector."
            ),
            "read_only": True,
            "read_only_violations": [],
            "real_pass_artifacts_found": True,
            "terminal_no_checks_accepted": True,
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)

        self.assertTrue(outcome.success,
                       "P4c outcome should SUCCEED with complete scheduling evidence")
        self.assertEqual(outcome.mode, "multipass")
        self.assertIsNone(outcome.root_cause_evidence_reason)


if __name__ == "__main__":
    unittest.main()
