"""Tests for incident_suggested_check_mapping classifier.

These tests verify the mapping classification logic for next-check-to-incident mapping.

Required test cases:
1. direct incident_id exact match is safe
2. direct incident_id missing incident is unsafe
3. run_id + source_candidate_id unique match is safe, if available
4. run_id + source_candidate_id duplicate match is ambiguous
5. bundle-only match with multiple incidents is ambiguous
6. entity-only match is ambiguous
7. text-only match is unsafe
8. missing required fields is unsafe
9. classifier returns a human-readable reason
10. classifier does not mutate incidents or artifacts
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.incident_suggested_check_mapping import (
    MappingDecision,
    classify_next_check_mapping_candidate,
    explain_next_check_mapping_candidate,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def make_incident(
    incident_id: str,
    namespace: str = "default",
    object_kind: str = "Pod",
    object_name: str = "test-pod",
    candidate_class: str = "crash_loop",
    source_candidate_id: str = "test-candidate",
    latest_snapshot_bundle_id: str | None = None,
    signals_run_ids: list[str] | None = None,
) -> dict:
    """Create a test incident dict."""
    signals = []
    if signals_run_ids:
        signals = [{"run_id": rid, "source": "pod", "reason": "test", "message": "test"} for rid in signals_run_ids]
    return {
        "incident_id": incident_id,
        "namespace": namespace,
        "object_kind": object_kind,
        "object_name": object_name,
        "candidate_class": candidate_class,
        "source_candidate_id": source_candidate_id,
        "latest_snapshot_bundle_id": latest_snapshot_bundle_id,
        "signals": signals,
    }


def make_next_check_candidate(
    description: str = "Check pod logs",
    candidate_id: str | None = None,
    incident_id: str | None = None,
    namespace: str | None = None,
    object_kind: str | None = None,
    object_name: str | None = None,
    candidate_class: str | None = None,
    latest_snapshot_bundle_id: str | None = None,
    artifact_path: str | None = None,
) -> dict:
    """Create a test next-check candidate dict."""
    candidate: dict = {"description": description}
    if candidate_id:
        candidate["candidateId"] = candidate_id
    if incident_id:
        candidate["incident_id"] = incident_id
    if namespace:
        candidate["namespace"] = namespace
    if object_kind:
        candidate["objectKind"] = object_kind
    if object_name:
        candidate["objectName"] = object_name
    if candidate_class:
        candidate["candidateClass"] = candidate_class
    if latest_snapshot_bundle_id:
        candidate["latest_snapshot_bundle_id"] = latest_snapshot_bundle_id
    if artifact_path:
        candidate["artifactPath"] = artifact_path
    return candidate


# =============================================================================
# Test Cases
# =============================================================================


class TestDirectIncidentIdMatch(unittest.TestCase):
    """Test direct incident_id matching."""

    def test_direct_incident_id_exact_match_is_safe(self) -> None:
        """Direct incident_id exact match should be classified as safe."""
        incident = make_incident("default-pod-my-pod-crash-loop")
        candidate = make_next_check_candidate(incident_id="default-pod-my-pod-crash-loop")

        result = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(result.confidence, "safe")
        self.assertEqual(result.matched_incident_id, "default-pod-my-pod-crash-loop")
        self.assertIn("incident_id", result.required_fields)

    def test_direct_incident_id_missing_incident_is_unsafe(self) -> None:
        """Direct incident_id with no matching incident should be classified as unsafe."""
        candidate = make_next_check_candidate(incident_id="nonexistent-incident")

        result = classify_next_check_mapping_candidate(candidate, [])

        self.assertEqual(result.confidence, "unsafe")
        self.assertIsNone(result.matched_incident_id)
        self.assertIn("incident_id", result.required_fields)


class TestRunIdAndCandidateIdMatch(unittest.TestCase):
    """Test run_id + candidate_id matching."""

    def test_run_id_plus_candidate_id_unique_match_is_conditionally_safe(self) -> None:
        """Unique run_id + candidate_id match should be conditionally safe."""
        incident = make_incident(
            "default-pod-my-pod-crash-loop",
            source_candidate_id="my-candidate",
            signals_run_ids=["run-123"],
        )
        candidate = make_next_check_candidate(
            candidate_id="my-candidate",
            artifact_path="runs/health/external-analysis/run-123-next-check-plan.json",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(result.confidence, "conditionally_safe")
        self.assertIsNotNone(result.matched_incident_id)
        self.assertIn("run_id", result.required_fields)
        self.assertIn("candidateId", result.required_fields)

    def test_duplicate_run_id_plus_candidate_id_is_ambiguous(self) -> None:
        """Duplicate run_id + candidate_id match should be classified as ambiguous.

        When the same run_id + candidateId pair matches multiple incidents,
        we cannot determine a unique mapping, so it is ambiguous.
        """
        incident1 = make_incident(
            "inc-1",
            source_candidate_id="my-candidate",
            signals_run_ids=["run-123"],
        )
        incident2 = make_incident(
            "inc-2",
            source_candidate_id="my-candidate",
            signals_run_ids=["run-123"],
        )
        candidate = make_next_check_candidate(
            candidate_id="my-candidate",
            artifact_path="runs/health/external-analysis/run-123-next-check-plan.json",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident1, incident2])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)
        self.assertIn("run_id", result.required_fields)
        self.assertIn("candidateId", result.required_fields)

    def test_entity_identity_duplicate_match_is_ambiguous(self) -> None:
        """Duplicate entity identity match across runs should be classified as ambiguous.

        Note: run_id + candidate_id uniqueness check returns False when there are
        multiple matches (len != 1), causing fallthrough to entity identity match.
        When entity identity matches multiple incidents, that is ambiguous.
        """
        # Two incidents with same entity identity (same pod recurs across runs)
        incident1 = make_incident(
            "default-pod-my-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
            source_candidate_id="default-pod-my-pod-crash-loop",
        )
        incident2 = make_incident(
            "default-pod-my-pod-crash-loop-v2",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
            source_candidate_id="default-pod-my-pod-crash-loop",
        )
        # Candidate with entity identity (no run_id extraction possible)
        candidate = make_next_check_candidate(
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident1, incident2])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)


class TestBundleMatch(unittest.TestCase):
    """Test bundle_id matching."""

    def test_bundle_only_match_with_multiple_incidents_is_ambiguous(self) -> None:
        """Bundle match with multiple incidents should be classified as ambiguous."""
        incident1 = make_incident("inc-1", latest_snapshot_bundle_id="bundle-xyz")
        incident2 = make_incident("inc-2", latest_snapshot_bundle_id="bundle-xyz")
        candidate = make_next_check_candidate(latest_snapshot_bundle_id="bundle-xyz")

        result = classify_next_check_mapping_candidate(candidate, [incident1, incident2])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)
        self.assertIn("latest_snapshot_bundle_id", result.required_fields)


class TestEntityIdentityMatch(unittest.TestCase):
    """Test entity identity matching (namespace + kind + name + class)."""

    def test_namespace_only_is_not_conditionally_safe(self) -> None:
        """Candidate with only namespace should NOT be classified as conditionally_safe.

        Partial entity identity is ambiguous, not safe.
        """
        incident = make_incident(
            "default-pod-my-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )
        # Candidate with only namespace
        candidate = make_next_check_candidate(namespace="default")

        result = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)

    def test_namespace_kind_only_is_not_conditionally_safe(self) -> None:
        """Candidate with only namespace+kind should NOT be classified as conditionally_safe.

        Partial entity identity (missing name and class) is ambiguous.
        """
        incident = make_incident(
            "default-pod-my-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )
        # Candidate with only namespace + kind
        candidate = make_next_check_candidate(
            namespace="default",
            object_kind="Pod",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)

    def test_entity_only_match_is_ambiguous_across_runs(self) -> None:
        """Entity match across runs should be classified as ambiguous (may recur)."""
        incident1 = make_incident(
            "default-pod-my-pod-crash-loop-v1",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )
        incident2 = make_incident(
            "default-pod-my-pod-crash-loop-v2",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )
        candidate = make_next_check_candidate(
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident1, incident2])

        self.assertEqual(result.confidence, "ambiguous")
        self.assertIsNone(result.matched_incident_id)

    def test_entity_identity_unique_match_is_conditionally_safe(self) -> None:
        """Unique entity match (all 4 fields) should be conditionally safe."""
        incident = make_incident(
            "default-pod-my-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )
        candidate = make_next_check_candidate(
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
            candidate_class="crash_loop",
        )

        result = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(result.confidence, "conditionally_safe")
        self.assertIsNotNone(result.matched_incident_id)


class TestTextOnlyMatch(unittest.TestCase):
    """Test text-only matching."""

    def test_text_only_match_is_unsafe(self) -> None:
        """Text-only match (description only) should be classified as unsafe."""
        candidate = make_next_check_candidate(
            description="Check pod logs for crash loop errors"
        )

        result = classify_next_check_mapping_candidate(candidate, [])

        self.assertEqual(result.confidence, "unsafe")
        self.assertIn("deterministic", result.reason.lower())

    def test_title_only_match_is_unsafe(self) -> None:
        """Title-only match should be classified as unsafe."""
        candidate = {"title": "Inspect pod logs"}

        result = classify_next_check_mapping_candidate(candidate, [])

        self.assertEqual(result.confidence, "unsafe")


class TestMissingFields(unittest.TestCase):
    """Test missing required fields."""

    def test_missing_all_fields_is_unsafe(self) -> None:
        """Empty candidate with no fields should be classified as unsafe."""
        candidate: dict = {}

        result = classify_next_check_mapping_candidate(candidate, [])

        self.assertEqual(result.confidence, "unsafe")
        self.assertIn("incident_id", result.required_fields)


class TestMappingDecision(unittest.TestCase):
    """Test MappingDecision helper methods."""

    def test_is_safe_returns_true_for_safe_confidence(self) -> None:
        """is_safe() should return True for safe confidence."""
        decision = MappingDecision(
            confidence="safe",
            reason="test",
            required_fields=("incident_id",),
            matched_incident_id="test",
        )
        self.assertTrue(decision.is_safe())

    def test_is_safe_returns_false_for_unsafe_confidence(self) -> None:
        """is_safe() should return False for non-safe confidence."""
        decision = MappingDecision(
            confidence="unsafe",
            reason="test",
            required_fields=("incident_id",),
            matched_incident_id=None,
        )
        self.assertFalse(decision.is_safe())

    def test_is_usable_returns_true_for_safe_and_conditionally_safe(self) -> None:
        """is_usable() should return True for safe and conditionally_safe."""
        safe_decision = MappingDecision(
            confidence="safe",
            reason="test",
            required_fields=(),
            matched_incident_id="test",
        )
        cond_decision = MappingDecision(
            confidence="conditionally_safe",
            reason="test",
            required_fields=(),
            matched_incident_id="test",
        )
        self.assertTrue(safe_decision.is_usable())
        self.assertTrue(cond_decision.is_usable())

    def test_requires_fields_works(self) -> None:
        """requires_fields() should check field availability."""
        decision = MappingDecision(
            confidence="safe",
            reason="test",
            required_fields=("incident_id", "run_id"),
            matched_incident_id="test",
        )
        self.assertTrue(decision.requires_fields("incident_id"))
        self.assertFalse(decision.requires_fields("namespace"))


class TestExplainNextCheckMappingCandidate(unittest.TestCase):
    """Test human-readable explanation generation."""

    def test_explain_returns_readable_output(self) -> None:
        """explain_next_check_mapping_candidate should return readable text."""
        incident = make_incident("default-pod-my-pod-crash-loop")
        candidate = make_next_check_candidate(incident_id="default-pod-my-pod-crash-loop")

        explanation = explain_next_check_mapping_candidate(candidate, [incident])

        self.assertIn("safe", explanation)
        self.assertIn("incident_id", explanation)
        self.assertIn("Matched incident_id", explanation)


class TestNoMutation(unittest.TestCase):
    """Test that classifier does not mutate inputs."""

    def test_classifier_does_not_mutate_incidents(self) -> None:
        """Classifier should not modify the incidents list."""
        incident = make_incident("test-incident")
        original_signals = list(incident.get("signals", []))
        candidate = make_next_check_candidate(incident_id="test-incident")

        classify_next_check_mapping_candidate(candidate, [incident])

        # Verify signals unchanged
        self.assertEqual(incident.get("signals"), original_signals)

    def test_classifier_does_not_mutate_candidate(self) -> None:
        """Classifier should not modify the candidate dict."""
        candidate = make_next_check_candidate(
            description="Test description",
            candidate_id="test-candidate",
        )
        original_description = candidate.get("description")

        classify_next_check_mapping_candidate(candidate, [])

        # Verify description unchanged
        self.assertEqual(candidate.get("description"), original_description)


class TestCurrentStateVerification(unittest.TestCase):
    """Verify current state: no safe mappings exist with current artifact shapes."""

    def test_current_plan_artifact_has_no_incident_id(self) -> None:
        """Current next-check plan artifacts do not have incident_id field."""
        # This is the current artifact shape from next-check-plan.json
        current_plan_candidate = {
            "candidateId": "c1",
            "description": "Check pod logs",
            "targetCluster": "cluster-a",
            "sourceReason": "CrashLoopBackOff investigation",
            "suggestedCommandFamily": "kubectl-logs",
            "safeToAutomate": True,
        }

        result = classify_next_check_mapping_candidate(current_plan_candidate, [])

        # Should be unsafe because incident_id is missing
        self.assertEqual(result.confidence, "unsafe")
        self.assertIn("incident_id", result.required_fields)

    def test_current_plan_artifact_has_no_entity_fields(self) -> None:
        """Current next-check plan artifacts do not have entity identity fields."""
        current_plan_candidate = {
            "description": "Check pod logs",
            "candidateId": "c1",
            "sourceReason": "CrashLoopBackOff",
        }

        result = classify_next_check_mapping_candidate(current_plan_candidate, [])

        # Should be unsafe (no entity fields)
        self.assertEqual(result.confidence, "unsafe")


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    unittest.main()
