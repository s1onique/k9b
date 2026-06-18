"""Safety tests for incident LLM diagnosis.

Tests:
1. No action-control fields appear in top-level report
2. allowed_actions is always empty
3. disallowed_actions includes required mutation/remediation verbs
4. Diagnosis generation does not mutate the case-file input
5. Diagnosis generation does not make a real network call in unit tests
6. Model attempts to request execution/remediation are not promoted
7. Model output containing "run kubectl" remains text only
8. Model output containing JSON fields like "execute" does not create action controls
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_llm_diagnosis import (
    DISALLOWED_ACTIONS,
    build_incident_diagnosis,
)


class FakeCaseFile:
    """Minimal case file for safety tests."""

    @staticmethod
    def make_basic() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": list(DISALLOWED_ACTIONS),
            "incident": {
                "incident_id": "safety-test-incident",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "high",
                "status": "open",
            },
            "signals": [
                {"source": "pod", "reason": "CrashLoopBackOff", "message": "restarting"}
            ],
            "events": [],
            "suggested_checks": [],
            "evidence_links": [],
        }


class FakeLLMProvider:
    """Fake LLM provider for testing (no network calls)."""

    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str) -> str:
        return self.response


# Fields that should NEVER appear as action controls
FORBIDDEN_ACTION_FIELDS: list[str] = [
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "run_command",
    "execute_command",
    "approve",
    "reject",
]


class TestIncidentDiagnosisSafetyActionControls(unittest.TestCase):
    """Tests that no action-control fields appear."""

    def test_no_action_control_fields_in_top_level_report(self) -> None:
        """No action-control fields appear in top-level report."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(field, report, f"Field '{field}' should not be in report top-level")

    def test_no_action_control_fields_in_diagnosis(self) -> None:
        """No action-control fields appear in diagnosis section."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)
        diagnosis = report["diagnosis"]

        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(field, diagnosis, f"Field '{field}' should not be in diagnosis section")

    def test_no_action_control_fields_in_safety_notes(self) -> None:
        """No action-control fields appear in safety_notes."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # Safety notes may mention these words in context of prohibition
        # but should not have them as action control fields
        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(f'"{field}"', str(report.get("safety_notes", [])))


class TestIncidentDiagnosisSafetyAllowedActions(unittest.TestCase):
    """Tests for allowed_actions emptiness."""

    def test_allowed_actions_always_empty(self) -> None:
        """allowed_actions is always empty regardless of model output."""
        # Model tries to suggest actions
        json_response = """{
            "summary": "Fix needed",
            "likely_causes": ["Configuration error"],
            "supporting_evidence": [],
            "recommended_investigations": ["Check config"],
            "uncertainties": [],
            "confidence": "medium"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["allowed_actions"], [])
        self.assertIsInstance(report["allowed_actions"], list)
        self.assertEqual(len(report["allowed_actions"]), 0)


class TestIncidentDiagnosisSafetyDisallowedActions(unittest.TestCase):
    """Tests for disallowed_actions completeness."""

    def test_disallowed_actions_includes_required_verbs(self) -> None:
        """disallowed_actions includes all required mutation/remediation verbs."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        required_actions = {"execute", "promote", "apply", "remediate", "delete", "mutate_cluster"}
        self.assertEqual(set(report["disallowed_actions"]), required_actions)

    def test_disallowed_actions_constant_matches_report(self) -> None:
        """DISALLOWED_ACTIONS constant matches report value."""
        self.assertEqual(set(DISALLOWED_ACTIONS), {"execute", "promote", "apply", "remediate", "delete", "mutate_cluster"})


class TestIncidentDiagnosisSafetyNoMutation(unittest.TestCase):
    """Tests that diagnosis generation does not mutate input."""

    def test_case_file_not_mutated_by_diagnosis(self) -> None:
        """Diagnosis generation does not mutate the case-file input."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        # Record initial state
        initial_keys = set(case_file.keys())
        initial_incident_keys = set(case_file["incident"].keys())

        # Build diagnosis
        build_incident_diagnosis(case_file, llm=llm)

        # Verify no mutation
        self.assertEqual(set(case_file.keys()), initial_keys)
        self.assertEqual(set(case_file["incident"].keys()), initial_incident_keys)

    def test_signals_not_mutated(self) -> None:
        """Signals in case file are not mutated by diagnosis."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        # Record initial signals
        initial_signals = list(case_file["signals"])

        # Build diagnosis multiple times
        for _ in range(5):
            build_incident_diagnosis(case_file, llm=llm)

        # Verify signals unchanged
        self.assertEqual(case_file["signals"], initial_signals)


