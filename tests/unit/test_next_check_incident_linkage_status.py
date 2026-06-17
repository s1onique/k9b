"""Tests for next_check_incident_linkage status/invariant behavior.

These tests verify the linkage_status semantics and the invariant that
linkage_status == "linked" iff incident_id is present.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
    IncidentLinkageContext,
    build_next_check_incident_linkage,
    enrich_next_check_candidate_dict,
)

from .next_check_incident_linkage_fixtures import make_linkage_context

# =============================================================================
# Test Cases: Linkage Status Determination
# =============================================================================


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
            object_name=None,
            candidate_class=None,
        )

        status = context.determine_linkage_status()

        self.assertEqual(status, "unlinked")


# =============================================================================
# Test Cases: Linkage Reason
# =============================================================================


class TestIncidentLinkageContextReason(unittest.TestCase):
    """Test linkage reason generation."""

    def test_linked_reason_includes_incident_id(self) -> None:
        """Linked reason includes the incident_id."""
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
# Test Cases: INVARIANT - incident_id only with linked
# =============================================================================


class TestInvariantIncidentIdOnlyWithLinked(unittest.TestCase):
    """INVARIANT: candidate.linkage_status == 'linked' iff candidate.incident_id is present."""

    def test_invariant_incident_id_only_with_linked(self) -> None:
        """INVARIANT: candidate.linkage_status == 'linked' iff candidate.incident_id is present."""
        test_cases = [
            # (candidate, incident_id_in_context, source_candidate_id, entity_fields_present, should_have_incident_id, expected_status)
            # Explicit match with incident_id -> linked
            ({"candidateId": "c1"}, True, "c1", True, True, "linked"),
            # Explicit match without incident_id -> partial (not linked!)
            ({"candidateId": "c1"}, False, "c1", True, False, "partial"),
            # No match, linked context -> partial
            ({"candidateId": "c2"}, True, "c1", True, False, "partial"),
            # No match, partial context (no entity) -> partial
            ({"candidateId": "c2"}, False, "c1", False, False, "partial"),
            # No match, unlinked context (no entity) -> unlinked
            ({"candidateId": "c1"}, False, None, False, False, "unlinked"),
        ]

        for candidate, has_incident_id, src_cand_id, has_entity, should_have, expected_status in test_cases:
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
                    namespace=None,
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

        self.assertIn("candidateId", old_candidate)
        self.assertIn("description", old_candidate)
        self.assertNotIn("incident_id", old_candidate)

    def test_linkage_status_unlinked_for_old_context(self) -> None:
        """Old context (no incident context) produces unlinked status."""
        context = IncidentLinkageContext(
            incident_id=None,
            source_candidate_id=None,
            namespace=None,
            object_kind=None,
            object_name=None,
            candidate_class=None,
            run_id="run-123",
        )

        self.assertEqual(context.determine_linkage_status(), "unlinked")

    def test_enrich_function_works_with_partial_context(self) -> None:
        """Enrich function handles partial context gracefully."""
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
        self.assertEqual(plan_linkage.linkage_status, "unlinked")
        self.assertEqual(candidate_linkage.linkage_status, "unlinked")
        self.assertEqual(candidate_linkage.namespace, "default")
        self.assertEqual(plan_linkage.run_id, "run-123")


# =============================================================================
# Test Cases: Integration with Classifier
# =============================================================================


class TestClassifierCompatibility(unittest.TestCase):
    """Test that new linkage fields work with existing classifier."""

    def test_direct_incident_id_with_linkage_is_safe(self) -> None:
        """Candidate with incident_id from linkage is classified as safe."""
        from k8s_diag_agent.ui.incident_suggested_check_mapping import (
            classify_next_check_mapping_candidate,
        )

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

        candidate = {
            "candidateId": "c1",
            "description": "Check pod logs",
        }

        decision = classify_next_check_mapping_candidate(candidate, [])

        self.assertNotEqual(decision.confidence, "safe")
        self.assertIn("incident_id", decision.required_fields)


if __name__ == "__main__":
    unittest.main()
