"""Tests for the in-memory incident store.

Covers:
- promotes one candidate to open incident
- repeated same candidate updates existing incident instead of creating duplicate
- multiple distinct candidates create multiple incidents
- list_incidents returns deterministic ordering
- status filter works
- get_incident returns expected record
- collecting_evidence transition updates stored incident
- ready_for_review transition updates stored incident
- suppress transition updates stored incident
- duplicate transition updates stored incident
- unknown raw object kinds remain distinct
- no remediation/mutation/LLM/subprocess APIs exist
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
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore

# Standard test timestamps
TEST_TIME_1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)


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


class TestPromoteOneCandidate(unittest.TestCase):
    """Test promoting a single candidate to an open incident."""

    def test_promotes_one_candidate_to_open_incident(self) -> None:
        """A single candidate must produce an incident in OPEN state."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.OPEN)
        self.assertEqual(incidents[0].namespace, "default")
        self.assertEqual(incidents[0].object_name, "crashloop-pod")
        self.assertEqual(incidents[0].first_observed_at, TEST_TIME_1)
        self.assertEqual(incidents[0].last_observed_at, TEST_TIME_1)

    def test_promoted_incident_has_signals(self) -> None:
        """Promoted incident must include signals from the candidate."""
        store = IncidentStore()
        candidate = make_candidate(name="test-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        self.assertEqual(len(incidents[0].signals), 1)
        self.assertEqual(incidents[0].signals[0].source, "pod")


class TestRepeatedCandidateDedup(unittest.TestCase):
    """Test that repeated same candidate updates existing incident."""

    def test_repeated_same_candidate_updates_existing_incident(self) -> None:
        """Repeated same candidate must NOT create a duplicate incident."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        # First promotion
        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        # Second promotion with same candidate
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)

        # Should still have only 1 incident
        self.assertEqual(len(incidents1), 1)
        self.assertEqual(len(incidents2), 1)
        self.assertEqual(incidents1[0].incident_id, incidents2[0].incident_id)

    def test_repeated_candidate_updates_last_observed_at(self) -> None:
        """Repeated candidate must update last_observed_at."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)

        self.assertEqual(incidents1[0].last_observed_at, TEST_TIME_1)
        self.assertEqual(incidents2[0].last_observed_at, TEST_TIME_2)
        # first_observed_at should remain stable
        self.assertEqual(incidents2[0].first_observed_at, TEST_TIME_1)

    def test_repeated_candidate_appends_signals(self) -> None:
        """Repeated candidate must append new signals."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)

        # First promotion has 1 signal
        self.assertEqual(len(incidents1[0].signals), 1)
        # After merge, should have 2 signals
        self.assertEqual(len(incidents2[0].signals), 2)

    def test_store_len_increments_correctly(self) -> None:
        """Store length must reflect unique incidents."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        self.assertEqual(len(store), 0)
        store.promote_candidates([candidate], TEST_TIME_1)
        self.assertEqual(len(store), 1)
        store.promote_candidates([candidate], TEST_TIME_2)
        # Still 1, not 2
        self.assertEqual(len(store), 1)


class TestMultipleDistinctCandidates(unittest.TestCase):
    """Test that multiple distinct candidates create multiple incidents."""

    def test_multiple_distinct_candidates_create_multiple_incidents(self) -> None:
        """Distinct candidates must produce distinct incidents."""
        store = IncidentStore()
        candidate1 = make_candidate(name="crashloop-pod-1", namespace="default")
        candidate2 = make_candidate(name="crashloop-pod-2", namespace="default")

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)

    def test_different_namespace_creates_different_incident(self) -> None:
        """Different namespaces must create different incidents."""
        store = IncidentStore()
        candidate1 = make_candidate(name="myapp", namespace="default")
        candidate2 = make_candidate(name="myapp", namespace="k9b")

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)

    def test_different_candidate_class_creates_different_incident(self) -> None:
        """Different candidate classes must create different incidents."""
        store = IncidentStore()
        candidate1 = make_candidate(
            name="myapp",
            candidate_class=CandidateClass.CRASH_LOOP,
        )
        candidate2 = make_candidate(
            name="myapp",
            candidate_class=CandidateClass.IMAGE_PULL_ERROR,
        )

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)


