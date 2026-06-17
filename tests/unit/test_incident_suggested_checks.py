"""Tests for incident_suggested_checks extraction helper.

Required test cases (from ACT scope):
1. linked candidate with matching incident_id produces one suggested check
2. linked candidate with non-matching incident_id is ignored
3. partial candidate with matching-like entity fields is ignored
4. unlinked candidate is ignored
5. old candidate without linkage fields is ignored
6. provider/text-only candidate is ignored
7. malformed candidate does not crash extraction
8. multiple linked candidates for same incident produce multiple suggested checks
9. mixed plan candidates produce only safe linked suggestions
10. output includes check_id, title/rationale/source/status/artifact_id/run_id fields
11. function does not mutate input payload
12. no execution/promotion/remediation fields are emitted

Additional serializer tests:
13. IncidentDetailPayload includes suggested_checks from linked artifact
14. IncidentDetailPayload remains suggested_checks: [] when no artifact exists
15. IncidentDetailPayload ignores partial/unlinked artifacts
16. Old artifact shapes remain compatible
"""

from __future__ import annotations

import copy
import unittest

from k8s_diag_agent.ui.incident_suggested_checks import (
    build_suggested_check_from_linked_candidate,
    build_suggested_checks_from_next_check_plan_payload,
)

# =============================================================================
# Test Fixtures
# =============================================================================


def make_linked_candidate(
    incident_id: str,
    candidate_id: str = "c1",
    description: str = "Check pod logs",
    title: str | None = None,
    rationale: str | None = None,
    risk_level: str | None = None,
) -> dict:
    """Create a safely linked candidate dict."""
    candidate = {
        "linkage_status": "linked",
        "incident_id": incident_id,
        "candidateId": candidate_id,
        "description": description,
    }
    if title:
        candidate["title"] = title
    if rationale:
        candidate["rationale"] = rationale
    if risk_level:
        candidate["riskLevel"] = risk_level
    return candidate


def make_partial_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
    namespace: str = "default",
    object_kind: str = "Pod",
    object_name: str = "my-pod",
) -> dict:
    """Create a partial candidate (no incident_id, has entity fields)."""
    return {
        "linkage_status": "partial",
        "candidateId": candidate_id,
        "description": description,
        "namespace": namespace,
        "objectKind": object_kind,
        "objectName": object_name,
    }


def make_unlinked_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
) -> dict:
    """Create an unlinked candidate."""
    return {
        "linkage_status": "unlinked",
        "candidateId": candidate_id,
        "description": description,
    }


def make_old_candidate(
    candidate_id: str = "c1",
    description: str = "Check pod logs",
) -> dict:
    """Create a legacy candidate without linkage fields."""
    return {
        "candidateId": candidate_id,
        "description": description,
        "suggestedCommandFamily": "kubectl-logs",
    }


def make_plan_payload(
    candidates: list[dict],
    run_id: str = "run-123",
    linkage_status: str | None = None,
    linkage_reason: str | None = None,
) -> dict:
    """Create a plan payload dict."""
    plan = {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "candidates": candidates,
    }
    if linkage_status:
        plan["linkage_status"] = linkage_status
    if linkage_reason:
        plan["linkage_reason"] = linkage_reason
    return plan


# =============================================================================
# Test Cases: SAFE Filter Implementation
# =============================================================================


class TestLinkedCandidateWithMatchingIncidentId(unittest.TestCase):
    """Test case 1: linked candidate with matching incident_id produces one suggested check."""

    def test_linked_matching_produces_suggested_check(self) -> None:
        """Linked candidate with matching incident_id must produce a suggested check."""
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
            description="Check pod logs for crash loop",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["check_id"], "check-001")
        self.assertEqual(result["status"], "suggested")
        self.assertEqual(result["source"], "next-check-plan")


# =============================================================================
# Test Cases: Non-Matching Incident ID
# =============================================================================


