"""Bounds tests for incident read-only check runner.

Tests:
1. max_checks is enforced
2. Excess checks are skipped with reason
3. Long fake handler summary is truncated
4. Long fake evidence string is truncated or omitted
5. Result stays JSON-serializable after truncation
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_read_only_check_runner import (
    DEFAULT_MAX_CHECKS_TO_RUN,
    DEFAULT_MAX_RESULT_CHARS,
    DEFAULT_MAX_SUMMARY_CHARS,
    run_read_only_checks,
)


class TestRunnerBounds(unittest.TestCase):
    """Bounds enforcement tests."""

    def test_max_checks_is_enforced(self) -> None:
        """max_checks parameter is enforced."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {"check_id": "pod_logs", "title": f"Check {i}", "read_only": True, "source": "test"}
            for i in range(10)
        ]

        # Use max_checks=3
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            max_checks=3,
        )

        # Only 3 checks should run
        self.assertEqual(result["checks_run"], 3)
        # Rest should be skipped
        self.assertEqual(result["checks_skipped"], 7)

    def test_excess_checks_are_skipped_with_reason(self) -> None:
        """Excess checks are skipped with reason."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {"check_id": "pod_logs", "title": f"Check {i}", "read_only": True, "source": "test"}
            for i in range(5)
        ]

        # Use max_checks=2
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            max_checks=2,
        )

        # Check skipped checks have reasons
        skipped = result["skipped_checks"]
        self.assertEqual(len(skipped), 3)
        for s in skipped:
            self.assertIn("reason", s)
            self.assertIn("max_checks", s["reason"])

    def test_default_max_checks_is_enforced(self) -> None:
        """Default max_checks is enforced."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {"check_id": "pod_logs", "title": f"Check {i}", "read_only": True, "source": "test"}
            for i in range(DEFAULT_MAX_CHECKS_TO_RUN + 5)
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Default max should be enforced
        self.assertEqual(result["checks_run"], DEFAULT_MAX_CHECKS_TO_RUN)

    def test_long_fake_handler_summary_is_truncated(self) -> None:
        """Long fake handler summary is truncated."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        def long_summary_handler(check, *, now):
            return {
                "summary": "x" * 1000,  # Way over limit
                "observations": ["test"],
            }

        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check",
                "read_only": True,
                "source": "test",
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": long_summary_handler},
        )

        check_result = result["results"][0]
        evidence = check_result.get("evidence", {})

        # Summary should be truncated
        summary = evidence.get("summary", "")
        self.assertLessEqual(len(summary), DEFAULT_MAX_SUMMARY_CHARS)

    def test_long_evidence_string_is_truncated(self) -> None:
        """Long evidence strings are truncated."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        def long_evidence_handler(check, *, now):
            return {
                "summary": "test summary",
                "observations": [
                    "short",
                    "x" * 5000,  # Way over limit
                    "another short",
                ],
            }

        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check",
                "read_only": True,
                "source": "test",
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": long_evidence_handler},
        )

        check_result = result["results"][0]
        evidence = check_result.get("evidence", {})
        observations = evidence.get("observations", [])

        # All observations should be truncated
        for obs in observations:
            self.assertLessEqual(len(obs), DEFAULT_MAX_RESULT_CHARS)

    def test_result_stays_json_serializable_after_truncation(self) -> None:
        """Result stays JSON-serializable after truncation."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        def pathological_handler(check, *, now):
            return {
                "summary": "x" * 10000,
                "observations": ["y" * 10000 for _ in range(100)],
            }

        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check",
                "read_only": True,
                "source": "test",
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": pathological_handler},
        )

        # Should still be JSON-serializable
        json_str = json.dumps(result)
        self.assertIsInstance(json_str, str)

        # Should round-trip
        parsed = json.loads(json_str)
        self.assertEqual(parsed["checks_run"], 1)


class TestRunnerBoundsConstants(unittest.TestCase):
    """Bounds constants tests."""

    def test_default_max_checks_is_positive(self) -> None:
        """DEFAULT_MAX_CHECKS_TO_RUN is a positive integer."""
        self.assertIsInstance(DEFAULT_MAX_CHECKS_TO_RUN, int)
        self.assertGreater(DEFAULT_MAX_CHECKS_TO_RUN, 0)

    def test_default_max_result_chars_is_positive(self) -> None:
        """DEFAULT_MAX_RESULT_CHARS is a positive integer."""
        self.assertIsInstance(DEFAULT_MAX_RESULT_CHARS, int)
        self.assertGreater(DEFAULT_MAX_RESULT_CHARS, 0)

    def test_default_max_summary_chars_is_positive(self) -> None:
        """DEFAULT_MAX_SUMMARY_CHARS is a positive integer."""
        self.assertIsInstance(DEFAULT_MAX_SUMMARY_CHARS, int)
        self.assertGreater(DEFAULT_MAX_SUMMARY_CHARS, 0)

    def test_summary_chars_less_than_result_chars(self) -> None:
        """DEFAULT_MAX_SUMMARY_CHARS <= DEFAULT_MAX_RESULT_CHARS."""
        self.assertLessEqual(DEFAULT_MAX_SUMMARY_CHARS, DEFAULT_MAX_RESULT_CHARS)


if __name__ == "__main__":
    unittest.main()
