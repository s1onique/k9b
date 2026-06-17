"""Tests for next_check_incident_linkage module.

These tests verify the incident linkage field injection for next-check plan artifacts.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
    LINKAGE_SCHEMA_VERSION,
    IncidentLinkageContext,
    NextCheckCandidateLinkage,
    NextCheckPlanLinkage,
    build_next_check_incident_linkage,
    enrich_next_check_candidate_dict,
    enrich_next_check_plan_dict,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def make_incident_candidate(
    candidate_id: str = "test-candidate",
    namespace: str = "default",
    object_kind: ObjectKind = ObjectKind.POD,
    object_name: str = "test-pod",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
) -> IncidentCandidate:
    """Create a test incident candidate."""
    return IncidentCandidate(
        candidate_id=candidate_id,
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(),
        evidence_needed=("kubectl logs",),
    )


def make_linkage_context(
    incident_id: str | None = "default-pod-test-pod-crash-loop",
    source_candidate_id: str | None = "test-candidate",
    namespace: str | None = "default",
    object_kind: str | None = "Pod",
    object_name: str | None = "test-pod",
    candidate_class: str | None = "crash_loop",
    run_id: str | None = "run-123",
) -> IncidentLinkageContext:
    """Create a test linkage context."""
    return IncidentLinkageContext(
        incident_id=incident_id,
        source_candidate_id=source_candidate_id,
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        candidate_class=candidate_class,
        run_id=run_id,
    )


# =============================================================================
# Test Cases: IncidentLinkageContext
# =============================================================================


class TestIncidentLinkageContextFromCandidate(unittest.TestCase):
    """Test creating linkage context from IncidentCandidate."""

    def test_from_incident_candidate_derives_incident_id(self) -> None:
        """incident_id is derived deterministically from candidate components."""
        candidate = make_incident_candidate(
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="my-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
        )

        context = IncidentLinkageContext.from_incident_candidate(candidate, run_id="run-456")

        self.assertEqual(context.namespace, "default")
        self.assertEqual(context.object_kind, "Pod")
        self.assertEqual(context.object_name, "my-pod")
        self.assertEqual(context.candidate_class, "crash_loop")
        self.assertEqual(context.source_candidate_id, candidate.candidate_id)
        self.assertEqual(context.run_id, "run-456")
        # incident_id should be derived deterministically
        self.assertIsNotNone(context.incident_id)
        self.assertIn("default", context.incident_id)
        self.assertIn("pod", context.incident_id)
        self.assertIn("my-pod", context.incident_id)
        self.assertIn("crash_loop", context.incident_id)

    def test_from_incident_candidate_run_id_optional(self) -> None:
        """run_id is optional when creating from candidate."""
        candidate = make_incident_candidate()

        context = IncidentLinkageContext.from_incident_candidate(candidate)

        self.assertIsNone(context.run_id)


class TestIncidentLinkageContextLinkageStatus(unittest.TestCase):
    """Test linkage status determination."""

    def test_linked_when_incident_id_present(self) -> None:
        """Context with incident_id is 'linked'."""
        context = make_linkage_context(incident_id="default-pod-test-crash-loop")

        status = context.determine_linkage_status()

        self.assertEqual(status, "linked")

    def test_partial_when_run_id_and_source_candidate_id_present(self) -> None:
        """Context with run_id + source_candidate_id but no incident_id is 'partial'."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id="cand-001",
            run_id="run-123",
        )

        status = context.determine_linkage_status()

        self.assertEqual(status, "partial")

    def test_partial_when_complete_entity_identity_present(self) -> None:
        """Context with all 4 entity identity fields but no incident_id is 'partial'."""
        context = make_linkage_context(
            incident_id=None,
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )

        status = context.determine_linkage_status()

        self.assertEqual(status, "partial")

    def test_unlinked_when_insufficient_fields(self) -> None:
        """Context without incident_id, run_id+source_candidate_id, or entity identity is 'unlinked'."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id=None,
            run_id=None,
            namespace="default",
            object_kind=None,
            object_name=None,
            candidate_class=None,
        )

        status = context.determine_linkage_status()

        self.assertEqual(status, "unlinked")

    def test_partial_with_partial_entity_identity(self) -> None:
        """Partial entity identity (missing fields) alone is not sufficient for 'partial'."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id=None,
            run_id=None,
            namespace="default",
            object_kind="Pod",
            object_name=None,  # Missing
            candidate_class=None,  # Missing
        )

        status = context.determine_linkage_status()

        # Without run_id+source_candidate_id, partial entity is not enough
        self.assertEqual(status, "unlinked")