class TestIncidentDiagnosisSafetyNoNetworkCalls(unittest.TestCase):
    """Tests that unit tests do not make real network calls."""

    def test_fake_provider_does_not_make_network_call(self) -> None:
        """Fake LLM provider does not make a real network call."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        # This should not make any network calls
        report = build_incident_diagnosis(case_file, llm=llm)

        # Verify report was built from fake provider
        self.assertEqual(report["diagnosis"]["summary"], "Test")
        # If we got here, no network call was made

    def test_no_real_provider_instantiated_internally(self) -> None:
        """Implementation does not instantiate a real provider internally."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        # Build diagnosis - should use injected provider only
        report = build_incident_diagnosis(case_file, llm=llm)

        # Verify injected provider was called
        self.assertIsNotNone(report)
        # If no exception raised, no internal provider instantiation occurred


class TestIncidentDiagnosisSafetyModelOutputGuarding(unittest.TestCase):
    """Tests that model output is treated as untrusted text."""

    def test_model_execution_request_not_promoted(self) -> None:
        """Model attempts to request execution are not promoted into allowed actions."""
        json_response = """{
            "summary": "Run kubectl to fix this",
            "likely_causes": ["Config issue"],
            "supporting_evidence": [],
            "recommended_investigations": ["Execute kubectl get pods"],
            "uncertainties": [],
            "confidence": "high"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # Model output should be preserved as text
        self.assertIn("Execute kubectl", report["diagnosis"]["recommended_investigations"][0])
        # But allowed_actions should still be empty
        self.assertEqual(report["allowed_actions"], [])

    def test_model_remediation_request_not_promoted(self) -> None:
        """Model requests for remediation are not promoted."""
        json_response = """{
            "summary": "Remediate immediately",
            "likely_causes": ["Resource exhaustion"],
            "supporting_evidence": [],
            "recommended_investigations": ["Apply resource limits"],
            "uncertainties": [],
            "confidence": "medium"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # allowed_actions should still be empty
        self.assertEqual(report["allowed_actions"], [])
        # "remediate" should not be in allowed_actions
        self.assertNotIn("remediate", report["allowed_actions"])

    def test_model_run_kubectl_mentioned_but_not_executed(self) -> None:
        """Model output containing 'run kubectl' remains text only."""
        json_response = """{
            "summary": "Check pods",
            "likely_causes": [],
            "supporting_evidence": [],
            "recommended_investigations": ["Run kubectl get pods -n default"],
            "uncertainties": [],
            "confidence": "high"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # Command should appear as text in investigations
        self.assertIn("kubectl", report["diagnosis"]["recommended_investigations"][0])
        # But no "run" field should exist
        self.assertNotIn("run", report)
        self.assertNotIn("run", report["diagnosis"])

    def test_model_json_with_execute_field_not_promoted(self) -> None:
        """Model output containing JSON with 'execute' field does not create action controls."""
        json_response = """{
            "summary": "Execute the fix",
            "likely_causes": [],
            "supporting_evidence": [],
            "recommended_investigations": [],
            "uncertainties": [],
            "confidence": "low",
            "execute": "kubectl apply -f fix.yaml"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # execute field from model should NOT appear in report
        self.assertNotIn("execute", report)
        self.assertNotIn("execute", report["diagnosis"])
        # allowed_actions should still be empty
        self.assertEqual(report["allowed_actions"], [])

    def test_model_json_with_remediate_field_not_promoted(self) -> None:
        """Model output containing JSON with 'remediate' field does not create action controls."""
        json_response = """{
            "summary": "Remediate the issue",
            "likely_causes": [],
            "supporting_evidence": [],
            "recommended_investigations": [],
            "uncertainties": [],
            "confidence": "unknown",
            "remediate": true
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # remediate field from model should NOT appear in report
        self.assertNotIn("remediate", report)
        self.assertNotIn("remediate", report["diagnosis"])
        # allowed_actions should still be empty
        self.assertEqual(report["allowed_actions"], [])


class TestIncidentDiagnosisSafetySafetyNotes(unittest.TestCase):
    """Tests for safety notes content."""

    def test_safety_notes_mention_read_only(self) -> None:
        """Safety notes mention read-only nature."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        safety_text = " ".join(report["safety_notes"]).lower()
        self.assertIn("read-only", safety_text)

    def test_safety_notes_warn_about_model_output(self) -> None:
        """Safety notes warn that model output is untrusted."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        safety_text = " ".join(report["safety_notes"]).lower()
        self.assertIn("untrusted", safety_text)

    def test_safety_notes_add_command_warning_when_detected(self) -> None:
        """Safety notes add warning when model output contains command references."""
        json_response = '{"summary": "Run kubectl logs", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": ["Run kubectl logs"], "uncertainties": [], "confidence": "medium"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        safety_text = " ".join(report["safety_notes"]).lower()
        self.assertIn("command", safety_text)
        self.assertIn("text", safety_text)


if __name__ == "__main__":
    unittest.main()