"""Prompt tests for incident LLM diagnosis.

Tests:
1. Prompt includes incident identity from case file
2. Prompt includes linked signals, evidence, events, suggested checks
3. Prompt includes read-only safety instructions
4. Prompt includes forbidden action instructions
5. Prompt is bounded by max_prompt_chars
6. Prompt does not include execution-control affordances
7. Prompt tells model not to invent evidence
8. Prompt tells model to separate facts, hypotheses, missing evidence
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.incident_llm_diagnosis import (
    DISALLOWED_ACTIONS,
    build_diagnosis_prompt,
)


class FakeCaseFile:
    """Minimal case file for prompt tests."""

    @staticmethod
    def make_basic() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "disallowed_actions": list(DISALLOWED_ACTIONS),
            "incident": {
                "incident_id": "test-incident-001",
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "failing-pod",
                "severity": "high",
                "status": "open",
                "first_observed_at": "2024-06-01T10:00:00+00:00",
                "last_observed_at": "2024-06-01T12:00:00+00:00",
            },
            "signals": [
                {
                    "source": "pod",
                    "reason": "CrashLoopBackOff",
                    "message": "restarting",
                    "captured_at": "2024-06-01T10:00:00+00:00",
                    "run_id": "run-001",
                }
            ],
            "events": [
                {
                    "event_type": "STATUS_CHANGED",
                    "occurred_at": "2024-06-01T10:00:00+00:00",
                    "message": "Pod status changed",
                }
            ],
            "suggested_checks": [
                {"description": "Check pod logs", "method": "kubectl", "status": "suggested"}
            ],
            "evidence_links": [],
        }


class TestIncidentDiagnosisPromptBasic(unittest.TestCase):
    """Basic prompt content tests."""

    def test_prompt_includes_incident_identity(self) -> None:
        """Prompt includes incident identity from case file."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("test-incident-001", prompt)
        self.assertIn("default", prompt)
        self.assertIn("Pod", prompt)
        self.assertIn("failing-pod", prompt)
        self.assertIn("high", prompt)

    def test_prompt_includes_signal_count(self) -> None:
        """Prompt includes signal count from case file."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("signal_count", prompt)
        self.assertIn("1", prompt)

    def test_prompt_includes_sample_signals(self) -> None:
        """Prompt includes sample signals when present."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("sample_signals", prompt)
        self.assertIn("CrashLoopBackOff", prompt)

    def test_prompt_includes_event_count(self) -> None:
        """Prompt includes event count from case file."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("event_count", prompt)

    def test_prompt_includes_suggested_check_count(self) -> None:
        """Prompt includes suggested check count from case file."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("suggested_check_count", prompt)


class TestIncidentDiagnosisPromptSafety(unittest.TestCase):
    """Safety instruction tests for prompt."""

    def test_prompt_includes_read_only_instruction(self) -> None:
        """Prompt includes read-only safety instructions."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("read-only", prompt.lower())
        self.assertIn("MUST NOT", prompt)

    def test_prompt_includes_forbidden_action_instructions(self) -> None:
        """Prompt includes forbidden action instructions."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("execute", prompt.lower())
        self.assertIn("promote", prompt.lower())
        self.assertIn("apply", prompt.lower())
        self.assertIn("remediate", prompt.lower())

    def test_prompt_forbids_inventing_evidence(self) -> None:
        """Prompt tells model not to invent evidence."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("Invent", prompt)
        self.assertIn("evidence", prompt.lower())
        self.assertIn("case file", prompt.lower())

    def test_prompt_tells_model_to_separate_facts_hypotheses(self) -> None:
        """Prompt tells model to separate facts, hypotheses, missing evidence."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        # Check for separation instructions
        self.assertIn("facts", prompt.lower())
        self.assertIn("hypotheses", prompt.lower())
        self.assertIn("evidence", prompt.lower())

    def test_prompt_includes_output_format(self) -> None:
        """Prompt includes expected output format instructions."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertIn("JSON", prompt)
        self.assertIn("summary", prompt)
        self.assertIn("likely_causes", prompt)
        self.assertIn("confidence", prompt)


class TestIncidentDiagnosisPromptBounds(unittest.TestCase):
    """Prompt bound/bounded tests."""

    def test_prompt_respects_max_prompt_chars(self) -> None:
        """Prompt is bounded by max_prompt_chars."""
        case_file = FakeCaseFile.make_basic()
        max_chars = 500
        prompt = build_diagnosis_prompt(case_file, max_prompt_chars=max_chars)

        self.assertLessEqual(len(prompt), max_chars + len("\n\n[PROMPT TRUNCATED]"))

    def test_prompt_handles_empty_case_file(self) -> None:
        """Prompt handles empty/minimal case file gracefully."""
        case_file: dict[str, object] = {}
        prompt = build_diagnosis_prompt(case_file)

        self.assertIsInstance(prompt, str)
        self.assertIn("Incident Diagnosis Request", prompt)
        # Should still have safety instructions
        self.assertIn("read-only", prompt.lower())

    def test_prompt_handles_large_signals_list(self) -> None:
        """Prompt handles large signals list with truncation."""
        case_file = FakeCaseFile.make_basic()
        # Add many signals
        case_file["signals"] = [
            {"source": "pod", "reason": f"Reason-{i}", "message": f"msg-{i}"}
            for i in range(100)
        ]
        prompt = build_diagnosis_prompt(case_file, max_incident_json_chars=1000)

        self.assertIsInstance(prompt, str)
        # Only first 5 signals should be included
        self.assertIn("sample_signals", prompt)

    def test_prompt_strips_execution_fields_from_suggested_checks(self) -> None:
        """Prompt strips execution fields from suggested checks."""
        case_file = FakeCaseFile.make_basic()
        case_file["suggested_checks"] = [
            {
                "description": "Check logs",
                "method": "kubectl",
                "status": "suggested",
                "run": "kubectl logs",  # Should be stripped
                "execute": "apply -f fix.yaml",  # Should be stripped
                "action": "delete pod",  # Should be stripped
            }
        ]
        prompt = build_diagnosis_prompt(case_file)

        # Execution field values should not appear in prompt
        self.assertNotIn("kubectl logs", prompt)
        self.assertNotIn("apply -f fix.yaml", prompt)
        self.assertNotIn("delete pod", prompt)
        # But description should remain
        self.assertIn("Check logs", prompt)
        self.assertIn("kubectl", prompt)  # method field is allowed


class TestIncidentDiagnosisPromptExecutionAffordances(unittest.TestCase):
    """Tests that prompt does not include execution-control affordances."""

    def test_prompt_does_not_include_run_command(self) -> None:
        """Prompt does not include run command affordances."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        # Should not have bare "run" as action indicator
        self.assertNotIn("run:", prompt)
        self.assertNotIn("run ", prompt.lower())

    def test_prompt_does_not_include_execute_field(self) -> None:
        """Prompt does not include execute action field."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertNotIn('"execute"', prompt)

    def test_prompt_does_not_include_action_field(self) -> None:
        """Prompt does not include generic action field."""
        case_file = FakeCaseFile.make_basic()
        prompt = build_diagnosis_prompt(case_file)

        self.assertNotIn('"action"', prompt)


if __name__ == "__main__":
    unittest.main()