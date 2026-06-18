"""Basic tests for incident read-only check runner.

Tests:
1. Runner returns schema version
2. Runner includes incident_id and run_id
3. Runner result is JSON-serializable
4. Known fake check runs successfully
5. Multiple known fake checks run successfully
6. Result contains checks_requested, checks_run, checks_skipped
7. Result contains stable timestamps from injected now
8. Repeated call with same input and same now produces identical result
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_read_only_check_runner import (
    RUNNER_SCHEMA_VERSION,
    run_read_only_checks,
)


class TestRunnerBasic(unittest.TestCase):
    """Basic runner tests."""

    def test_schema_version_is_defined(self) -> None:
        """RUNNER_SCHEMA_VERSION is defined."""
        self.assertEqual(RUNNER_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(RUNNER_SCHEMA_VERSION, str)

    def test_runner_returns_schema_version(self) -> None:
        """Runner result includes schema_version."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertEqual(result["schema_version"], RUNNER_SCHEMA_VERSION)
        self.assertIsInstance(result["schema_version"], str)

    def test_runner_includes_incident_id(self) -> None:
        """Runner result includes incident_id."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident-001",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertEqual(result["incident_id"], "test-incident-001")

    def test_runner_includes_run_id(self) -> None:
        """Runner result includes run_id."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertEqual(result["run_id"], "run-001")

    def test_runner_result_is_json_serializable(self) -> None:
        """Runner result can be serialized to JSON."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        # Should not raise
        json_str = json.dumps(result)
        self.assertIsInstance(json_str, str)

        # Should round-trip
        parsed = json.loads(json_str)
        self.assertEqual(parsed["incident_id"], "test-incident")
        self.assertEqual(parsed["run_id"], "run-001")

    def test_known_fake_check_runs_successfully(self) -> None:
        """Known fake check (pod_logs) runs successfully."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {
                    "namespace": "default",
                    "object_name": "test-pod",
                },
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        self.assertEqual(result["checks_requested"], 1)
        self.assertEqual(result["checks_run"], 1)
        self.assertEqual(result["checks_skipped"], 0)
        self.assertEqual(result["checks_rejected"], 0)

        self.assertEqual(len(result["results"]), 1)
        check_result = result["results"][0]
        self.assertEqual(check_result["check_id"], "pod_logs")
        self.assertEqual(check_result["status"], "completed")
        self.assertTrue(check_result["read_only"])
        self.assertTrue(check_result["bounded"])

    def test_multiple_known_fake_checks_run_successfully(self) -> None:
        """Multiple known fake checks run successfully."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            },
            {
                "check_id": "pod_events",
                "title": "Check pod events",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            },
            {
                "check_id": "deployment_status",
                "title": "Check deployment",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-deployment"},
            },
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        self.assertEqual(result["checks_requested"], 3)
        self.assertEqual(result["checks_run"], 3)
        self.assertEqual(result["checks_skipped"], 0)

        check_ids = [r["check_id"] for r in result["results"]]
        self.assertIn("pod_logs", check_ids)
        self.assertIn("pod_events", check_ids)
        self.assertIn("deployment_status", check_ids)

    def test_result_contains_checks_requested(self) -> None:
        """Result contains checks_requested count."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("checks_requested", result)
        self.assertEqual(result["checks_requested"], 0)
        self.assertIsInstance(result["checks_requested"], int)

    def test_result_contains_checks_run(self) -> None:
        """Result contains checks_run count."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("checks_run", result)
        self.assertEqual(result["checks_run"], 0)
        self.assertIsInstance(result["checks_run"], int)

    def test_result_contains_checks_skipped(self) -> None:
        """Result contains checks_skipped count."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("checks_skipped", result)
        self.assertEqual(result["checks_skipped"], 0)
        self.assertIsInstance(result["checks_skipped"], int)

    def test_result_contains_stable_timestamps(self) -> None:
        """Result contains timestamps from injected now."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        check_result = result["results"][0]
        self.assertEqual(check_result["started_at"], "2024-06-01T12:00:00+00:00")
        self.assertEqual(check_result["finished_at"], "2024-06-01T12:00:00+00:00")

    def test_repeated_call_produces_identical_result(self) -> None:
        """Repeated call with same input produces identical result."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            }
        ]

        result1 = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        result2 = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Results should be identical
        self.assertEqual(result1, result2)

        # JSON serialization should also be identical
        json1 = json.dumps(result1, sort_keys=True)
        json2 = json.dumps(result2, sort_keys=True)
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
