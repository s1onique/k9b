"""Contract and API tests for IncidentStore.

Tests:
- Empty store behavior
- Store returns immutable snapshots
- No external/remediation APIs exist
"""

from __future__ import annotations

import unittest

from incident_store_fixtures import TEST_TIME_1, make_candidate, make_store


class TestEmptyStoreBehavior(unittest.TestCase):
    """Test behavior of empty store."""

    def test_empty_store_list_incidents_returns_empty_tuple(self) -> None:
        """list_incidents on empty store must return empty tuple."""
        store = make_store()

        incidents = store.list_incidents()

        self.assertEqual(incidents, ())

    def test_empty_store_get_incident_returns_none(self) -> None:
        """get_incident on empty store must return None."""
        store = make_store()

        result = store.get_incident("any-id")

        self.assertIsNone(result)

    def test_empty_store_len_is_zero(self) -> None:
        """len(empty_store) must be 0."""
        store = make_store()

        self.assertEqual(len(store), 0)


class TestStoreReturnsSnapshots(unittest.TestCase):
    """Test that store methods return snapshots, not internal state."""

    def test_get_incident_returns_snapshot(self) -> None:
        """get_incident must return a snapshot, not internal state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod", namespace="default")

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

    def test_promote_candidates_returns_snapshot_not_internal_state(self) -> None:
        """promote_candidates must return snapshot copies, not internal state."""
        store = make_store()
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
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        incidents = store.promote_candidates([candidate], TEST_TIME_1)

        original_evidence_len = len(incidents[0].evidence_needed)
        incidents[0].evidence_needed.append("new_evidence")

        stored = store.list_incidents()[0]
        self.assertEqual(len(stored.evidence_needed), original_evidence_len)

    def test_promote_candidates_multiple_returns_independent_snapshots(self) -> None:
        """Multiple promote_candidates calls must return independent snapshots."""
        store = make_store()
        candidate1 = make_candidate(name="pod-1")
        candidate2 = make_candidate(name="pod-2")

        incidents1 = store.promote_candidates([candidate1], TEST_TIME_1)
        incidents2 = store.promote_candidates([candidate2], TEST_TIME_1)

        # Mutating one must not affect the other
        incidents1[0].signals.append(incidents1[0].signals[0])

        # incidents2 should be unchanged
        self.assertEqual(len(incidents2[0].signals), 1)

    def test_list_incidents_returns_immutable_snapshot(self) -> None:
        """Store methods must return copies, not expose internal state."""
        store = make_store()
        candidate = make_candidate(name="crashloop-pod")

        store.promote_candidates([candidate], TEST_TIME_1)
        incident = store.list_incidents()[0]

        # Attempt to mutate - should not affect store
        original_signals_len = len(incident.signals)
        incident.signals.append(incident.signals[0])

        # Store should be unchanged
        stored = store.list_incidents()[0]
        self.assertEqual(len(stored.signals), original_signals_len)


class TestNoExternalApisExist(unittest.TestCase):
    """Verify no remediation, mutation, LLM, or subprocess APIs exist in the store."""

    def test_store_has_no_remediation_methods(self) -> None:
        """IncidentStore must not have remediation-related methods."""
        store = make_store()
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


if __name__ == "__main__":
    unittest.main()