class TestListIncidentsOrdering(unittest.TestCase):
    """Test deterministic ordering of list_incidents."""

    def test_list_incidents_returns_deterministic_ordering(self) -> None:
        """list_incidents must return incidents sorted by incident_id."""
        store = IncidentStore()
        # Add incidents in non-sorted order
        cand_z = make_candidate(name="z-pod", namespace="default")
        cand_a = make_candidate(name="a-pod", namespace="default")
        cand_m = make_candidate(name="m-pod", namespace="default")

        store.promote_candidates([cand_z, cand_a, cand_m], TEST_TIME_1)

        incidents = store.list_incidents()

        # Should be sorted alphabetically by incident_id
        incident_ids = [i.incident_id for i in incidents]
        self.assertEqual(incident_ids, sorted(incident_ids))

    def test_list_incidents_with_status_filter(self) -> None:
        """list_incidents must filter by status correctly."""
        store = IncidentStore()
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)

        # Mark one as suppressed
        incidents = store.list_incidents()
        store.suppress(incidents[0].incident_id, "known issue")

        # Filter by OPEN status
        open_incidents = store.list_incidents(status=IncidentStatus.OPEN)
        self.assertEqual(len(open_incidents), 1)

        # Filter by SUPPRESSED status
        suppressed_incidents = store.list_incidents(status=IncidentStatus.SUPPRESSED)
        self.assertEqual(len(suppressed_incidents), 1)

        # Filter by non-matching status
        investigating_incidents = store.list_incidents(status=IncidentStatus.INVESTIGATING)
        self.assertEqual(len(investigating_incidents), 0)


class TestGetIncident(unittest.TestCase):
    """Test get_incident retrieval."""

    def test_get_incident_returns_expected_record(self) -> None:
        """get_incident must return the correct incident."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        retrieved = store.get_incident(incident_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.incident_id, incident_id)
        self.assertEqual(retrieved.namespace, "default")
        self.assertEqual(retrieved.object_name, "crashloop-pod")

    def test_get_incident_returns_none_for_unknown_id(self) -> None:
        """get_incident must return None for unknown ID."""
        store = IncidentStore()

        retrieved = store.get_incident("unknown-id")

        self.assertIsNone(retrieved)

    def test_get_incident_returns_snapshot(self) -> None:
        """get_incident must return a snapshot, not internal state."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        retrieved1 = store.get_incident(store.list_incidents()[0].incident_id)
        retrieved2 = store.get_incident(store.list_incidents()[0].incident_id)

        # Modifying returned incident should not affect store
        if retrieved1:
            retrieved1.signals.append(
                store.list_incidents()[0].signals[0]
            )  # type: ignore

        # retrieved2 should be unchanged
        self.assertIsNot(retrieved1, retrieved2)


