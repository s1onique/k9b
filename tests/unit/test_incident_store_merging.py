"""Tests for merging behavior: same dedupe key merges into existing incident.

Tests:
- Same dedupe key merges into existing incident
- first_observed_at remains stable
- last_observed_at updates
- signals append rather than replace
- Unknown raw object kinds remain distinct
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate, make_store

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    IncidentCandidate,
    ObjectKind,
    Severity,
)


class TestRepeatedCandidateDedup(unittest.TestCase):
    """Test that repeated same candidate updates existing incident."""

    def test_repeated_same_candidate_updates_existing_incident(self) -> None:
        """Repeated same candidate must NOT create a duplicate incident."""
        store = make_store()
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
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)

        self.assertEqual(incidents1[0].last_observed_at, TEST_TIME_1)
        self.assertEqual(incidents2[0].last_observed_at, TEST_TIME_2)
        # first_observed_at should remain stable
        self.assertEqual(incidents2[0].first_observed_at, TEST_TIME_1)

    def test_repeated_candidate_appends_signals(self) -> None:
        """Repeated candidate must append new signals."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)

        # First promotion has 1 signal
        self.assertEqual(len(incidents1[0].signals), 1)
        # After merge, should have 2 signals
        self.assertEqual(len(incidents2[0].signals), 2)

    def test_store_len_increments_correctly(self) -> None:
        """Store length must reflect unique incidents."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        self.assertEqual(len(store), 0)
        store.promote_candidates([candidate], TEST_TIME_1)
        self.assertEqual(len(store), 1)
        store.promote_candidates([candidate], TEST_TIME_2)
        # Still 1, not 2
        self.assertEqual(len(store), 1)


class TestUnknownObjectKindDedup(unittest.TestCase):
    """Test that unknown raw object kinds remain distinct."""

    def test_replicaset_and_statefulset_remain_distinct(self) -> None:
        """ReplicaSet/foo and StatefulSet/foo must produce distinct incidents."""
        store = make_store()

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
        store = make_store()

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


if __name__ == "__main__":
    unittest.main()
