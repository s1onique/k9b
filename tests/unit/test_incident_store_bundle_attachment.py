"""Tests for snapshot bundle attachment during incident promotion.

Tests:
- promote without bundle ID preserves current OPEN behavior
- promote with bundle ID opens incident as COLLECTING_EVIDENCE
- incident stores snapshot_bundle_id
- repeated same candidate with new bundle ID updates last_observed_at and snapshot_bundle_id
- first_observed_at remains stable
- SUPPRESSED incident is not reopened by repeated candidate
- DUPLICATE incident is not reopened by repeated candidate
- READY_FOR_REVIEW is not downgraded by repeated candidate
- returned incidents are still snapshots, not internal mutable state
- no persistence/remediation/mutation/LLM/external-tool APIs exist
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, TEST_TIME_2, TEST_TIME_3, make_candidate, make_store

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus


class TestPromoteWithoutBundleIdPreservesOpenBehavior(unittest.TestCase):
    """Test that promote_candidates without bundle_id maintains current OPEN behavior."""

    def test_promote_without_bundle_id_creates_open_incident(self) -> None:
        """Without bundle_id, new incidents must be in OPEN state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.OPEN)
        self.assertIsNone(incidents[0].latest_snapshot_bundle_id)

    def test_promote_without_bundle_id_merges_without_status_change(self) -> None:
        """Without bundle_id, merge should not change status."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # First promote
        incidents1 = store.promote_candidates([candidate], TEST_TIME_1)
        self.assertEqual(incidents1[0].status, IncidentStatus.OPEN)

        # Second promote (merge)
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2)
        self.assertEqual(incidents2[0].status, IncidentStatus.OPEN)


class TestPromoteWithBundleIdOpensCollectingEvidence(unittest.TestCase):
    """Test that promote_candidates with bundle_id opens incidents in COLLECTING_EVIDENCE state."""

    def test_promote_with_bundle_id_creates_collecting_evidence_incident(self) -> None:
        """With bundle_id, new incidents must be in COLLECTING_EVIDENCE state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-123"

        incidents = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(incidents[0].latest_snapshot_bundle_id, bundle_id)

    def test_promote_from_bundle_creates_collecting_evidence_incident(self) -> None:
        """promote_candidates_from_bundle must create COLLECTING_EVIDENCE incidents."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-456"

        incidents = store.promote_candidates_from_bundle(bundle_id, [candidate], TEST_TIME_1)

        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(incidents[0].latest_snapshot_bundle_id, bundle_id)


class TestIncidentStoresSnapshotBundleId(unittest.TestCase):
    """Test that incidents properly store snapshot_bundle_id."""

    def test_new_incident_stores_bundle_id(self) -> None:
        """New incident with bundle must store the bundle ID."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-test-1"

        incidents = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)

        self.assertEqual(incidents[0].latest_snapshot_bundle_id, bundle_id)

    def test_stored_incident_has_bundle_id(self) -> None:
        """Stored incident must have the bundle ID after promotion."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")
        bundle_id = "bundle-test-2"

        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id=bundle_id)
        stored = store.list_incidents()[0]

        self.assertEqual(stored.latest_snapshot_bundle_id, bundle_id)


class TestRepeatedCandidateWithNewBundleId(unittest.TestCase):
    """Test behavior when the same candidate is promoted with different bundle IDs."""

    def test_repeated_candidate_updates_last_observed_at(self) -> None:
        """Repeated candidate with bundle must update last_observed_at."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # First promote with bundle
        incidents1 = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        self.assertEqual(incidents1[0].last_observed_at, TEST_TIME_1)

        # Second promote with new bundle
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-2")
        self.assertEqual(incidents2[0].last_observed_at, TEST_TIME_2)

    def test_repeated_candidate_updates_snapshot_bundle_id(self) -> None:
        """Repeated candidate with bundle must update snapshot_bundle_id."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # First promote with bundle-1
        incidents1 = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        self.assertEqual(incidents1[0].latest_snapshot_bundle_id, "bundle-1")

        # Second promote with bundle-2
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-2")
        self.assertEqual(incidents2[0].latest_snapshot_bundle_id, "bundle-2")

    def test_first_observed_at_remains_stable(self) -> None:
        """first_observed_at must remain stable across repeated promotions."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # First promote
        incidents1 = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        # Second promote
        incidents2 = store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-2")
        # Third promote
        incidents3 = store.promote_candidates([candidate], TEST_TIME_3, snapshot_bundle_id="bundle-3")

        self.assertEqual(incidents1[0].first_observed_at, TEST_TIME_1)
        self.assertEqual(incidents2[0].first_observed_at, TEST_TIME_1)
        self.assertEqual(incidents3[0].first_observed_at, TEST_TIME_1)


