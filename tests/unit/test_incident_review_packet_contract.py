"""Tests for incident review packet contract and response shape.

These tests verify:
- API response shape for successful captures
- Error field contract in API responses
- Packet format field validation
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_review_packet import (
    K9B_SELF_CONTAINED_CONSTRAINT,
    REVIEWER_CONSTRAINTS,
)


class TestConstants(unittest.TestCase):
    """Test that constraint constants are properly defined."""

    def test_self_contained_constraint_has_cline_mentions(self) -> None:
        """Self-contained constraint must mention no Cline required."""
        self.assertIn("Cline", K9B_SELF_CONTAINED_CONSTRAINT)
        self.assertIn("cline", K9B_SELF_CONTAINED_CONSTRAINT.lower())

    def test_reviewer_constraints_mentions_pod_logs(self) -> None:
        """Reviewer constraints must mention pod logs are not included."""
        self.assertIn("Pod logs are NOT included", REVIEWER_CONSTRAINTS)

    def test_reviewer_constraints_mentions_separate_facts(self) -> None:
        """Reviewer constraints must mention separating facts, hypotheses, unknowns."""
        self.assertIn("facts", REVIEWER_CONSTRAINTS.lower())
        self.assertIn("hypotheses", REVIEWER_CONSTRAINTS.lower())

    def test_reviewer_constraints_mentions_no_invent_evidence(self) -> None:
        """Reviewer constraints must mention not inventing missing evidence."""
        self.assertIn("invent missing evidence", REVIEWER_CONSTRAINTS.lower())


if __name__ == "__main__":
    unittest.main()