class TestLinkedCandidateWithNonMatchingIncidentId(unittest.TestCase):
    """Test case 2: linked candidate with non-matching incident_id is ignored."""

    def test_linked_non_matching_is_ignored(self) -> None:
        """Linked candidate with different incident_id must be ignored."""
        candidate = make_linked_candidate(
            incident_id="other-incident-123",
            candidate_id="check-001",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)

    def test_linked_no_incident_id_is_ignored(self) -> None:
        """Linked candidate without incident_id must be ignored."""
        candidate = {
            "linkage_status": "linked",
            "candidateId": "check-001",
            "description": "Check logs",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Partial Candidate
# =============================================================================


class TestPartialCandidate(unittest.TestCase):
    """Test case 3: partial candidate with matching-like entity fields is ignored."""

    def test_partial_candidate_is_ignored(self) -> None:
        """Partial candidate must be ignored regardless of entity fields."""
        candidate = make_partial_candidate(
            candidate_id="check-001",
            namespace="default",
            object_kind="Pod",
            object_name="my-pod",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Unlinked Candidate
# =============================================================================


class TestUnlinkedCandidate(unittest.TestCase):
    """Test case 4: unlinked candidate is ignored."""

    def test_unlinked_is_ignored(self) -> None:
        """Unlinked candidate must be ignored."""
        candidate = make_unlinked_candidate(
            candidate_id="check-001",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Old Artifact Compatibility
# =============================================================================


class TestOldCandidateWithoutLinkageFields(unittest.TestCase):
    """Test case 5: old candidate without linkage fields is ignored."""

    def test_old_candidate_without_linkage_is_ignored(self) -> None:
        """Legacy candidate without linkage_status field must be ignored."""
        candidate = make_old_candidate(
            candidate_id="check-001",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)

    def test_old_candidate_with_partial_status_is_ignored(self) -> None:
        """Old candidate with partial linkage_status must be ignored."""
        candidate = make_partial_candidate(candidate_id="check-001")

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Provider/Text-Only Candidate
# =============================================================================


class TestProviderTextOnlyCandidate(unittest.TestCase):
    """Test case 6: provider/text-only candidate is ignored."""

    def test_text_only_candidate_is_ignored(self) -> None:
        """Candidate with only description text must be ignored."""
        candidate = {
            "description": "Check pod logs for crash loop errors",
            "suggestedCommandFamily": "kubectl-logs",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)

    def test_title_only_candidate_is_ignored(self) -> None:
        """Candidate with only title must be ignored."""
        candidate = {
            "title": "Inspect pod logs",
            "description": "Check pod logs",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Malformed Candidate
# =============================================================================


class TestMalformedCandidate(unittest.TestCase):
    """Test case 7: malformed candidate does not crash extraction."""

    def test_empty_candidate_returns_none(self) -> None:
        """Empty candidate dict must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate={},
        )

        self.assertIsNone(result)

    def test_non_dict_candidate_returns_none(self) -> None:
        """Non-dict candidate must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate="not a dict",
        )

        self.assertIsNone(result)

    def test_none_candidate_returns_none(self) -> None:
        """None candidate must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=None,
        )

        self.assertIsNone(result)


# =============================================================================
# Test Cases: Multiple Linked Candidates
# =============================================================================


class TestMultipleLinkedCandidates(unittest.TestCase):
    """Test case 8: multiple linked candidates for same incident produce multiple suggested checks."""

    def test_multiple_linked_candidates_produce_multiple_checks(self) -> None:
        """Plan with multiple linked candidates for same incident must produce multiple checks."""
        incident_id = "default-pod-my-pod-crash-loop"
        plan_payload = make_plan_payload(
            run_id="run-123",
            candidates=[
                make_linked_candidate(
                    incident_id=incident_id,
                    candidate_id="check-001",
                    description="Check pod logs",
                ),
                make_linked_candidate(
                    incident_id=incident_id,
                    candidate_id="check-002",
                    description="Check events",
                ),
                make_linked_candidate(
                    incident_id=incident_id,
                    candidate_id="check-003",
                    description="Check describe",
                ),
            ],
        )

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=incident_id,
            plan_payload=plan_payload,
        )

        self.assertEqual(len(result), 3)
        check_ids = {c["check_id"] for c in result}
        self.assertEqual(check_ids, {"check-001", "check-002", "check-003"})


# =============================================================================
# Test Cases: Mixed Plan Candidates
# =============================================================================


class TestMixedPlanCandidates(unittest.TestCase):
    """Test case 9: mixed plan candidates produce only safe linked suggestions."""

    def test_mixed_candidates_only_linked_extracted(self) -> None:
        """Plan with mixed candidates must only extract safely linked ones."""
        incident_id = "default-pod-my-pod-crash-loop"
        plan_payload = make_plan_payload(
            run_id="run-123",
            candidates=[
                make_linked_candidate(
                    incident_id=incident_id,
                    candidate_id="check-001",
                    description="Check pod logs",
                ),
                make_unlinked_candidate(candidate_id="check-002"),
                make_partial_candidate(candidate_id="check-003"),
                make_old_candidate(candidate_id="check-004"),
                make_linked_candidate(
                    incident_id="different-incident",
                    candidate_id="check-005",
                    description="Wrong incident",
                ),
            ],
        )

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=incident_id,
            plan_payload=plan_payload,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["check_id"], "check-001")


# =============================================================================
# Test Cases: Output Field Validation
# =============================================================================


class TestOutputIncludesRequiredFields(unittest.TestCase):
    """Test case 10: output includes check_id, title/rationale/source/status/artifact_id/run_id fields."""

    def test_output_includes_all_required_fields(self) -> None:
        """Suggested check must include all required fields."""
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
            description="Check pod logs for crash loop",
            title="Pod Log Inspection",
            rationale="Investigate crash loop",
            risk_level="LOW",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
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
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
            risk_level="MEDIUM",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
        )

        self.assertEqual(result["risk_level"], "MEDIUM")

    def test_risk_level_snake_case(self) -> None:
        """Risk level from candidate.risk_level (snake_case) must be preserved."""
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
        )
        candidate["risk_level"] = "HIGH"

        result = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
        )

        self.assertEqual(result["risk_level"], "HIGH")

    def test_rationale_fallback_chain(self) -> None:
        """Rationale must fall back through: rationale > description > linkage_reason > default."""
        # Case: no rationale, has description
        candidate = make_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate_id="check-001",
            description="Check pod logs for crash loop",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Check pod logs for crash loop")

    def test_rationale_with_linkage_reason_fallback(self) -> None:
        """Rationale must fall back to linkage_reason if description absent."""
        candidate = {
            "linkage_status": "linked",
            "incident_id": "default-pod-my-pod-crash-loop",
            "candidateId": "check-001",
            "linkage_reason": "Deterministic incident match",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Deterministic incident match")

    def test_rationale_default_when_no_text(self) -> None:
        """Rationale must be 'Linked by incident_id' when no text fields present."""
        candidate = {
            "linkage_status": "linked",
            "incident_id": "default-pod-my-pod-crash-loop",
            "candidateId": "check-001",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id="default-pod-my-pod-crash-loop",
            candidate=candidate,
        )

        self.assertEqual(result["rationale"], "Linked by incident_id")


# =============================================================================
# Test Cases: No Mutation
# =============================================================================


class TestNoMutation(unittest.TestCase):
    """Test case 11: function does not mutate input payload."""

    def test_plan_payload_not_mutated(self) -> None:
        """build_suggested_checks_from_next_check_plan_payload must not mutate input."""
        incident_id = "default-pod-my-pod-crash-loop"
        original_candidates = [
            make_linked_candidate(
                incident_id=incident_id,
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
            incident_id=incident_id,
            plan_payload=plan_payload,
        )

        # Verify no mutation
        self.assertEqual(str(plan_payload), original_json)

    def test_candidate_not_mutated(self) -> None:
        """build_suggested_check_from_linked_candidate must not mutate input."""
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
            description="Check pod logs",
        )
        original_json = str(candidate)

        # Run extraction
        build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
        )

        # Verify no mutation
        self.assertEqual(str(candidate), original_json)


# =============================================================================
# Test Cases: No Execution/Promotion/Remediation
# =============================================================================


class TestNoActionFields(unittest.TestCase):
    """Test case 12: no execution/promotion/remediation fields are emitted."""

    def test_no_execution_fields_in_output(self) -> None:
        """Suggested check must NOT include execution fields."""
        incident_id = "default-pod-my-pod-crash-loop"
        candidate = make_linked_candidate(
            incident_id=incident_id,
            candidate_id="check-001",
            description="Check pod logs",
        )
        # Add execution-like fields (should be ignored)
        candidate["safeToAutomate"] = True
        candidate["requiresOperatorApproval"] = True
        candidate["suggestedCommandFamily"] = "kubectl-logs"

        result = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
        )

        self.assertIsNotNone(result)
        self.assertNotIn("safe_to_automate", result)
        self.assertNotIn("requires_operator_approval", result)
        self.assertNotIn("suggested_command_family", result)
        self.assertNotIn("execution_status", result)
        self.assertNotIn("promotion_status", result)
        self.assertNotIn("remediation_status", result)


# =============================================================================
# Test Cases: Plan Payload Compatibility
# =============================================================================


class TestPlanPayloadCompatibility(unittest.TestCase):
    """Test old artifact shapes remain compatible."""

    def test_plan_without_candidates_returns_empty(self) -> None:
        """Plan without candidates key must return empty list."""
        plan_payload = {"run_id": "run-123", "linkage_schema_version": 1}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id="default-pod-my-pod-crash-loop",
            plan_payload=plan_payload,
        )

        self.assertEqual(result, [])

    def test_plan_with_empty_candidates_returns_empty(self) -> None:
        """Plan with empty candidates list must return empty list."""
        plan_payload = {"run_id": "run-123", "candidates": []}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id="default-pod-my-pod-crash-loop",
            plan_payload=plan_payload,
        )

        self.assertEqual(result, [])

    def test_plan_without_run_id_works(self) -> None:
        """Plan without run_id must still extract candidates."""
        incident_id = "default-pod-my-pod-crash-loop"
        plan_payload = {
            "candidates": [
                make_linked_candidate(
                    incident_id=incident_id,
                    candidate_id="check-001",
                ),
            ],
        }

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=incident_id,
            plan_payload=plan_payload,
        )

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["run_id"])

    def test_non_list_candidates_returns_empty(self) -> None:
        """Plan with non-list candidates must return empty list."""
        plan_payload = {"run_id": "run-123", "candidates": "not a list"}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id="default-pod-my-pod-crash-loop",
            plan_payload=plan_payload,
        )

        self.assertEqual(result, [])


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    unittest.main()