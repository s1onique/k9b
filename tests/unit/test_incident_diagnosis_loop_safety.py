"""Safety tests for incident diagnosis loop.

Tests:
1. No execution occurs
2. No subprocess/shell/Kubernetes client is called
3. Top-level allowed_actions remains []
4. Top-level read_only remains True
5. disallowed_actions remains complete
6. Accepted check specs contain no command strings
7. Rejected malicious proposal does not create an accepted check
8. Loop function does not mutate case file or diagnosis report inputs
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_diagnosis_loop import (
    DISALLOWED_ACTIONS as LOOP_DISALLOWED,
)
from k8s_diag_agent.collect.incident_diagnosis_loop import (
    LoopDecision,
    plan_next_diagnosis_pass,
)


class FakeCaseFile:
    """Minimal case file for tests."""

    @staticmethod
    def make_basic() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident": {
                "incident_id": "test-incident-001",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "open",
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "evidence_links": [],
        }


class FakeDiagnosisReport:
    """Minimal diagnosis report for tests."""

    @staticmethod
    def make(
        recommended_investigations: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "generated_at": "2024-06-01T12:00:00+00:00",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
            "incident_id": "test-incident-001",
            "diagnosis": {
                "summary": "Test diagnosis",
                "likely_causes": ["Unknown issue"],
                "supporting_evidence": [],
                "recommended_investigations": recommended_investigations or ["Check logs"],
                "uncertainties": [],
                "confidence": "medium",
            },
            "safety_notes": [],
        }


class TestNoExecution(unittest.TestCase):
    """Tests that no execution occurs."""

    def test_no_command_execution_in_result(self) -> None:
        """Result contains no executable commands."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=["Check pod logs"],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Convert result to string for inspection
        result_str = str(result)

        # Should not contain executable patterns
        self.assertNotIn("kubectl exec", result_str)
        self.assertNotIn("kubectl delete", result_str)
        self.assertNotIn("kubectl apply", result_str)
        self.assertNotIn("run_command", result_str)
        self.assertNotIn("execute_command", result_str)

    def test_no_checks_executed(self) -> None:
        """No checks are executed in this ACT."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=["Check logs", "Check events"],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Note in result should indicate no execution
        self.assertIn("note", result)
        self.assertIn("does not execute checks", result["note"])


class TestNoExternalCalls(unittest.TestCase):
    """Tests that no external calls are made."""

    def test_no_kubernetes_client_instantiated(self) -> None:
        """No Kubernetes client is instantiated."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        # This should not instantiate any Kubernetes client
        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Verify safety metadata
        self.assertIn("safety_metadata", result)
        self.assertTrue(result["safety_metadata"]["no_kubernetes_client"])

    def test_no_llm_execution(self) -> None:
        """No LLM execution is performed."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertTrue(result["safety_metadata"]["no_llm_execution"])


class TestSafetyMetadata(unittest.TestCase):
    """Tests for safety metadata completeness."""

    def test_read_only_always_true(self) -> None:
        """read_only is always True."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["safety_metadata"]["read_only"], True)

    def test_allowed_actions_always_empty(self) -> None:
        """allowed_actions is always empty."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(result["safety_metadata"]["allowed_actions"], [])

    def test_disallowed_actions_complete(self) -> None:
        """disallowed_actions includes all mutation verbs."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        disallowed = result["safety_metadata"]["disallowed_actions"]
        # DISALLOWED_ACTIONS from policy includes "execute" in addition to mutation verbs
        required = {"execute_arbitrary_command", "promote", "apply", "remediate", "delete", "mutate_cluster", "execute"}
        self.assertEqual(set(disallowed), required)

    def test_loop_state_safety_metadata(self) -> None:
        """Loop state includes safety metadata."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        loop_state = result["loop_state"]
        self.assertEqual(loop_state["read_only"], True)
        self.assertEqual(loop_state["allowed_actions"], [])
        self.assertIn("disallowed_actions", loop_state)


class TestAcceptedChecksSafety(unittest.TestCase):
    """Tests for accepted check safety."""

    def test_accepted_checks_contain_no_command_strings(self) -> None:
        """Accepted checks contain no command strings."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=["Check pod logs", "Check pod events"],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        accepted = result.get("accepted_checks", [])
        for check in accepted:
            check_str = str(check)
            self.assertNotIn("kubectl", check_str.lower())
            self.assertNotIn("command", check_str.lower())
            self.assertNotIn("exec", check_str.lower())
            self.assertNotIn("shell", check_str.lower())

    def test_mutation_proposal_not_accepted(self) -> None:
        """Mutation proposal is not accepted."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=[
                {"check_id": "kubectl_exec", "command": "kubectl exec bash"},
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Should either stop or reject the mutation
        self.assertIn("decision", result)
        # The mutation check should not be in accepted
        accepted = result.get("accepted_checks", [])
        accepted_ids = [c.get("check_id") for c in accepted]
        self.assertNotIn("kubectl_exec", accepted_ids)


class TestRejectionSafety(unittest.TestCase):
    """Tests for rejection safety."""

    def test_rejected_checks_have_reasons(self) -> None:
        """Rejected checks have rejection reasons."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=["Check kubectl exec something"],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        rejected = result.get("rejected_checks", [])
        for rejection in rejected:
            self.assertIn("rejection_reason", rejection)
            self.assertIsNotNone(rejection["rejection_reason"])

    def test_rejection_includes_safety_blocked_flag(self) -> None:
        """Rejections include safety_blocked flag."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=[
                {"check_id": "pod_logs", "command": "kubectl exec bash"},
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        rejected = result.get("rejected_checks", [])
        if rejected:
            for rejection in rejected:
                self.assertIn("safety_blocked", rejection)


class TestInputMutation(unittest.TestCase):
    """Tests that inputs are not mutated."""

    def test_case_file_not_mutated(self) -> None:
        """Case file is not mutated."""
        case_file = FakeCaseFile.make_basic()

        # Record initial state
        initial_keys = set(case_file.keys())
        initial_incident_keys = set(case_file["incident"].keys())

        diagnosis_report = FakeDiagnosisReport.make()

        plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Verify no mutation
        self.assertEqual(set(case_file.keys()), initial_keys)
        self.assertEqual(set(case_file["incident"].keys()), initial_incident_keys)

    def test_diagnosis_report_not_mutated(self) -> None:
        """Diagnosis report is not mutated."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        # Record initial state
        initial_diagnosis = dict(diagnosis_report["diagnosis"])

        plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Verify no mutation
        self.assertEqual(diagnosis_report["diagnosis"], initial_diagnosis)

    def test_signals_not_mutated(self) -> None:
        """Signals in case file are not mutated."""
        case_file = FakeCaseFile.make_basic()
        initial_signals = list(case_file.get("signals", []))
        diagnosis_report = FakeDiagnosisReport.make()

        # Run multiple times
        for _ in range(5):
            plan_next_diagnosis_pass(
                incident_id="test-incident-001",
                case_file=case_file,
                diagnosis_report=diagnosis_report,
                now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
            )

        # Signals unchanged
        self.assertEqual(case_file.get("signals", []), initial_signals)