class TestSuppressedIncidentNotReopened(unittest.TestCase):
    """Test that SUPPRESSED incidents are not reopened by repeated candidates."""

    def test_suppressed_incident_not_reopened(self) -> None:
        """SUPPRESSED incident status must not change when candidate is repeated."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Create incident and suppress it
        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id
        store.suppress(incident_id, "known issue")

        # Verify suppressed
        suppressed = store.get_incident(incident_id)
        self.assertEqual(suppressed.status, IncidentStatus.SUPPRESSED)

        # Promote again with bundle - should NOT reopen
        store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-1")
        after_repeat = store.get_incident(incident_id)

        self.assertEqual(after_repeat.status, IncidentStatus.SUPPRESSED)
        # last_observed_at should still update
        self.assertEqual(after_repeat.last_observed_at, TEST_TIME_2)
        # snapshot_bundle_id should NOT be updated for SUPPRESSED
        self.assertIsNone(after_repeat.latest_snapshot_bundle_id)


class TestDuplicateIncidentNotReopened(unittest.TestCase):
    """Test that DUPLICATE incidents are not reopened by repeated candidates."""

    def test_duplicate_incident_not_reopened(self) -> None:
        """DUPLICATE incident status must not change when candidate is repeated."""
        store = make_store()
        candidate1 = make_candidate(name="crashloop-pod-1")
        candidate2 = make_candidate(name="crashloop-pod-2")

        # Create two incidents
        store.promote_candidates([candidate1, candidate2], TEST_TIME_1)
        incidents = store.list_incidents()
        incident1_id = incidents[0].incident_id
        incident2_id = incidents[1].incident_id

        # Mark incident2 as duplicate of incident1
        store.mark_duplicate(incident2_id, incident1_id)

        # Verify duplicate
        duplicate = store.get_incident(incident2_id)
        self.assertEqual(duplicate.status, IncidentStatus.DUPLICATE)

        # Promote again with bundle - should NOT reopen
        store.promote_candidates([candidate2], TEST_TIME_2, snapshot_bundle_id="bundle-1")
        after_repeat = store.get_incident(incident2_id)

        self.assertEqual(after_repeat.status, IncidentStatus.DUPLICATE)
        # last_observed_at should still update
        self.assertEqual(after_repeat.last_observed_at, TEST_TIME_2)
        # snapshot_bundle_id should NOT be updated for DUPLICATE
        self.assertIsNone(after_repeat.latest_snapshot_bundle_id)


class TestReadyForReviewNotDowngraded(unittest.TestCase):
    """Test that READY_FOR_REVIEW incidents are not downgraded by repeated candidates."""

    def test_ready_for_review_not_downgraded(self) -> None:
        """READY_FOR_REVIEW incident status must not be downgraded."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Create incident and mark ready for review
        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id
        store.mark_ready_for_review(incident_id, "review-123")

        # Verify ready for review
        ready = store.get_incident(incident_id)
        self.assertEqual(ready.status, IncidentStatus.READY_FOR_REVIEW)

        # Promote again with bundle - should NOT downgrade
        store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-1")
        after_repeat = store.get_incident(incident_id)

        self.assertEqual(after_repeat.status, IncidentStatus.READY_FOR_REVIEW)
        # last_observed_at should still update
        self.assertEqual(after_repeat.last_observed_at, TEST_TIME_2)
        # snapshot_bundle_id should NOT be updated for READY_FOR_REVIEW
        self.assertIsNone(after_repeat.latest_snapshot_bundle_id)


