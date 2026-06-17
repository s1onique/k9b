"""Tests for suggested check extraction contract (shape/schema).

These tests verify:
1. Empty/missing/malformed plan behavior
2. Public helper contract tests
3. Old artifact shapes remain compatible
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
)


class TestMalformedCandidateContract(unittest.TestCase):
    """Test case 7: malformed candidate does not crash extraction."""

    def test_empty_candidate_returns_none(self) -> None:
        """Empty candidate dict must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate={},
        )
        self.assertIsNone(result)

    def test_non_dict_candidate_returns_none(self) -> None:
        """Non-dict candidate must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate="not a dict",
        )
        self.assertIsNone(result)

    def test_none_candidate_returns_none(self) -> None:
        """None candidate must not crash."""
        result = build_suggested_check_from_linked_candidate(
            incident_id=DEFAULT_INCIDENT_ID,
            candidate=None,
        )
        self.assertIsNone(result)


class TestPlanPayloadCompatibility(unittest.TestCase):
    """Test old artifact shapes remain compatible."""

    def test_plan_without_candidates_returns_empty(self) -> None:
        """Plan without candidates key must return empty list."""
        plan_payload = {"run_id": "run-123", "linkage_schema_version": 1}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(result, [])

    def test_plan_with_empty_candidates_returns_empty(self) -> None:
        """Plan with empty candidates list must return empty list."""
        plan_payload = {"run_id": "run-123", "candidates": []}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(result, [])

    def test_plan_without_run_id_works(self) -> None:
        """Plan without run_id must still extract candidates."""
        plan_payload = {
            "candidates": [
                make_linked_candidate(
                    incident_id=DEFAULT_INCIDENT_ID,
                    candidate_id="check-001",
                ),
            ],
        }

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["run_id"])

    def test_non_list_candidates_returns_empty(self) -> None:
        """Plan with non-list candidates must return empty list."""
        plan_payload = {"run_id": "run-123", "candidates": "not a list"}

        result = build_suggested_checks_from_next_check_plan_payload(
            incident_id=DEFAULT_INCIDENT_ID,
            plan_payload=plan_payload,
        )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
