"""Tests for next_check_incident_linkage_builder module.

These tests verify the build_next_check_incident_linkage() function.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.external_analysis.next_check_incident_linkage import (
    NextCheckCandidateLinkage,
    NextCheckPlanLinkage,
    build_next_check_incident_linkage,
)

from .next_check_incident_linkage_fixtures import make_linkage_context

# =============================================================================
# Test Cases: Main Enrichment Function
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


if __name__ == "__main__":
    unittest.main()