class TestCollectingEvidenceTransition(unittest.TestCase):
    """Test collecting_evidence state transition."""

    def test_collecting_evidence_transition_updates_stored_incident(self) -> None:
        """mark_collecting_evidence must update the incident in the store."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_collecting_evidence(incident_id, "bundle-123")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(updated.snapshot_bundle_id, "bundle-123")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.COLLECTING_EVIDENCE)

    def test_collecting_evidence_returns_none_for_unknown(self) -> None:
        """mark_collecting_evidence must return None for unknown ID."""
        store = IncidentStore()

        result = store.mark_collecting_evidence("unknown-id", "bundle-123")

        self.assertIsNone(result)


class TestReadyForReviewTransition(unittest.TestCase):
    """Test ready_for_review state transition."""

    def test_ready_for_review_transition_updates_stored_incident(self) -> None:
        """mark_ready_for_review must update the incident in the store."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_ready_for_review(incident_id, "review-456")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)
        self.assertEqual(updated.review_packet_id, "review-456")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.READY_FOR_REVIEW)

    def test_ready_for_review_without_packet_id(self) -> None:
        """mark_ready_for_review must work without review_packet_id."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.mark_ready_for_review(incident_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.READY_FOR_REVIEW)
        self.assertTrue(updated.review_packet_available)


class TestSuppressTransition(unittest.TestCase):
    """Test suppress state transition."""

    def test_suppress_transition_updates_stored_incident(self) -> None:
        """suppress must update the incident in the store."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incidents = store.list_incidents()
        incident_id = incidents[0].incident_id

        updated = store.suppress(incident_id, "known issue during maintenance")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.SUPPRESSED)
        self.assertEqual(updated.suppressed_reason, "known issue during maintenance")

        # Verify stored incident is updated
        stored = store.get_incident(incident_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.SUPPRESSED)

    def test_suppress_returns_none_for_unknown(self) -> None:
        """suppress must return None for unknown ID."""
        store = IncidentStore()

        result = store.suppress("unknown-id", "test")

        self.assertIsNone(result)


class TestDuplicateTransition(unittest.TestCase):
    """Test duplicate state transition."""

    def test_duplicate_transition_updates_stored_incident(self) -> None:
        """mark_duplicate must update the incident in the store."""
        store = IncidentStore()
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)
        incidents = store.list_incidents()

        # Mark incident 2 as duplicate of incident 1
        incident2_id = incidents[1].incident_id
        incident1_id = incidents[0].incident_id

        updated = store.mark_duplicate(incident2_id, incident1_id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.DUPLICATE)
        self.assertEqual(updated.duplicate_of, incident1_id)

        # Verify stored incident is updated
        stored = store.get_incident(incident2_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, IncidentStatus.DUPLICATE)

    def test_duplicate_returns_none_for_unknown(self) -> None:
        """mark_duplicate must return None for unknown ID."""
        store = IncidentStore()

        result = store.mark_duplicate("unknown-id", "primary-incident")

        self.assertIsNone(result)


