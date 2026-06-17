"""Tests for next_check_incident_linkage_enrichment module.

These tests verify the enrich_next_check_candidate_dict() and
enrich_next_check_plan_dict() functions.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
    LINKAGE_SCHEMA_VERSION,
    build_next_check_incident_linkage,
    enrich_next_check_candidate_dict,
    enrich_next_check_plan_dict,
)

from .next_check_incident_linkage_fixtures import make_linkage_context

# =============================================================================
# Test Cases: Candidate Dict Enrichment
# =============================================================================


class TestEnrichNextCheckCandidateDict(unittest.TestCase):
    """Test candidate dict enrichment with strict structured matching."""

    def test_candidate_id_matching_source_candidate_gets_linked(self) -> None:
        """enrich_next_check_candidate_dict links when candidateId matches source_candidate_id."""
        original = {
            "candidateId": "c1",
            "description": "Check pod logs",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Matches candidateId
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")

    def test_full_structured_identity_match_gets_linked(self) -> None:
        """enrich_next_check_candidate_dict links when all four structured fields match."""
        original = {
            "candidateId": "c2",
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": "test-pod",
            "candidateClass": "crash_loop",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")

    def test_description_mentioning_namespace_does_not_become_linked(self) -> None:
        """enrich_next_check_candidate_dict does NOT link based on description text matching."""
        original = {
            "candidateId": "c2",
            "description": "Check pod logs for default namespace",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_generic_kubectl_describe_does_not_become_linked(self) -> None:
        """enrich_next_check_candidate_dict does NOT link generic kubectl commands."""
        original = {
            "candidateId": "c3",
            "description": "Describe the pod to check status",
            "suggestedCommandFamily": "kubectl describe",
            "targetCluster": "cluster-a",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_unrelated_candidate_gets_partial_without_incident_id(self) -> None:
        """enrich_next_check_candidate_dict sets partial WITHOUT incident_id for unrelated candidates."""
        original = {
            "candidateId": "c2",
            "description": "Check deployment status for api-server",
            "targetCluster": "cluster-b",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_bogus_incident_id_is_removed(self) -> None:
        """Provider-supplied bogus incident_id is removed when no explicit match exists."""
        original = {
            "candidateId": "c2",
            "incident_id": "bogus-provider-injected-id",
            "description": "Check deployment",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_incident_id_overwritten_on_explicit_match(self) -> None:
        """Provider-supplied incident_id is overwritten when explicit structured match exists."""
        original = {
            "candidateId": "c1",
            "incident_id": "provider-wrong-id",
            "description": "Check pod logs",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")

    def test_unrelated_candidate_preserves_original_fields(self) -> None:
        """enrich_next_check_candidate_dict preserves original fields for unrelated candidates."""
        original = {
            "candidateId": "c2",
            "description": "Check api-server deployment",
            "safeToAutomate": True,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["candidateId"], "c2")
        self.assertEqual(enriched["description"], "Check api-server deployment")
        self.assertEqual(enriched["safeToAutomate"], True)
        self.assertEqual(enriched["linkage_status"], "partial")
        self.assertNotIn("incident_id", enriched)

    def test_original_dict_unchanged(self) -> None:
        """enrich_next_check_candidate_dict does not mutate original."""
        original = {"candidateId": "c1", "description": "Check pod logs"}
        context = make_linkage_context(incident_id="inc-001")
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", original)


# =============================================================================
# Test Cases: All-None Structured Fields
# =============================================================================


class TestAllNoneStructuredFields(unittest.TestCase):
    """Regression tests for all-None structured fields."""

    def test_all_none_structured_fields_do_not_match(self) -> None:
        """All-None structured fields on candidate do NOT trigger full-identity match."""
        original = {
            "candidateId": "c2",
            "namespace": None,
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_linkage_fields_all_none_do_not_match(self) -> None:
        """All-None structured fields on linkage context do NOT trigger full-identity match."""
        original = {
            "candidateId": "c1",
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": "test-pod",
            "candidateClass": "crash_loop",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_partial_presence_does_not_match(self) -> None:
        """Partial presence of structured fields (1-3 fields) does NOT trigger full-identity match."""
        original = {
            "candidateId": "c2",
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")


# =============================================================================
# Test Cases: Provider Matching
# =============================================================================


class TestProviderMatchingIncidentIdAlone(unittest.TestCase):
    """Regression tests for provider-supplied matching incident_id."""

    def test_provider_matching_incident_id_alone_does_not_link(self) -> None:
        """Provider-supplied matching incident_id WITHOUT explicit candidateId match does NOT link."""
        original = {
            "candidateId": "c2",
            "incident_id": "default-pod-test-pod-crash-loop",
            "namespace": None,
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_matching_incident_id_overwritten_on_candidate_id_match(self) -> None:
        """Provider incident_id IS overwritten when candidateId matches source_candidate_id."""
        original = {
            "candidateId": "c1",
            "incident_id": "provider-wrong-id",
            "namespace": None,
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")

    def test_provider_matching_incident_id_overwritten_on_full_match(self) -> None:
        """Provider incident_id IS overwritten when full 4-field structured match exists."""
        original = {
            "candidateId": "c2",
            "incident_id": "provider-wrong-id",
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": "test-pod",
            "candidateClass": "crash_loop",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")


# =============================================================================
# Test Cases: Plan Dict Enrichment
# =============================================================================


class TestEnrichNextCheckPlanDict(unittest.TestCase):
    """Test plan dict enrichment."""

    def test_adds_linkage_fields_to_plan(self) -> None:
        """enrich_next_check_plan_dict adds plan-level linkage fields."""
        original = {
            "review_path": "/path/to/review",
            "candidates": [],
        }
        context = make_linkage_context(run_id="run-123", incident_id="inc-001")
        plan_linkage, _ = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_plan_dict(original, plan_linkage)

        self.assertEqual(enriched["review_path"], "/path/to/review")
        self.assertEqual(enriched["linkage_schema_version"], LINKAGE_SCHEMA_VERSION)
        self.assertEqual(enriched["run_id"], "run-123")
        self.assertEqual(enriched["linkage_status"], "linked")


if __name__ == "__main__":
    unittest.main()
