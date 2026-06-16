"""Tests for event-based incident candidate detection.

Covers: warning_event_burst, unknown object kinds, dedupe semantics
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    ObjectKind,
    Severity,
    _safe_object_kind,
    detect_incident_candidates,
)
from k8s_diag_agent.collect.incident_models import (
    EventSummary,
)


def make_event(
    name: str,
    namespace: str = "default",
    event_type: str = "Warning",
    reason: str = "BackOff",
    message: str = "Back-off restarting",
    involved_object_kind: str | None = "Pod",
    involved_object_name: str | None = "test-pod",
    count: int = 1,
) -> EventSummary:
    """Helper to create test event summaries."""
    return EventSummary(
        namespace=namespace,
        name=name,
        type=event_type,
        reason=reason,
        message=message,
        involved_object_kind=involved_object_kind,
        involved_object_name=involved_object_name,
        count=count,
        last_timestamp=None,
    )


class TestWarningEventBurstDetection(unittest.TestCase):
    """Test warning_event_burst candidate detection."""

    def test_detects_warning_event_burst(self) -> None:
        """3+ warning events for same object should produce a burst candidate."""
        events = [
            make_event(name="event-1", reason="BackOff", involved_object_name="test-pod"),
            make_event(name="event-2", reason="BackOff", involved_object_name="test-pod"),
            make_event(name="event-3", reason="Failed", involved_object_name="test-pod"),
        ]
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[],
            events=events,
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.candidate_class, CandidateClass.WARNING_EVENT_BURST)
        self.assertEqual(candidate.severity, Severity.WARNING)
        self.assertEqual(len(candidate.signals), 3)  # All 3 events
        self.assertTrue(all(s.source == "event" for s in candidate.signals))

    def test_below_threshold_no_candidate(self) -> None:
        """Fewer than 3 warning events should not produce a burst candidate."""
        events = [
            make_event(name="event-1", involved_object_name="test-pod"),
            make_event(name="event-2", involved_object_name="test-pod"),
        ]
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[],
            events=events,
        )

        self.assertEqual(len(candidates), 0)

    def test_normal_events_ignored(self) -> None:
        """Normal (non-warning) events should be ignored."""
        events = [
            make_event(name="event-1", event_type="Normal", reason="Scheduled"),
            make_event(name="event-2", event_type="Normal", reason="Started"),
        ]
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[],
            events=events,
        )

        self.assertEqual(len(candidates), 0)


class TestEventDeduplication(unittest.TestCase):
    """Test deduplication behavior for events."""

    def test_repeated_warning_events_same_object_produces_one_candidate(self) -> None:
        """Multiple warning events for same object should dedupe to one candidate."""
        events = [
            make_event(name="event-1", reason="BackOff", message="msg1", involved_object_name="test-pod"),
            make_event(name="event-2", reason="BackOff", message="msg2", involved_object_name="test-pod"),
            make_event(name="event-3", reason="BackOff", message="msg3", involved_object_name="test-pod"),
        ]
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[],
            events=events,
        )

        self.assertEqual(len(candidates), 1)
        # All signals should be included but from same candidate
        self.assertEqual(len(candidates[0].signals), 3)

    def test_different_objects_produce_different_candidates(self) -> None:
        """Warning events for different objects should produce separate candidates."""
        events = [
            make_event(name="event-1", involved_object_name="pod-a"),
            make_event(name="event-2", involved_object_name="pod-a"),
            make_event(name="event-3", involved_object_name="pod-a"),
            make_event(name="event-4", involved_object_name="pod-b"),
            make_event(name="event-5", involved_object_name="pod-b"),
            make_event(name="event-6", involved_object_name="pod-b"),
        ]
        candidates = detect_incident_candidates(
            pods=[],
            deployments=[],
            events=events,
        )

        self.assertEqual(len(candidates), 2)
        candidate_ids = {c.candidate_id for c in candidates}
        self.assertEqual(len(candidate_ids), 2)

    def test_different_namespaces_different_candidates(self) -> None:
        """Same object name in different namespaces should produce different candidates."""
        events1 = [
            make_event(name="event-1", namespace="ns-a", involved_object_name="test-pod"),
            make_event(name="event-2", namespace="ns-a", involved_object_name="test-pod"),
            make_event(name="event-3", namespace="ns-a", involved_object_name="test-pod"),
        ]
        events2 = [
            make_event(name="event-4", namespace="ns-b", involved_object_name="test-pod"),
            make_event(name="event-5", namespace="ns-b", involved_object_name="test-pod"),
            make_event(name="event-6", namespace="ns-b", involved_object_name="test-pod"),
        ]
        candidates1 = detect_incident_candidates(pods=[], deployments=[], events=events1)
        candidates2 = detect_incident_candidates(pods=[], deployments=[], events=events2)

        self.assertNotEqual(candidates1[0].candidate_id, candidates2[0].candidate_id)


class TestUnknownObjectKindIdCollision(unittest.TestCase):
    """Test that unknown object kinds produce unique candidate IDs."""

    def test_replicaset_vs_statefulset_unique_ids(self) -> None:
        """ReplicaSet/foo and StatefulSet/foo must produce distinct candidate IDs.

        Without raw_object_kind in ID, both would produce 'default-unknown-foo-warning_event_burst'.
        With the fix, they produce distinct IDs:
        - ReplicaSet: 'default-replicaset-foo-warning_event_burst'
        - StatefulSet: 'default-statefulset-foo-warning_event_burst'
        """
        # Events for ReplicaSet
        rs_events = [
            make_event(name="rs-event-1", namespace="default", involved_object_kind="ReplicaSet", involved_object_name="foo"),
            make_event(name="rs-event-2", namespace="default", involved_object_kind="ReplicaSet", involved_object_name="foo"),
            make_event(name="rs-event-3", namespace="default", involved_object_kind="ReplicaSet", involved_object_name="foo"),
        ]
        # Events for StatefulSet
        sts_events = [
            make_event(name="sts-event-1", namespace="default", involved_object_kind="StatefulSet", involved_object_name="foo"),
            make_event(name="sts-event-2", namespace="default", involved_object_kind="StatefulSet", involved_object_name="foo"),
            make_event(name="sts-event-3", namespace="default", involved_object_kind="StatefulSet", involved_object_name="foo"),
        ]

        rs_candidates = detect_incident_candidates(pods=[], deployments=[], events=rs_events)
        sts_candidates = detect_incident_candidates(pods=[], deployments=[], events=sts_events)

        # Both should produce exactly one candidate
        self.assertEqual(len(rs_candidates), 1)
        self.assertEqual(len(sts_candidates), 1)

        # Candidate IDs must be distinct (this was the collision bug)
        self.assertNotEqual(rs_candidates[0].candidate_id, sts_candidates[0].candidate_id)

        # Verify the IDs contain the raw kind
        self.assertIn("replicaset", rs_candidates[0].candidate_id)
        self.assertIn("statefulset", sts_candidates[0].candidate_id)

        # raw_object_kind should be preserved in the candidate
        self.assertEqual(rs_candidates[0].raw_object_kind, "ReplicaSet")
        self.assertEqual(sts_candidates[0].raw_object_kind, "StatefulSet")

    def test_same_unknown_kind_same_object_same_id(self) -> None:
        """Same unknown kind + name should produce the same ID on repeated calls."""
        events = [
            make_event(name="event-1", namespace="default", involved_object_kind="DaemonSet", involved_object_name="foo"),
            make_event(name="event-2", namespace="default", involved_object_kind="DaemonSet", involved_object_name="foo"),
            make_event(name="event-3", namespace="default", involved_object_kind="DaemonSet", involved_object_name="foo"),
        ]

        result1 = detect_incident_candidates(pods=[], deployments=[], events=events)
        result2 = detect_incident_candidates(pods=[], deployments=[], events=events)

        self.assertEqual(len(result1), 1)
        self.assertEqual(len(result2), 1)
        self.assertEqual(result1[0].candidate_id, result2[0].candidate_id)
        self.assertIn("daemonset", result1[0].candidate_id)


class TestUnknownObjectKinds(unittest.TestCase):
    """Test handling of unknown Kubernetes object kinds."""

    def test_safe_object_kind_known_pod(self) -> None:
        """Known kind 'Pod' should map to ObjectKind.POD."""
        result = _safe_object_kind("Pod")
        self.assertEqual(result, ObjectKind.POD)

    def test_safe_object_kind_known_deployment(self) -> None:
        """Known kind 'Deployment' should map to ObjectKind.DEPLOYMENT."""
        result = _safe_object_kind("Deployment")
        self.assertEqual(result, ObjectKind.DEPLOYMENT)

    def test_safe_object_kind_unknown_replicaset(self) -> None:
        """Unknown kind 'ReplicaSet' should map to ObjectKind.UNKNOWN."""
        result = _safe_object_kind("ReplicaSet")
        self.assertEqual(result, ObjectKind.UNKNOWN)

    def test_safe_object_kind_unknown_statefulset(self) -> None:
        """Unknown kind 'StatefulSet' should map to ObjectKind.UNKNOWN."""
        result = _safe_object_kind("StatefulSet")
        self.assertEqual(result, ObjectKind.UNKNOWN)

    def test_safe_object_kind_unknown_pvc(self) -> None:
        """Unknown kind 'PersistentVolumeClaim' should map to ObjectKind.UNKNOWN."""
        result = _safe_object_kind("PersistentVolumeClaim")
        self.assertEqual(result, ObjectKind.UNKNOWN)

    def test_safe_object_kind_none(self) -> None:
        """None kind should map to ObjectKind.UNKNOWN."""
        result = _safe_object_kind(None)
        self.assertEqual(result, ObjectKind.UNKNOWN)

    def test_safe_object_kind_empty(self) -> None:
        """Empty kind should map to ObjectKind.UNKNOWN."""
        result = _safe_object_kind("")
        self.assertEqual(result, ObjectKind.UNKNOWN)

    def test_warning_burst_replicaset_no_crash(self) -> None:
        """Warning burst for ReplicaSet should not crash."""
        events = [
            make_event(name="event-1", involved_object_kind="ReplicaSet", involved_object_name="rs-abc"),
            make_event(name="event-2", involved_object_kind="ReplicaSet", involved_object_name="rs-abc"),
            make_event(name="event-3", involved_object_kind="ReplicaSet", involved_object_name="rs-abc"),
        ]
        # Should not raise ValueError
        candidates = detect_incident_candidates(pods=[], deployments=[], events=events)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].candidate_class, CandidateClass.WARNING_EVENT_BURST)
        self.assertEqual(candidates[0].object_kind, ObjectKind.UNKNOWN)

    def test_warning_burst_statefulset_no_crash(self) -> None:
        """Warning burst for StatefulSet should not crash."""
        events = [
            make_event(name="event-1", involved_object_kind="StatefulSet", involved_object_name="sts-data"),
            make_event(name="event-2", involved_object_kind="StatefulSet", involved_object_name="sts-data"),
            make_event(name="event-3", involved_object_kind="StatefulSet", involved_object_name="sts-data"),
        ]
        candidates = detect_incident_candidates(pods=[], deployments=[], events=events)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].object_kind, ObjectKind.UNKNOWN)

    def test_warning_burst_pvc_no_crash(self) -> None:
        """Warning burst for PersistentVolumeClaim should not crash."""
        events = [
            make_event(name="event-1", involved_object_kind="PersistentVolumeClaim", involved_object_name="pvc-data"),
            make_event(name="event-2", involved_object_kind="PersistentVolumeClaim", involved_object_name="pvc-data"),
            make_event(name="event-3", involved_object_kind="PersistentVolumeClaim", involved_object_name="pvc-data"),
        ]
        candidates = detect_incident_candidates(pods=[], deployments=[], events=events)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].object_kind, ObjectKind.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