class TestUnknownObjectKindDedup(unittest.TestCase):
    """Test that unknown raw object kinds remain distinct."""

    def test_replicaset_and_statefulset_remain_distinct(self) -> None:
        """ReplicaSet/foo and StatefulSet/foo must produce distinct incidents."""
        store = IncidentStore()

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

        incidents = store.promote_candidates([rs_candidate, sts_candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)
        # Verify raw_object_kind is preserved
        raw_kinds = {i.raw_object_kind for i in incidents}
        self.assertEqual(raw_kinds, {"ReplicaSet", "StatefulSet"})

    def test_job_and_cronjob_remain_distinct(self) -> None:
        """Job/bar and CronJob/bar must produce distinct incidents."""
        store = IncidentStore()

        job_candidate = IncidentCandidate(
            candidate_id="ns-job-bar-crash_loop",
            namespace="ns",
            object_kind=ObjectKind.UNKNOWN,
            object_name="bar",
            candidate_class=CandidateClass.FAILED_POD,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=(),
            raw_object_kind="Job",
        )
        cronjob_candidate = IncidentCandidate(
            candidate_id="ns-cronjob-bar-crash_loop",
            namespace="ns",
            object_kind=ObjectKind.UNKNOWN,
            object_name="bar",
            candidate_class=CandidateClass.FAILED_POD,
            severity=Severity.ERROR,
            signals=(),
            evidence_needed=(),
            raw_object_kind="CronJob",
        )

        incidents = store.promote_candidates([job_candidate, cronjob_candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 2)
        self.assertNotEqual(incidents[0].incident_id, incidents[1].incident_id)


class TestPromoteCandidatesSnapshot(unittest.TestCase):
    """Test that promote_candidates returns snapshots, not internal state."""

    def test_promote_candidates_returns_snapshot_not_internal_state(self) -> None:
        """promote_candidates must return snapshot copies, not internal state."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        # Mutating returned incident must not affect store
        self.assertEqual(len(incidents), 1)
        original_signals_len = len(incidents[0].signals)
        incidents[0].signals.append(incidents[0].signals[0])

        # Store should be unchanged
        stored = store.list_incidents()[0]
        self.assertEqual(len(stored.signals), original_signals_len)

    def test_promote_candidates_evidence_needed_immutable(self) -> None:
        """promote_candidates must not expose internal evidence_needed list."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        original_evidence_len = len(incidents[0].evidence_needed)
        incidents[0].evidence_needed.append("new_evidence")

        stored = store.list_incidents()[0]
        self.assertEqual(len(stored.evidence_needed), original_evidence_len)

    def test_promote_candidates_multiple_returns_independent_snapshots(self) -> None:
        """Multiple promote_candidates calls must return independent snapshots."""
        store = IncidentStore()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")

        incidents1 = store.promote_candidates([candidate1], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate2], TEST_TIME_2)

        # Mutating one must not affect the other
        incidents1[0].signals.append(incidents1[0].signals[0])

        # incidents2 should be unchanged
        self.assertEqual(len(incidents2[0].signals), 1)


class TestNoExternalApisExist(unittest.TestCase):
    """Verify no remediation, mutation, LLM, or subprocess APIs exist in the store."""

    def test_store_has_no_remediation_methods(self) -> None:
        """IncidentStore must not have remediation-related methods."""
        store = IncidentStore()
        store_attrs = dir(store)

        remediation_keywords = ["remediat", "kubectl", "apply", "patch", "delete", "scale", "restart"]

        for attr in store_attrs:
            if not attr.startswith("_"):
                for keyword in remediation_keywords:
                    self.assertNotIn(
                        keyword,
                        attr.lower(),
                        f"Store contains remediation-related method: {attr}",
                    )

    def test_store_module_has_no_forbidden_imports(self) -> None:
        """Store module must not import forbidden packages."""
        import k8s_diag_agent.collect.incident_store as store_module

        module_file = store_module.__file__
        if module_file:
            with open(module_file) as f:
                content = f.read()

            # Check for forbidden imports
            forbidden = ["subprocess", "kubectl", "kubernetes.client", "openai", "anthropic"]
            for keyword in forbidden:
                self.assertNotIn(
                    f"import {keyword}",
                    content,
                    f"Store module contains forbidden import: {keyword}",
                )
                self.assertNotIn(
                    f"from {keyword}",
                    content,
                    f"Store module contains forbidden from-import: {keyword}",
                )

    def test_store_returns_immutable_snapshots(self) -> None:
        """Store methods must return copies, not expose internal state."""
        store = IncidentStore()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incident = store.list_incidents()[0]

        # Attempt to mutate - should not affect store
        original_signals_len = len(incident.signals)
        incident.signals.append(incident.signals[0])

        # Store should be unchanged
        stored = store.list_incidents()[0]
        self.assertEqual(len(stored.signals), original_signals_len)


class TestEmptyStoreBehavior(unittest.TestCase):
    """Test behavior of empty store."""

    def test_empty_store_list_incidents_returns_empty_tuple(self) -> None:
        """list_incidents on empty store must return empty tuple."""
        store = IncidentStore()

        incidents = store.list_incidents()

        self.assertEqual(incidents, ())

    def test_empty_store_get_incident_returns_none(self) -> None:
        """get_incident on empty store must return None."""
        store = IncidentStore()

        result = store.get_incident("any-id")

        self.assertIsNone(result)

    def test_empty_store_len_is_zero(self) -> None:
        """len(empty_store) must be 0."""
        store = IncidentStore()

        self.assertEqual(len(store), 0)


if __name__ == "__main__":
    unittest.main()
