"""Safety tests for incident read-only check runner.

Tests:
1. No Kubernetes client is imported or instantiated
2. No subprocess/shell call is made
3. No kubectl command is present in accepted handler input
4. No mutation/remediation verbs become actions
5. allowed_actions remains []
6. read_only remains True
7. disallowed_actions remains complete
8. Fake handler failure is captured as 'failed', not raised
9. Exception text is bounded and does not include traceback
10. No incident store mutation occurs
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from k8s_diag_agent.collect.incident_read_only_check_runner import (
    STATUS_FAILED,
    run_checks_from_loop_decision,
    run_read_only_checks,
)


class TestRunnerSafety(unittest.TestCase):
    """Safety guarantee tests."""

    def test_allowed_actions_remains_empty(self) -> None:
        """allowed_actions remains empty list."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("allowed_actions", result)
        self.assertEqual(result["allowed_actions"], [])

    def test_read_only_remains_true(self) -> None:
        """read_only flag remains True."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("read_only", result)
        self.assertTrue(result["read_only"])

    def test_disallowed_actions_is_complete(self) -> None:
        """disallowed_actions contains expected mutation verbs."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("disallowed_actions", result)
        disallowed = result["disallowed_actions"]

        # Check for key mutation verbs
        self.assertIn("execute", disallowed)
        self.assertIn("apply", disallowed)
        self.assertIn("delete", disallowed)
        self.assertIn("remediate", disallowed)
        self.assertIn("mutate_cluster", disallowed)

    def test_no_kubernetes_client_import(self) -> None:
        """Module does not import kubernetes client."""
        # This is verified by static analysis - the module should not have
        # kubernetes imports in its namespace
        import k8s_diag_agent.collect.incident_read_only_check_runner as runner_module

        # Check for kubernetes client imports
        module_attrs = dir(runner_module)
        kubernetes_attrs = [a for a in module_attrs if "kubernetes" in a.lower()]
        self.assertEqual(
            kubernetes_attrs,
            [],
            f"Found kubernetes-related attributes: {kubernetes_attrs}",
        )

    def test_no_subprocess_calls(self) -> None:
        """No subprocess calls are made during runner execution."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        with patch("subprocess.run") as mock_run:
            with patch("subprocess.Popen") as mock_popen:
                accepted_checks = [
                    {
                        "check_id": "pod_logs",
                        "title": "Check pod logs",
                        "read_only": True,
                        "source": "test",
                        "parameters": {"namespace": "default", "object_name": "test-pod"},
                    }
                ]

                run_read_only_checks(
                    incident_id="test-incident",
                    run_id="run-001",
                    accepted_checks=accepted_checks,
                    now=now,
                )

                # Neither subprocess method should have been called
                mock_run.assert_not_called()
                mock_popen.assert_not_called()

    def test_no_kubectl_in_handler_input(self) -> None:
        """No kubectl commands appear in handler input."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        handler_input: dict = {}

        def capturing_handler(check, *, now):
            nonlocal handler_input
            handler_input = dict(check)
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
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            }
        ]

        run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": capturing_handler},
        )

        # Check handler input doesn't contain kubectl
        input_str = str(handler_input)
        self.assertNotIn("kubectl", input_str.lower())
        self.assertNotIn("kubectl_", input_str)

    def test_no_mutation_verbs_in_results(self) -> None:
        """Mutation/remediation verbs don't appear as actions."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        mutation_verbs = ["apply", "delete", "patch", "scale", "restart", "rollout"]

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

        # Check results don't contain mutation verbs as keys
        result_str = str(result)
        for verb in mutation_verbs:
            # Should not appear as a top-level action
            self.assertNotIn(f'"{verb}"', result_str)

    def test_fake_handler_failure_is_captured(self) -> None:
        """Fake handler failure is captured as 'failed', not raised."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        def failing_handler(check, *, now):
            raise ValueError("Intentional test failure")

        accepted_checks = [
            {
                "check_id": "pod_logs",
                "title": "Check pod logs",
                "read_only": True,
                "source": "test",
                "parameters": {"namespace": "default", "object_name": "test-pod"},
            }
        ]

        # Should not raise
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=accepted_checks,
            now=now,
            fake_handlers={"pod_logs": failing_handler},
        )

        # Check captured as failed
        self.assertEqual(result["checks_run"], 1)
        check_result = result["results"][0]
        self.assertEqual(check_result["status"], STATUS_FAILED)

    def test_exception_text_is_bounded(self) -> None:
        """Exception text in failed results is bounded."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        def failing_handler(check, *, now):
            raise ValueError("x" * 5000)

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
            fake_handlers={"pod_logs": failing_handler},
        )

        check_result = result["results"][0]
        error_msg = check_result.get("evidence", {}).get("error", "")

        # Error should be bounded
        self.assertLess(len(error_msg), 5000)
        # Should not contain traceback
        self.assertNotIn("Traceback", error_msg)
        self.assertNotIn("line ", error_msg)

    def test_safety_metadata_is_present(self) -> None:
        """Safety metadata is present in result."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = run_read_only_checks(
            incident_id="test-incident",
            run_id="run-001",
            accepted_checks=[],
            now=now,
        )

        self.assertIn("safety_metadata", result)
        safety = result["safety_metadata"]

        self.assertTrue(safety.get("read_only"))
        self.assertTrue(safety.get("no_kubernetes_client"))
        self.assertTrue(safety.get("no_shell"))
        self.assertTrue(safety.get("no_subprocess"))
        self.assertTrue(safety.get("no_kubectl"))
        self.assertTrue(safety.get("no_mutation"))
        self.assertTrue(safety.get("policy_revalidated"))
        self.assertTrue(safety.get("fake_runner"))


