"""Tests for SAFE filter enforcement in suggested check extraction.

These tests verify:
1. Only linkage_status == "linked" candidates are included
2. Only matching incident_id candidates are included
3. Missing incident_id is ignored
4. Mismatched incident_id is ignored
5. Unlinked/partial/old candidates are ignored
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.incident_suggested_checks import (
    build_suggested_check_from_linked_candidate,
    build_suggested_checks_from_next_check_plan_payload,
)

from .incident_suggested_checks_fixtures import (
    DEFAULT_INCIDENT_ID,
    make_linked_candidate,
    make_old_candidate,
    make_partial_candidate,
    make_plan_payload,
    make_unlinked_candidate,
)


class TestLinkedCandidateWithMatchingIncidentId(unittest.TestCase):
    """Test case 1: linked candidate with matching incident_id produces one suggested check."""

    def test_linked_matching_produces_suggested_check(self) -> None:
        """Linked candidate with matching incident_id must produce a suggested check."""
        candidate = make_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate_id="check-001",
            description="Check pod logs for crash loop",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["check_id"], "check-001")
        self.assertEqual(result["status"], "suggested")
        self.assertEqual(result["source"], "next-check-plan")


class TestLinkedCandidateWithNonMatchingIncidentId(unittest.TestCase):
    """Test case 2: linked candidate with non-matching incident_id is ignored."""

    def test_linked_non_matching_is_ignored(self) -> None:
        """Linked candidate with different incident_id must be ignored."""
        candidate = make_linked_candidate(
            incident_id="other-incident-123",
            candidate_id="check-001",
        )

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
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
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)


class TestPartialCandidateSafeFilter(unittest.TestCase):
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
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)


class TestUnlinkedCandidateSafeFilter(unittest.TestCase):
    """Test case 4: unlinked candidate is ignored."""

    def test_unlinked_is_ignored(self) -> None:
        """Unlinked candidate must be ignored."""
        candidate = make_unlinked_candidate(candidate_id="check-001")

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)


class TestOldCandidateWithoutLinkageFields(unittest.TestCase):
    """Test case 5: old candidate without linkage fields is ignored."""

    def test_old_candidate_without_linkage_is_ignored(self) -> None:
        """Legacy candidate without linkage_status field must be ignored."""
        candidate = make_old_candidate(candidate_id="check-001")

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)

    def test_old_candidate_with_partial_status_is_ignored(self) -> None:
        """Old candidate with partial linkage_status must be ignored."""
        candidate = make_partial_candidate(candidate_id="check-001")

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)


class TestProviderTextOnlyCandidateSafeFilter(unittest.TestCase):
    """Test case 6: provider/text-only candidate is ignored."""

    def test_text_only_candidate_is_ignored(self) -> None:
        """Candidate with only description text must be ignored."""
        candidate = {
            "description": "Check pod logs for crash loop errors",
            "suggestedCommandFamily": "kubectl-logs",
        }

        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
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
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=candidate,
        )
        self.assertIsNone(result)


class TestMixedPlanCandidatesSafeFilter(unittest.TestCase):
    """Test case 9: mixed plan candidates produce only safe linked suggestions."""

    def test_mixed_candidates_only_linked_extracted(self) -> None:
        """Plan with mixed candidates must only extract safely linked ones."""
        plan_payload = make_plan_payload(
            run_id="run-123",
            candidates=[
                make_linked_candidate(
                    incident_id=DEFAULT_INCIDENT_ID,
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
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["check_id"], "check-001")


class TestMultipleLinkedCandidatesSafeFilter(unittest.TestCase):
    """Test case 8: multiple linked candidates for same incident produce multiple suggested checks."""

    def test_multiple_linked_candidates_produce_multiple_checks(self) -> None:
        """Plan with multiple linked candidates for same incident must produce multiple checks."""
        plan_payload = make_plan_payload(
            run_id="run-123",
            candidates=[
                make_linked_candidate(
                    incident_id=DEFAULT_INCIDENT_ID,
                    candidate_id="check-001",
                    description="Check pod logs",
                ),
                make_linked_candidate(
                    incident_id=DEFAULT_INCIDENT_ID,
                    candidate_id="check-002",
                    description="Check events",
                ),
                make_linked_candidate(
                    incident_id=DEFAULT_INCIDENT_ID,
                    candidate_id="check-003",
                    description="Check describe",
                ),
            ],
        )

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(len(result), 3)
        check_ids = {c["check_id"] for c in result}
        self.assertEqual(check_ids, {"check-001", "check-002", "check-003"})


if __name__ == "__main__":
    unittest.main()