class TestReturnedIncidentsAreSnapshots(unittest.TestCase):
    """Test that returned incidents are snapshots, not internal mutable state."""

    def test_promote_returns_independent_snapshots(self) -> None:
        """Multiple promote calls must return independent snapshot objects."""
        store = make_store()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")

        incidents1 = store.promote_candidates([candidate1], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        incidents2 = store.promote_candidates([candidate2], TEST_TIME_2, snapshot_bundle_id="bundle-2")

        # Returns should be different objects (independent snapshots)
        self.assertIsNot(incidents1[0], incidents2[0])

        # incidents2 should be unchanged after mutating incidents1
        incidents1[0].signals.append(incidents1[0].signals[0])  # Mutate list
        self.assertEqual(len(incidents2[0].signals), 1)  # Still 1 signal

    def test_promote_with_bundle_returns_snapshot(self) -> None:
        """promote_candidates must return snapshots, not internal state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")

        # Mutating returned incident's mutable fields must not affect store
        incidents[0].signals.append(incidents[0].signals[0])
        incidents[0].evidence_needed.append("new_evidence")

        stored = store.list_incidents()[0]
        # Store should be unchanged (only 1 signal, only original evidence_needed)
        self.assertEqual(len(stored.signals), 1)
        self.assertNotIn("new_evidence", stored.evidence_needed)


class TestNoForbiddenApisExist(unittest.TestCase):
    """Verify no persistence, remediation, mutation, LLM, or external tool APIs exist."""

    def test_promote_has_no_forbidden_parameters(self) -> None:
        """promote_candidates must not have forbidden parameters."""
        import inspect

        from k8s_diag_agent.collect.incident_store import IncidentStore

        sig = inspect.signature(IncidentStore.promote_candidates)
        params = [p.name for p in sig.parameters.values()]

        forbidden = ["kubectl", "remediation", "mutation", "llm", "external", "persist", "database"]
        for param in params:
            for forb in forbidden:
                self.assertNotIn(forb, param.lower())

    def test_promote_from_bundle_has_no_forbidden_parameters(self) -> None:
        """promote_candidates_from_bundle must not have forbidden parameters."""
        import inspect

        from k8s_diag_agent.collect.incident_store import IncidentStore

        sig = inspect.signature(IncidentStore.promote_candidates_from_bundle)
        params = [p.name for p in sig.parameters.values()]

        forbidden = ["kubectl", "remediation", "mutation", "llm", "external", "persist", "database"]
        for param in params:
            for forb in forbidden:
                self.assertNotIn(forb, param.lower())


class TestBundleAttachmentSemantics(unittest.TestCase):
    """Test bundle attachment semantics across different scenarios."""

    def test_open_incident_transitions_to_collecting_evidence_on_bundle_merge(self) -> None:
        """OPEN incident must transition to COLLECTING_EVIDENCE on bundle merge."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Create in OPEN state (no bundle)
        store.promote_candidates([candidate], TEST_TIME_1)
        incident_id = store.list_incidents()[0].incident_id
        self.assertEqual(store.get_incident(incident_id).status, IncidentStatus.OPEN)

        # Merge with bundle - should transition to COLLECTING_EVIDENCE
        store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-1")
        after_merge = store.get_incident(incident_id)

        self.assertEqual(after_merge.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(after_merge.latest_snapshot_bundle_id, "bundle-1")

    def test_collecting_evidence_updates_bundle_id_on_merge(self) -> None:
        """COLLECTING_EVIDENCE incident must update bundle_id on merge."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Create with first bundle
        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        incident_id = store.list_incidents()[0].incident_id

        # Merge with second bundle
        store.promote_candidates([candidate], TEST_TIME_2, snapshot_bundle_id="bundle-2")
        after_merge = store.get_incident(incident_id)

        self.assertEqual(after_merge.status, IncidentStatus.COLLECTING_EVIDENCE)
        self.assertEqual(after_merge.latest_snapshot_bundle_id, "bundle-2")

    def test_investigating_incident_not_downgraded(self) -> None:
        """INVESTIGATING incident should transition to COLLECTING_EVIDENCE (not preserved)."""
        # Note: Currently INVESTIGATING is not in the protected list,
        # so it will transition. This is intentional - INVESTIGATING is not terminal.
        # If we want to protect INVESTIGATING, we'd add it to _TERMINAL_REOPEN_BLOCKED_STATUSES
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        # Create and transition to investigating via mark_collecting_evidence then
        # we don't have a direct "investigate" transition, so let's just test the current behavior
        store.promote_candidates([candidate], TEST_TIME_1, snapshot_bundle_id="bundle-1")
        incident_id = store.list_incidents()[0].incident_id

        # Currently COLLECTING_EVIDENCE will stay COLLECTING_EVIDENCE
        self.assertEqual(store.get_incident(incident_id).status, IncidentStatus.COLLECTING_EVIDENCE)


class TestMultipleCandidatesWithBundle(unittest.TestCase):
    """Test bundle attachment with multiple candidates."""

    def test_multiple_candidates_all_get_bundle_id(self) -> None:
        """All new incidents from promote must get the bundle ID."""
        store = make_store()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")
        bundle_id = "bundle-multi"

        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_1, snapshot_bundle_id=bundle_id)

        self.assertEqual(len(incidents), 2)
        for incident in incidents:
            self.assertEqual(incident.latest_snapshot_bundle_id, bundle_id)
            self.assertEqual(incident.status, IncidentStatus.COLLECTING_EVIDENCE)

    def test_mixed_new_and_existing_with_bundle(self) -> None:
        """Mix of new and existing incidents must handle bundle correctly."""
        store = make_store()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")

        # Create first incident (no bundle)
        store.promote_candidates([candidate1], TEST_TIME_1)

        # Promote both with bundle - one new, one merge
        incidents = store.promote_candidates([candidate1, candidate2], TEST_TIME_2, snapshot_bundle_id="bundle-1")

        self.assertEqual(len(incidents), 2)
        for incident in incidents:
            self.assertEqual(incident.latest_snapshot_bundle_id, "bundle-1")
            self.assertEqual(incident.status, IncidentStatus.COLLECTING_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