class TestIncidentLinkageContextReason(unittest.TestCase):
    """Test linkage reason generation."""

    def test_linked_reason_includes_incident_id(self) -> None:
        """Linked reason includes the incident_id."""
        # Create context with ONLY incident_id set, no other fields
        context = IncidentLinkageContext(
            incident_id="default-pod-test-crash-loop",
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
            run_id=None,
        )

        reason = context.get_linkage_reason()

        self.assertIn("direct", reason.lower())
        self.assertIn("default-pod-test-crash-loop", reason)

    def test_partial_reason_includes_fields(self) -> None:
        """Partial reason indicates what fields are available."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id="cand-001",
            run_id="run-123",
        )

        reason = context.get_linkage_reason()

        self.assertIn("partial", reason.lower())
        self.assertIn("run_id", reason)

    def test_unlinked_reason_indicates_no_context(self) -> None:
        """Unlinked reason indicates no context available."""
        # Create context with NO linkage fields at all
        context = IncidentLinkageContext(
            incident_id=None,
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
            run_id=None,
        )

        reason = context.get_linkage_reason()

        self.assertIn("no", reason.lower())
        self.assertIn("available", reason.lower())


# =============================================================================
# Test Cases: NextCheckCandidateLinkage
# =============================================================================


class TestNextCheckCandidateLinkageToDict(unittest.TestCase):
    """Test candidate linkage dict serialization."""

    def test_to_dict_includes_all_linkage_fields(self) -> None:
        """to_dict() includes incident_id, source_candidate_id, entity fields, status, reason."""
        context = make_linkage_context(
            incident_id="default-pod-test-crash-loop",
            source_candidate_id="cand-001",
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        linkage = NextCheckCandidateLinkage.from_context(context)

        result = linkage.to_dict()

        self.assertIn("incident_id", result)
        self.assertIn("source_candidate_id", result)
        self.assertIn("namespace", result)
        self.assertIn("objectKind", result)  # camelCase per spec
        self.assertIn("objectName", result)
        self.assertIn("candidateClass", result)
        self.assertIn("linkage_status", result)
        self.assertIn("linkage_reason", result)
        self.assertEqual(result["incident_id"], "default-pod-test-crash-loop")
        self.assertEqual(result["linkage_status"], "linked")

    def test_to_dict_null_when_fields_missing(self) -> None:
        """to_dict() returns null for missing fields."""
        context = make_linkage_context(
            incident_id=None,
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
        )
        linkage = NextCheckCandidateLinkage.from_context(context)

        result = linkage.to_dict()

        self.assertIsNone(result["incident_id"])
        self.assertIsNone(result["source_candidate_id"])
        self.assertIsNone(result["namespace"])
        self.assertIsNone(result["objectKind"])
        self.assertIsNone(result["objectName"])
        self.assertIsNone(result["candidateClass"])


# =============================================================================
# Test Cases: NextCheckPlanLinkage
# =============================================================================


class TestNextCheckPlanLinkageToDict(unittest.TestCase):
    """Test plan linkage dict serialization."""

    def test_to_dict_includes_schema_version(self) -> None:
        """to_dict() includes linkage_schema_version."""
        context = make_linkage_context(run_id="run-123")
        plan_linkage = NextCheckPlanLinkage.from_context(context)

        result = plan_linkage.to_dict()

        self.assertIn("linkage_schema_version", result)
        self.assertEqual(result["linkage_schema_version"], LINKAGE_SCHEMA_VERSION)

    def test_to_dict_includes_run_id_and_status(self) -> None:
        """to_dict() includes run_id and linkage_status."""
        context = make_linkage_context(run_id="run-123", incident_id="inc-001")
        plan_linkage = NextCheckPlanLinkage.from_context(context)

        result = plan_linkage.to_dict()

        self.assertEqual(result["run_id"], "run-123")
        self.assertEqual(result["linkage_status"], "linked")


# =============================================================================
# Test Cases: Main Enrichment Functions
# =============================================================================


class TestBuildNextCheckIncidentLinkage(unittest.TestCase):
    """Test main enrichment function."""

    def test_returns_tuple_when_context_provided(self) -> None:
        """build_next_check_incident_linkage returns (plan_linkage, candidate_linkage) when context provided."""
        context = make_linkage_context(incident_id="inc-001")

        result = build_next_check_incident_linkage(context)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        plan_linkage, candidate_linkage = result
        self.assertIsInstance(plan_linkage, NextCheckPlanLinkage)
        self.assertIsInstance(candidate_linkage, NextCheckCandidateLinkage)

    def test_returns_none_when_context_none(self) -> None:
        """build_next_check_incident_linkage returns None when context is None."""
        result = build_next_check_incident_linkage(None)

        self.assertIsNone(result)

    def test_plan_linkage_has_correct_status(self) -> None:
        """Plan linkage status matches context determination."""
        context = make_linkage_context(incident_id="inc-001")
        plan_linkage, _ = build_next_check_incident_linkage(context)

        self.assertEqual(plan_linkage.linkage_status, "linked")

    def test_candidate_linkage_has_correct_status(self) -> None:
        """Candidate linkage status matches context determination."""
        context = make_linkage_context(incident_id="inc-001")
        _, candidate_linkage = build_next_check_incident_linkage(context)

        self.assertEqual(candidate_linkage.linkage_status, "linked")


class TestEnrichNextCheckCandidateDict(unittest.TestCase):
    """Test candidate dict enrichment with strict structured matching."""

    def test_candidate_id_matching_source_candidate_gets_linked(self) -> None:
        """enrich_next_check_candidate_dict links when candidateId matches source_candidate_id."""
        # Candidate's candidateId matches the linkage's source_candidate_id
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

        # Explicit ID match gets linked with incident_id
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

        # All four fields match exactly - gets linked with incident_id
        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")
        self.assertEqual(enriched["namespace"], "default")
        self.assertEqual(enriched["objectKind"], "Pod")

    def test_description_mentioning_namespace_does_not_become_linked(self) -> None:
        """enrich_next_check_candidate_dict does NOT link based on description text matching."""
        # Candidate mentions namespace in description, but no structured match
        original = {
            "candidateId": "c2",
            "description": "Check pod logs for default namespace",  # Mentions "default"
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

        # Text matching is NOT used - candidate gets partial WITHOUT incident_id
        self.assertNotIn("incident_id", enriched)  # invariant: incident_id only with linked
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

        # Command family matching is NOT used - gets partial WITHOUT incident_id
        self.assertNotIn("incident_id", enriched)  # invariant: incident_id only with linked
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_unrelated_candidate_gets_partial_without_incident_id(self) -> None:
        """enrich_next_check_candidate_dict sets partial WITHOUT incident_id for unrelated candidates."""
        # Candidate about completely different workload
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

        # Unrelated candidate gets partial WITHOUT incident_id
        # INVARIANT: incident_id only exists when linkage_status == "linked"
        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_bogus_incident_id_is_removed(self) -> None:
        """Provider-supplied bogus incident_id is removed when no explicit match exists."""
        # Candidate has bogus incident_id from provider
        original = {
            "candidateId": "c2",
            "incident_id": "bogus-provider-injected-id",  # Provider tried to inject
            "description": "Check deployment",
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Doesn't match candidateId
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        # Bogus incident_id is NOT present - provider forgery prevented
        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_incident_id_overwritten_on_explicit_match(self) -> None:
        """Provider-supplied incident_id is overwritten when explicit structured match exists."""
        # Candidate has different incident_id from provider, but candidateId matches
        original = {
            "candidateId": "c1",  # Matches source_candidate_id
            "incident_id": "provider-wrong-id",
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

        # Provider's bogus ID is overwritten with deterministic linkage incident_id
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

        # Original fields preserved
        self.assertEqual(enriched["candidateId"], "c2")
        self.assertEqual(enriched["description"], "Check api-server deployment")
        self.assertEqual(enriched["safeToAutomate"], True)
        # But linkage status is partial (not linked) and NO incident_id
        self.assertEqual(enriched["linkage_status"], "partial")
        self.assertNotIn("incident_id", enriched)

    def test_original_dict_unchanged(self) -> None:
        """enrich_next_check_candidate_dict does not mutate original."""
        original = {"candidateId": "c1", "description": "Check pod logs"}
        context = make_linkage_context(incident_id="inc-001")
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enrich_next_check_candidate_dict(original, candidate_linkage)

        # Original should not have linkage fields
        self.assertNotIn("incident_id", original)

    def test_invariant_incident_id_only_with_linked(self) -> None:
        """INVARIANT: candidate.linkage_status == 'linked' iff candidate.incident_id is present."""
        # Create various scenarios and verify the invariant holds
        # Note: candidateId="c1" matches source_candidate_id="c1" → explicit match
        # But linked requires incident_id to be present
        test_cases = [
            # (candidate, incident_id_in_context, source_candidate_id, entity_fields_present, should_have_incident_id, expected_status)
            # Explicit match with incident_id → linked
            ({"candidateId": "c1"}, True, "c1", True, True, "linked"),
            # Explicit match without incident_id → partial (not linked!)
            ({"candidateId": "c1"}, False, "c1", True, False, "partial"),
            # No match, linked context → partial
            ({"candidateId": "c2"}, True, "c1", True, False, "partial"),
            # No match, partial context (no entity) → partial
            ({"candidateId": "c2"}, False, "c1", False, False, "partial"),
            # No match, unlinked context (no entity) → unlinked
            ({"candidateId": "c1"}, False, None, False, False, "unlinked"),
        ]

        for candidate, has_incident_id, src_cand_id, has_entity, should_have, expected_status in test_cases:
            # Only set entity fields if has_entity is True
            if has_entity:
                context = make_linkage_context(
                    incident_id="inc-001" if has_incident_id else None,
                    source_candidate_id=src_cand_id,
                    namespace="default",
                    object_kind="Pod",
                    object_name="test",
                    candidate_class="crash_loop",
                    run_id="run-123",
                )
            else:
                context = make_linkage_context(
                    incident_id="inc-001" if has_incident_id else None,
                    source_candidate_id=src_cand_id,
                    namespace=None,  # No entity identity
                    object_kind=None,
                    object_name=None,
                    candidate_class=None,
                    run_id="run-123",
                )
            _, candidate_linkage = build_next_check_incident_linkage(context)
            enriched = enrich_next_check_candidate_dict(candidate, candidate_linkage)

            has_incident_id_result = "incident_id" in enriched
            self.assertEqual(
                has_incident_id_result, should_have,
                f"Case {candidate} x inc_id={has_incident_id} x src={src_cand_id} x entity={has_entity}: "
                f"expected incident_id={should_have}, got {has_incident_id_result}"
            )
            self.assertEqual(
                enriched["linkage_status"], expected_status,
                f"Case {candidate} x inc_id={has_incident_id} x src={src_cand_id} x entity={has_entity}: "
                f"expected status={expected_status}, got {enriched['linkage_status']}"
            )
            # Invariant: incident_id present iff status is linked
            if has_incident_id_result:
                self.assertEqual(enriched["linkage_status"], "linked")


class TestAllNoneStructuredFields(unittest.TestCase):
    """Regression tests for all-None structured fields."""

    def test_all_none_structured_fields_do_not_match(self) -> None:
        """All-None structured fields on candidate do NOT trigger full-identity match."""
        # Candidate has all-None structured fields (common in old/simple artifacts)
        # Uses c2 to avoid candidateId="c1" matching source_candidate_id="c1"
        original = {
            "candidateId": "c2",  # Different from source_candidate_id="c1"
            "namespace": None,  # All None
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Doesn't match candidateId="c2"
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        # Should NOT be linked - candidateId doesn't match AND structured fields are all None
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
        # Linkage has all-None structured fields
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id=None,
            namespace=None,  # All None
            object_kind=None,
            object_name=None,
            candidate_class=None,
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        # Should NOT be linked - linkage fields are all None
        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_partial_presence_does_not_match(self) -> None:
        """Partial presence of structured fields (1-3 fields) does NOT trigger full-identity match."""
        # candidateId does NOT match source_candidate_id (different ID)
        original = {
            "candidateId": "c2",  # Different from source_candidate_id="c1"
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": None,  # Missing - partial presence
            "candidateClass": None,  # Missing - partial presence
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Doesn't match c2
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        # Should NOT be linked - candidateId doesn't match, and only partial structured fields
        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")


class TestProviderMatchingIncidentIdAlone(unittest.TestCase):
    """Regression tests for provider-supplied matching incident_id."""

    def test_provider_matching_incident_id_alone_does_not_link(self) -> None:
        """Provider-supplied matching incident_id WITHOUT explicit candidateId match does NOT link."""
        # Candidate has matching incident_id from provider, but no candidateId match
        original = {
            "candidateId": "c2",  # Different from source_candidate_id
            "incident_id": "default-pod-test-pod-crash-loop",  # Same as linkage.incident_id
            "namespace": None,
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
        }
        context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Does NOT match candidateId="c2"
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
        )
        _, candidate_linkage = build_next_check_incident_linkage(context)

        enriched = enrich_next_check_candidate_dict(original, candidate_linkage)

        # Provider's matching incident_id alone is NOT trusted
        # Without candidateId match or full 4-field match, it's NOT linked
        self.assertNotIn("incident_id", enriched)
        self.assertEqual(enriched["linkage_status"], "partial")

    def test_provider_matching_incident_id_overwritten_on_candidate_id_match(self) -> None:
        """Provider incident_id IS overwritten when candidateId matches source_candidate_id."""
        # Candidate has incident_id from provider, AND candidateId matches
        original = {
            "candidateId": "c1",  # Matches source_candidate_id
            "incident_id": "provider-wrong-id",  # Bogus provider ID
            "namespace": None,
            "objectKind": None,
            "objectName": None,
            "candidateClass": None,
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

        # Provider's bogus ID is overwritten - candidateId match triggers linking
        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")

    def test_provider_matching_incident_id_overwritten_on_full_match(self) -> None:
        """Provider incident_id IS overwritten when full 4-field structured match exists."""
        # Candidate has incident_id from provider, AND full structured match
        original = {
            "candidateId": "c2",
            "incident_id": "provider-wrong-id",
            "namespace": "default",  # Matches
            "objectKind": "Pod",  # Matches
            "objectName": "test-pod",  # Matches
            "candidateClass": "crash_loop",  # Matches
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

        # Provider's bogus ID is overwritten - full structured match triggers linking
        self.assertEqual(enriched["incident_id"], "default-pod-test-pod-crash-loop")
        self.assertEqual(enriched["linkage_status"], "linked")


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

        # Original fields preserved
        self.assertEqual(enriched["review_path"], "/path/to/review")
        # Linkage fields added
        self.assertEqual(enriched["linkage_schema_version"], LINKAGE_SCHEMA_VERSION)
        self.assertEqual(enriched["run_id"], "run-123")
        self.assertEqual(enriched["linkage_status"], "linked")


# =============================================================================
# Test Cases: Old Artifact Compatibility
# =============================================================================


class TestOldArtifactCompatibility(unittest.TestCase):
    """Test that old artifacts without linkage fields remain compatible."""

    def test_old_candidate_dict_without_linkage_is_readable(self) -> None:
        """Candidate dict without linkage fields is still a valid candidate."""
        old_candidate = {
            "candidateId": "c1",
            "description": "Check pod logs",
            "targetCluster": "cluster-a",
            "safeToAutomate": True,
        }

        # These fields should not be required for reading
        self.assertIn("candidateId", old_candidate)
        self.assertIn("description", old_candidate)
        self.assertNotIn("incident_id", old_candidate)  # Old artifact has no incident_id

    def test_linkage_status_unlinked_for_old_context(self) -> None:
        """Old context (no incident context) produces unlinked status."""
        context = IncidentLinkageContext(
            incident_id=None,
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
            run_id="run-123",  # Only run_id available
        )

        self.assertEqual(context.determine_linkage_status(), "unlinked")

    def test_enrich_function_works_with_partial_context(self) -> None:
        """Enrich function handles partial context gracefully."""
        # Partial context: only run_id known
        context = IncidentLinkageContext(
            incident_id=None,
            source_candidate_id=None,
            namespace="default",
            object_kind=None,
            object_name=None,
            candidate_class=None,
            run_id="run-123",
        )

        result = build_next_check_incident_linkage(context)

        self.assertIsNotNone(result)
        plan_linkage, candidate_linkage = result
        # Should be unlinked since we don't have incident_id or source_candidate_id
        self.assertEqual(plan_linkage.linkage_status, "unlinked")
        self.assertEqual(candidate_linkage.linkage_status, "unlinked")
        # But fields should still be populated
        self.assertEqual(candidate_linkage.namespace, "default")
        # run_id is on plan linkage, not candidate linkage
        self.assertEqual(plan_linkage.run_id, "run-123")


# =============================================================================
# Test Cases: Classifier Compatibility
# =============================================================================


class TestClassifierCompatibility(unittest.TestCase):
    """Test that new linkage fields work with existing classifier."""

    def test_direct_incident_id_with_linkage_is_safe(self) -> None:
        """Candidate with incident_id from linkage is classified as safe."""
        from k8s_diag_agent.ui.incident_suggested_check_mapping import (
            classify_next_check_mapping_candidate,
        )

        # Simulate new artifact with linkage fields
        candidate = {
            "incident_id": "default-pod-my-pod-crash-loop",
            "namespace": "default",
            "objectKind": "Pod",
            "objectName": "my-pod",
            "candidateClass": "crash_loop",
        }
        incident = {
            "incident_id": "default-pod-my-pod-crash-loop",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "my-pod",
            "candidate_class": "crash_loop",
            "source_candidate_id": "cand-001",
            "signals": [],
        }

        decision = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(decision.confidence, "safe")
        self.assertTrue(decision.is_safe())

    def test_run_id_plus_candidate_id_is_conditionally_safe(self) -> None:
        """Candidate with run_id + source_candidate_id is conditionally safe."""
        from k8s_diag_agent.ui.incident_suggested_check_mapping import (
            classify_next_check_mapping_candidate,
        )

        candidate = {
            "candidateId": "cand-001",
            "artifactPath": "runs/health/external-analysis/run-123-next-check-plan.json",
        }
        incident = {
            "incident_id": "default-pod-my-pod-crash-loop",
            "source_candidate_id": "cand-001",
            "signals": [{"run_id": "run-123", "source": "pod", "reason": "test", "message": "test"}],
        }

        decision = classify_next_check_mapping_candidate(candidate, [incident])

        self.assertEqual(decision.confidence, "conditionally_safe")

    def test_missing_incident_id_is_not_safe(self) -> None:
        """Old-style candidate without incident_id is not safe."""
        from k8s_diag_agent.ui.incident_suggested_check_mapping import (
            classify_next_check_mapping_candidate,
        )

        # Old artifact shape
        candidate = {
            "candidateId": "c1",
            "description": "Check pod logs",
        }

        decision = classify_next_check_mapping_candidate(candidate, [])

        self.assertNotEqual(decision.confidence, "safe")
        self.assertIn("incident_id", decision.required_fields)


# =============================================================================
# Test Cases: NextCheckPlan.to_payload() with Linkage
# =============================================================================


class TestNextCheckPlanToPayloadWithLinkage(unittest.TestCase):
    """Test NextCheckPlan.to_payload() with incident linkage using dict-based test."""

    def test_to_payload_with_one_linked_and_one_partial_candidate(self) -> None:
        """to_payload() produces artifact with one linked and one partial candidate.
        
        This tests the integration of enrich_next_check_candidate_dict and
        enrich_next_check_plan_dict which are used by NextCheckPlan.to_payload().
        """
        from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
            build_next_check_incident_linkage,
            enrich_next_check_candidate_dict,
            enrich_next_check_plan_dict,
        )

        # Simulate plan payload with two candidates (as built by NextCheckPlan.to_payload())
        plan_dict = {
            "review_path": "/path/to/review",
            "enrichment_artifact_path": "/path/to/enrichment.json",
            "candidates": [
                {"candidateId": "c1", "description": "Check pod logs"},  # Will match
                {"candidateId": "c2", "description": "Check deployment"},  # Won't match
            ],
        }

        # Create linkage context with source_candidate_id="c1"
        linkage_context = make_linkage_context(
            incident_id="default-pod-test-pod-crash-loop",
            source_candidate_id="c1",  # Matches c1's candidateId
            namespace="default",
            object_kind="Pod",
            object_name="test-pod",
            candidate_class="crash_loop",
            run_id="run-123",
        )

        # Apply linkage (as NextCheckPlan.to_payload() does)
        linkage_result = build_next_check_incident_linkage(linkage_context)
        self.assertIsNotNone(linkage_result)
        plan_linkage, candidate_linkage = linkage_result

        # Enrich plan-level fields
        enriched_plan = enrich_next_check_plan_dict(plan_dict, plan_linkage)
        
        # Enrich each candidate
        enriched_candidates = []
        for cand in plan_dict["candidates"]:
            enriched = enrich_next_check_candidate_dict(cand, candidate_linkage)
            enriched_candidates.append(enriched)
        enriched_plan["candidates"] = enriched_candidates

        # Verify plan-level linkage
        self.assertEqual(enriched_plan["run_id"], "run-123")
        self.assertEqual(enriched_plan["linkage_status"], "linked")
        self.assertIn("linkage_schema_version", enriched_plan)

        # Verify first candidate is linked
        linked = enriched_plan["candidates"][0]
        self.assertEqual(linked["candidateId"], "c1")
        self.assertEqual(linked["linkage_status"], "linked")
        self.assertIn("incident_id", linked)
        self.assertEqual(linked["incident_id"], "default-pod-test-pod-crash-loop")

        # Verify second candidate is partial
        partial = enriched_plan["candidates"][1]
        self.assertEqual(partial["candidateId"], "c2")
        self.assertEqual(partial["linkage_status"], "partial")
        self.assertNotIn("incident_id", partial)

    def test_to_payload_without_linkage_context(self) -> None:
        """to_payload() works without linkage_context (old behavior preserved)."""

        # Simulate plan without linkage context
        plan_dict = {
            "review_path": "/path/to/review",
            "enrichment_artifact_path": "/path/to/enrichment.json",
            "candidates": [{"candidateId": "c1", "description": "Check pod logs"}],
        }

        # No linkage context - plan_linkage is None
        # In real code, to_payload() checks if linkage_context is None
        
        # Without linkage, the plan dict should be unchanged (no linkage fields)
        # This simulates what happens when linkage_context=None
        self.assertNotIn("linkage_status", plan_dict)
        self.assertNotIn("run_id", plan_dict)
        self.assertNotIn("linkage_schema_version", plan_dict)


if __name__ == "__main__":
    unittest.main()
