"""Policy tests for incident diagnosis loop - Part 1.

Tests for policy constants and known read-only checks.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_next_check_policy import (
    DISALLOWED_ACTIONS,
    FORBIDDEN_COMMAND_FIELDS,
    MUTATION_CHECK_IDS,
    READ_ONLY_CHECK_REGISTRY,
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
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "pod_logs", "title": "Read pod logs"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.validated_check)
        self.assertEqual(result.validated_check["check_id"], "pod_logs")

    def test_pod_events_accepted(self) -> None:
        """pod_events is accepted."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "pod_events", "title": "Read pod events"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_deployment_status_accepted(self) -> None:
        """deployment_status is accepted."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "deployment_status", "title": "Read deployment"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_node_status_accepted(self) -> None:
        """node_status is accepted."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "node_status", "title": "Read node"}
        result = validate_next_check_proposal(proposal)

        self.assertTrue(result.accepted)

    def test_all_registry_checks_accepted(self) -> None:
        """All checks in registry are accepted."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        for check_id in READ_ONLY_CHECK_REGISTRY:
            proposal = {"check_id": check_id, "title": f"Check {check_id}"}
            result = validate_next_check_proposal(proposal)

            self.assertTrue(result.accepted, f"Check {check_id} should be accepted")


class TestUnknownCheckIDs(unittest.TestCase):
    """Tests for unknown check IDs."""

    def test_unknown_check_id_rejected(self) -> None:
        """Unknown check ID is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "unknown_check", "title": "Unknown"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertIsNotNone(result.rejection_reason)
        self.assertIn("not in read-only registry", result.rejection_reason)

    def test_arbitrary_string_rejected(self) -> None:
        """Arbitrary string as check_id is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "kubectl get pods", "title": "Run command"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)

    def test_malformed_check_id_rejected(self) -> None:
        """Malformed check_id is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "random-command-123", "title": "Random"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)


class TestMutationCheckIDs(unittest.TestCase):
    """Tests for mutation/remediation check IDs."""

    def test_kubectl_exec_rejected(self) -> None:
        """kubectl_exec is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "kubectl_exec", "title": "Exec into pod"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_kubectl_apply_rejected(self) -> None:
        """kubectl_apply is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "kubectl_apply", "title": "Apply manifest"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_restart_pod_rejected(self) -> None:
        """restart_pod is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "restart_pod", "title": "Restart pod"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_scale_deployment_rejected(self) -> None:
        """scale_deployment is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "scale_deployment", "title": "Scale"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)

    def test_execute_command_rejected(self) -> None:
        """execute_command is rejected."""
        from k8s_diag_agent.collect.incident_next_check_policy import validate_next_check_proposal
        proposal = {"check_id": "execute_command", "title": "Execute"}
        result = validate_next_check_proposal(proposal)

        self.assertFalse(result.accepted)
        self.assertTrue(result.safety_blocked)


if __name__ == "__main__":
    unittest.main()
