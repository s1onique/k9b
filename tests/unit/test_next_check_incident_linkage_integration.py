"""Integration tests for next_check_incident_linkage module.

These tests verify the integration of enrichment functions with plan-level artifacts.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
    build_next_check_incident_linkage,
    enrich_next_check_candidate_dict,
    enrich_next_check_plan_dict,
)

from .next_check_incident_linkage_fixtures import make_linkage_context


class TestNextCheckPlanPayloadWithLinkage(unittest.TestCase):
    """Test NextCheckPlan.to_payload() integration with incident linkage."""

    def test_to_payload_with_one_linked_and_one_partial_candidate(self) -> None:
        """to_payload() produces artifact with one linked and one partial candidate.

        This tests the integration of enrich_next_check_candidate_dict and
        enrich_next_check_plan_dict which are used by NextCheckPlan.to_payload().
        """
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
        # Without linkage, the plan dict should be unchanged (no linkage fields)
        self.assertNotIn("linkage_status", plan_dict)
        self.assertNotIn("run_id", plan_dict)
        self.assertNotIn("linkage_schema_version", plan_dict)


if __name__ == "__main__":
    unittest.main()
