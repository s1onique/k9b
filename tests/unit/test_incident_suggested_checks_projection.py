"""Tests for field projection/mapping in suggested check extraction.

These tests verify:
1. Output includes check_id, title/rationale/source/status/artifact_id/run_id fields
2. Function does not mutate input payload
3. No execution/promotion/remediation fields are emitted
"""

from __future__ import annotations

import copy
import unittest

from k8s_diag_agent.ui.incident_suggested_checks import (
    build_suggested_check_from_linked_candidate,
    build_suggested_checks_from_next_check_plan_payload,
)

from .incident_suggested_checks_fixtures import (
    DEFAULT_INCIDENT_ID,
    make_linked_candidate,
    make_plan_payload,
)


class TestOutputIncludesRequiredFields(unittest.TestCase):
    """Test case 10: output includes check_id, title/rationale/source/status/artifact_id/run_id fields."""

    def test_output_includes_all_required_fields(self) -> None:
        """Suggested check must include all required fields."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            description="Check pod logs for crash loop",
            title="Pod Log Inspection",
            rationale="Investigate crash loop",
            risk_level="LOW",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
            artifact_id="artifact-123",
            run_id="run-456",
        )

        self.assertIsNotNone(result)
        self.assertIn("check_id", result)
        self.assertIn("title", result)
        self.assertIn("rationale", result)
        self.assertIn("source", result)
        self.assertIn("status", result)
        self.assertIn("artifact_id", result)
        self.assertIn("run_id", result)

        # Verify field values
        self.assertEqual(result["check_id"], "check-001")
        self.assertEqual(result["title"], "Pod Log Inspection")
        self.assertEqual(result["rationale"], "Investigate crash loop")
        self.assertEqual(result["source"], "next-check-plan")
        self.assertEqual(result["status"], "suggested")
        self.assertEqual(result["artifact_id"], "artifact-123")
        self.assertEqual(result["run_id"], "run-456")

    def test_risk_level_normalized(self) -> None:
        """Risk level from candidate.riskLevel must be preserved."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            risk_level="MEDIUM",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertEqual(result["risk_level"], "MEDIUM")

    def test_risk_level_snake_case(self) -> None:
        """Risk level from candidate.risk_level (snake_case) must be preserved."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
        )
        candidate["risk_level"] = "HIGH"

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertEqual(result["risk_level"], "HIGH")

    def test_rationale_fallback_chain(self) -> None:
        """Rationale must fall back through: rationale > description > linkage_reason > default."""
        # Case: no rationale, has description
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            description="Check pod logs for crash loop",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Check pod logs for crash loop")

    def test_rationale_with_linkage_reason_fallback(self) -> None:
        """Rationale must fall back to linkage_reason if description absent."""
        candidate = {
            "linkage_status": "linked",
            "incident_id": DEFAULT_INCIDENT_ID,
            "candidateId": "check-001",
            "linkage_reason": "Deterministic incident match",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Deterministic incident match")

    def test_rationale_default_when_no_text(self) -> None:
        """Rationale must be 'Linked by incident_id' when no text fields present."""
        candidate = {
            "linkage_status": "linked",
            "incident_id": DEFAULT_INCIDENT_ID,
            "candidateId": "check-001",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Linked by incident_id")


class TestNoMutation(unittest.TestCase):
    """Test case 11: function does not mutate input payload."""

    def test_plan_payload_not_mutated(self) -> None:
        """build_suggested_checks_from_next_check_plan_payload must not mutate input."""
        original_candidates = [
            make_linked_candidate(
                incident_id=DEFAULT_INCIDENT_ID,
                candidate_id="check-001",
                description="Check pod logs",
            ),
        ]
        plan_payload = make_plan_payload(
            run_id="run-123",
            candidates=copy.deepcopy(original_candidates),
        )

        # Save original candidates
        original_json = str(plan_payload)

        # Run extraction
        build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )

        # Verify no mutation
        self.assertEqual(str(plan_payload), original_json)

    def test_candidate_not_mutated(self) -> None:
        """build_suggested_check_from_linked_candidate must not mutate input."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            description="Check pod logs",
        )
        original_json = str(candidate)

        # Run extraction
        build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        # Verify no mutation
        self.assertEqual(str(candidate), original_json)


class TestNoActionFields(unittest.TestCase):
    """Test case 12: no execution/promotion/remediation fields are emitted."""

    def test_no_execution_fields_in_output(self) -> None:
        """Suggested check must NOT include execution fields."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            description="Check pod logs",
        )
        # Add execution-like fields (should be ignored)
        candidate["safeToAutomate"] = True
        candidate["requiresOperatorApproval"] = True
        candidate["suggestedCommandFamily"] = "kubectl-logs"

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertIsNotNone(result)
        self.assertNotIn("safe_to_automate", result)
        self.assertNotIn("requires_operator_approval", result)
        self.assertNotIn("suggested_command_family", result)
        self.assertNotIn("execution_status", result)
        self.assertNotIn("promotion_status", result)
        self.assertNotIn("remediation_status", result)


if __name__ == "__main__":
    unittest.main()