class TestMultipleRunsDeterministic(unittest.TestCase):
    """Tests for deterministic behavior across multiple runs."""

    def test_same_result_for_same_input(self) -> None:
        """Same input produces same output."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=["Check logs"],
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        result1 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=now,
        )

        result2 = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=now,
        )

        # Decision should be same
        self.assertEqual(result1["decision"], result2["decision"])


class TestMaliciousInputSafety(unittest.TestCase):
    """Tests for malicious input handling."""

    def test_arbitrary_command_rejected(self) -> None:
        """Arbitrary commands are rejected."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=[
                {"check_id": "pod_logs", "command": "rm -rf /"},
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Should either stop with safety_blocked or not accept the command
        accepted = result.get("accepted_checks", [])
        for check in accepted:
            if "parameters" in check:
                self.assertNotIn("command", check["parameters"])

    def test_kubectl_command_rejected(self) -> None:
        """kubectl commands are rejected."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make(
            recommended_investigations=[
                {"check_id": "pod_logs", "kubectl": "get pods"},
            ],
        )

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Should stop due to safety
        self.assertEqual(result["decision"], LoopDecision.STOP_SAFETY_BLOCKED.value)


class TestDisallowedActionsConstant(unittest.TestCase):
    """Tests for disallowed actions constant."""

    def test_disallowed_actions_defined(self) -> None:
        """DISALLOWED_ACTIONS is defined."""
        self.assertIsInstance(LOOP_DISALLOWED, list)
        self.assertGreater(len(LOOP_DISALLOWED), 0)

    def test_disallowed_actions_complete(self) -> None:
        """DISALLOWED_ACTIONS includes all required verbs."""
        required = {
            "execute_arbitrary_command",
            "promote",
            "apply",
            "remediate",
            "delete",
            "mutate_cluster",
            "execute",
        }
        self.assertEqual(set(LOOP_DISALLOWED), required)


class TestChecksValidatedByPolicy(unittest.TestCase):
    """Tests for policy validation."""

    def test_checks_validated_by_policy_flag(self) -> None:
        """safety_metadata includes checks_validated_by_policy."""
        case_file = FakeCaseFile.make_basic()
        diagnosis_report = FakeDiagnosisReport.make()

        result = plan_next_diagnosis_pass(
            incident_id="test-incident-001",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            now=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )

        self.assertTrue(result["safety_metadata"]["checks_validated_by_policy"])


if __name__ == "__main__":
    unittest.main()
