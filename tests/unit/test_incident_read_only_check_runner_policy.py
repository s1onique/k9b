"""Policy tests for incident read-only check runner.

Tests:
1. Runner revalidates accepted checks
2. Unknown check ID is skipped/rejected
3. Mutation-like check ID is skipped/rejected
4. Proposal with command field is skipped/rejected
5. Proposal with kubectl field is skipped/rejected
6. Unsafe parameters are stripped or rejected consistently
7. Handler receives sanitized parameters only
8. Rejected checks include bounded rejection reasons
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_read_only_check_runner import (
    run_read_only_checks,
)


class TestRunnerPolicyRevalidation(unittest.TestCase):
    """Policy revalidation tests."""

    def test_runner_revalidates_accepted_checks(self) -> None:
        """Runner revalidates each check against policy."""
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

        # Check ran successfully
        self.assertEqual(result["checks_run"], 1)
        self.assertEqual(result["checks_rejected"], 0)

    def test_unknown_check_id_is_rejected(self) -> None:
        """Unknown check ID is rejected by policy revalidation."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "unknown_check",
                "title": "Unknown check",
                "read_only": True,
                "source": "test",
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Check was rejected
        self.assertEqual(result["checks_run"], 0)
        self.assertEqual(result["checks_rejected"], 1)
        self.assertEqual(len(result["rejected_checks"]), 1)

        rejected = result["rejected_checks"][0]
        self.assertEqual(rejected["check_id"], "unknown_check")
        self.assertIn("reason", rejected)
        self.assertTrue(rejected["safety_blocked"])

    def test_mutation_like_check_id_is_rejected(self) -> None:
        """Mutation-like check IDs are rejected."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        mutation_check_ids = [
            "kubectl_exec",
            "kubectl_apply",
            "kubectl_delete",
            "restart_pod",
            "scale_deployment",
            "apply_manifest",
        ]

        for check_id in mutation_check_ids:
            with self.subTest(check_id=check_id):
                accepted_checks = [
                    {
                        "check_id": check_id,
                        "title": f"{check_id} check",
                        "read_only": True,
                        "source": "test",
                    }
                ]

                result = run_read_only_checks(
                    incident_id="test-incident",
                    run_id="run-001",
                    accepted_checks=accepted_checks,
                    now=now,
                )

                # Check was rejected
                self.assertEqual(result["checks_run"], 0)
                self.assertEqual(result["checks_rejected"], 1)
                self.assertTrue(result["rejected_checks"][0]["safety_blocked"])

    def test_proposal_with_command_field_is_rejected(self) -> None:
        """Proposal with command field is rejected."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "command": "kubectl get pods",  # Forbidden field
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Check was rejected due to forbidden field
        self.assertEqual(result["checks_run"], 0)
        self.assertEqual(result["checks_rejected"], 1)

        rejected = result["rejected_checks"][0]
        self.assertIn("command", rejected["reason"].lower())

    def test_proposal_with_kubectl_field_is_rejected(self) -> None:
        """Proposal with kubectl field is rejected."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "kubectl": "get pods",  # Forbidden field
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Check was rejected due to forbidden field
        self.assertEqual(result["checks_run"], 0)
        self.assertEqual(result["checks_rejected"], 1)

        rejected = result["rejected_checks"][0]
        self.assertIn("kubectl", rejected["reason"].lower())

    def test_unsafe_parameters_are_stripped(self) -> None:
        """Unsafe parameters are stripped or rejected."""
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
                    "unknown_param": "should_be_stripped",  # Not in allowed list
                },
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        # Check ran successfully (unknown param was stripped)
        self.assertEqual(result["checks_run"], 1)

        check_result = result["results"][0]
        params = check_result.get("parameters", {})
        self.assertNotIn("unknown_param", params)
        self.assertEqual(params.get("namespace"), "default")
        self.assertEqual(params.get("object_name"), "test-pod")

    def test_handler_receives_sanitized_parameters(self) -> None:
        """Handler receives only sanitized parameters."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        received_params: dict = {}

        def capturing_handler(check, *, now):
            nonlocal received_params
            received_params = dict(check.get("parameters", {}))
            return {
                "summary": "test",
                "observations": ["test"],
            }

        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {
                    "namespace": "default",
                    "object_name": "test-pod",
                    "unknown_param": "should_be_stripped",
                },
            }
        ]

        run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": capturing_handler},
        )

        # Handler received only known parameters
        self.assertIn("namespace", received_params)
        self.assertIn("object_name", received_params)
        self.assertNotIn("unknown_param", received_params)

    def test_rejected_checks_include_bounded_rejection_reasons(self) -> None:
        """Rejected checks include bounded rejection reasons."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        accepted_checks = [
            {
                "check_id": "unknown_check",
                "title": "Unknown",
                "read_only": True,
                "source": "test",
            }
        ]

        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
        )

        rejected = result["rejected_checks"][0]
        self.assertIn("reason", rejected)
        # Reason should be a string, not overly long
        self.assertIsInstance(rejected["reason"], str)
        self.assertLess(len(rejected["reason"]), 500)


if __name__ == "__main__":
    unittest.main()
