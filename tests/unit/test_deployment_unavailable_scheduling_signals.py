"""Regression tests for P4c deployment scheduling signals.

Tests the fix where deployment_unavailable incident candidates now include
scheduling failure events (FailedScheduling, Unschedulable, nodeSelector) in signals.

This enables extract_scheduling_root_cause() to find scheduling root-cause evidence.
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


class TestDeploymentSchedulingSignals(unittest.TestCase):
    """Test that deployment candidates include scheduling events in signals."""

    def test_deployment_unavailable_includes_scheduling_events_in_signals(self) -> None:
        """deployment_unavailable candidate must include scheduling events in signals.

        P4c FIX: When a deployment has unavailable replicas due to scheduling failures,
        the candidate's signals must include the FailedScheduling event details so that
        extract_scheduling_root_cause() can find the root cause evidence.
        """
        deployment = make_deployment(
            name="shipping",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )

        failed_scheduling_event = make_event(
            namespace="otel-demo",
            reason="FailedScheduling",
            message="0/8 nodes are available: 1 node(s) had taints that the pod didn't tolerate, "
                    "7 nodes didn't match Pod's node affinity/selector. Label: k9b.dev/otel-lab-node=missing",
            type="Warning",
            involved_object_kind="Pod",
            involved_object_name="shipping-abc123-xyz",
        )

        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[failed_scheduling_event],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        self.assertEqual(candidate.candidate_class, CandidateClass.DEPLOYMENT_UNAVAILABLE)

        # P4c FIX: Candidate must have multiple signals including scheduling event
        self.assertGreaterEqual(
            len(candidate.signals), 2,
            "Candidate must have at least 2 signals: deployment + scheduling event"
        )

        deployment_signal = candidate.signals[0]
        self.assertEqual(deployment_signal.source, "deployment")
        self.assertEqual(deployment_signal.reason, "replicas_unavailable")
        self.assertIn("shipping", deployment_signal.message)
        self.assertIn("0/1", deployment_signal.message)

        scheduling_signal = candidate.signals[1]
        self.assertEqual(scheduling_signal.source, "event")
        self.assertEqual(scheduling_signal.reason, "FailedScheduling")
        self.assertIn("k9b.dev/otel-lab-node", scheduling_signal.message)

        evidence_needed = set(candidate.evidence_needed)
        self.assertIn("pod_node_selector", evidence_needed)
        self.assertIn("node_labels", evidence_needed)

    def test_deployment_unavailable_without_scheduling_events_has_single_signal(self) -> None:
        """deployment_unavailable without scheduling events has only deployment signal."""
        deployment = make_deployment(
            name="api-server",
            namespace="default",
            replicas=3,
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

        self.assertEqual(len(candidate.signals), 1)
        self.assertEqual(candidate.signals[0].source, "deployment")
        self.assertEqual(candidate.signals[0].reason, "replicas_unavailable")

        evidence_needed = set(candidate.evidence_needed)
        self.assertNotIn("pod_node_selector", evidence_needed)
        self.assertNotIn("node_labels", evidence_needed)

    def test_scheduling_events_not_in_wrong_namespace(self) -> None:
        """Scheduling events in different namespace should not be included."""
        deployment = make_deployment(
            name="shipping",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )

        wrong_namespace_event = make_event(
            namespace="default",
            reason="FailedScheduling",
            message="Node selector mismatch",
            type="Warning",
            involved_object_kind="Pod",
            involved_object_name="other-pod-xyz",
        )

        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[wrong_namespace_event],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        self.assertEqual(len(candidate.signals), 1)
        self.assertEqual(candidate.signals[0].source, "deployment")

    def test_scheduling_events_prefix_collision_protection(self) -> None:
        """Prefix collision: 'ship' deployment should NOT match 'shipping-xxx' pods."""
        deployment = make_deployment(
            name="ship",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )

        shipping_pod_event = make_event(
            namespace="otel-demo",
            reason="FailedScheduling",
            message="k9b.dev/otel-lab-node=missing",
            type="Warning",
            involved_object_kind="Pod",
            involved_object_name="shipping-abc123-xyz",
        )

        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[shipping_pod_event],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        self.assertEqual(len(candidate.signals), 1)
        self.assertEqual(candidate.signals[0].reason, "replicas_unavailable")

    def test_shipping_deployment_matches_shipping_pod_events(self) -> None:
        """The 'shipping' deployment SHOULD match 'shipping-xxx' pods."""
        deployment = make_deployment(
            name="shipping",
            namespace="otel-demo",
            replicas=1,
            available_replicas=0,
            available=False,
        )

        shipping_pod_event = make_event(
            namespace="otel-demo",
            reason="FailedScheduling",
            message="0/8 nodes are available: didn't match Pod's node affinity/selector. "
                    "Label: k9b.dev/otel-lab-node=missing",
            type="Warning",
            involved_object_kind="Pod",
            involved_object_name="shipping-abc123-xyz",
        )

        candidates = detect_incident_candidates(
            pods=[],
            deployments=[deployment],
            events=[shipping_pod_event],
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]

        self.assertEqual(len(candidate.signals), 2)
        self.assertEqual(candidate.signals[0].source, "deployment")
        self.assertEqual(candidate.signals[1].source, "event")
        self.assertEqual(candidate.signals[1].reason, "FailedScheduling")

        evidence_needed = set(candidate.evidence_needed)
        self.assertIn("pod_node_selector", evidence_needed)
        self.assertIn("node_labels", evidence_needed)


if __name__ == "__main__":
    unittest.main()