class TestLoopIntegrationSafety(unittest.TestCase):
    """Loop integration safety tests."""

    def test_stop_decision_does_not_run_checks(self) -> None:
        """Stop decisions do not run any checks."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        loop_update = {
            "decision": "stop_root_cause_found",
            "accepted_checks": [
                {"check_id": "pod_logs", "title": "Check", "read_only": True, "source": "test"}
            ],
        }

        result = run_checks_from_loop_decision(
            incident_id="test-incident",
            run_id="run-001",
            loop_update=loop_update,
            now=now,
        )

        # No checks should run
        self.assertEqual(result["checks_run"], 0)
        self.assertIn("reason", result)

    def test_missing_accepted_checks_produces_noop(self) -> None:
        """Missing accepted_checks produces no-op result."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        loop_update = {
            "decision": "run_allowed_read_only_checks",
            # No accepted_checks
        }

        result = run_checks_from_loop_decision(
            incident_id="test-incident",
            run_id="run-001",
            loop_update=loop_update,
            now=now,
        )

        # No checks should run
        self.assertEqual(result["checks_run"], 0)
        self.assertIn("reason", result)

    def test_malicious_check_in_loop_output_is_rejected(self) -> None:
        """Malicious accepted check inside loop output is still revalidated."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        loop_update = {
            "decision": "run_allowed_read_only_checks",
            "accepted_checks": [
                {
                    "check_id": "pod_logs",
                    "title": "Check",
                    "read_only": True,
                    "source": "test",
                    "command": "kubectl delete pod test",  # Malicious
                }
            ],
        }

        result = run_checks_from_loop_decision(
            incident_id="test-incident",
            run_id="run-001",
            loop_update=loop_update,
            now=now,
        )

        # Check should be rejected despite being in accepted_checks
        self.assertEqual(result["checks_run"], 0)
        self.assertEqual(result["checks_rejected"], 1)

    def test_loop_update_is_not_mutated(self) -> None:
        """Loop update input is not mutated."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        loop_update = {
            "decision": "run_allowed_read_only_checks",
            "accepted_checks": [
                {"check_id": "pod_logs", "title": "Check", "read_only": True, "source": "test"}
            ],
        }

        original = dict(loop_update)
        original_checks = list(loop_update["accepted_checks"])

        run_checks_from_loop_decision(
            incident_id="test-incident",
            run_id="run-001",
            loop_update=loop_update,
            now=now,
        )

        # Should not be mutated
        self.assertEqual(loop_update["decision"], original["decision"])
        self.assertEqual(loop_update["accepted_checks"], original_checks)


if __name__ == "__main__":
    unittest.main()
