"""Response tests for incident LLM diagnosis.

Tests:
1. Fake LLM JSON output produces structured diagnosis report
2. Fake LLM non-JSON output is wrapped safely
3. Fake LLM malformed JSON output is handled gracefully
4. Missing optional model fields default safely
5. Injected now makes output deterministic
6. raw_model_output is bounded
7. Diagnosis report includes incident ID from case file
8. Diagnosis report preserves read-only safety metadata
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_llm_diagnosis import (
    DISALLOWED_ACTIONS,
    build_incident_diagnosis,
)


class FakeCaseFile:
    """Minimal case file for response tests."""

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
            },
            "signals": [],
            "events": [],
            "suggested_checks": [],
            "evidence_links": [],
        }


class FakeLLMProvider:
    """Fake LLM provider for testing (no network calls)."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


class TestIncidentDiagnosisResponseJSON(unittest.TestCase):
    """Tests for valid JSON model output."""

    def test_valid_json_output_produces_structured_report(self) -> None:
        """Fake LLM JSON output produces structured diagnosis report."""
        json_response = """{
            "summary": "Pod is in CrashLoopBackOff state",
            "likely_causes": ["Resource limits too low", "Application error"],
            "supporting_evidence": ["Signal: CrashLoopBackOff"],
            "recommended_investigations": ["Check resource limits", "Review application logs"],
            "uncertainties": ["Unknown if limits are configured"],
            "confidence": "medium"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        report = build_incident_diagnosis(case_file, llm=llm, now=now)

        self.assertIn("schema_version", report)
        self.assertEqual(report["schema_version"], "1.0")
        self.assertIn("diagnosis", report)
        self.assertEqual(report["diagnosis"]["summary"], "Pod is in CrashLoopBackOff state")
        self.assertEqual(report["diagnosis"]["confidence"], "medium")

    def test_json_with_sample_signals_parsed(self) -> None:
        """JSON output with sample signals is parsed correctly."""
        json_response = """{
            "summary": "Multiple issues detected",
            "likely_causes": ["CrashLoopBackOff"],
            "supporting_evidence": [],
            "recommended_investigations": [],
            "uncertainties": [],
            "confidence": "high"
        }"""
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIsInstance(report["diagnosis"]["likely_causes"], list)
        self.assertEqual(report["diagnosis"]["likely_causes"][0], "CrashLoopBackOff")


class TestIncidentDiagnosisResponseNonJSON(unittest.TestCase):
    """Tests for non-JSON model output."""

    def test_plain_text_output_wrapped_safely(self) -> None:
        """Fake LLM non-JSON output is wrapped safely."""
        plain_text = "The pod appears to be crashing due to resource issues."
        llm = FakeLLMProvider(plain_text)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("diagnosis", report)
        # Plain text should be in summary
        self.assertIn("crashing", report["diagnosis"]["summary"])
        # Should indicate JSON parse failure
        self.assertIn("Model output was not in expected JSON format", report["diagnosis"]["uncertainties"][0])

    def test_markdown_code_block_wrapped(self) -> None:
        """Markdown code block output is handled."""
        markdown_response = """```json
{
    "summary": "Test diagnosis",
    "likely_causes": ["Test"],
    "supporting_evidence": [],
    "recommended_investigations": [],
    "uncertainties": [],
    "confidence": "low"
}
```"""
        llm = FakeLLMProvider(markdown_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["diagnosis"]["summary"], "Test diagnosis")

    def test_malformed_json_handled_gracefully(self) -> None:
        """Fake LLM malformed JSON output is handled gracefully."""
        malformed = '{"summary": "Incomplete json", "likely_causes": [}'
        llm = FakeLLMProvider(malformed)
        case_file = FakeCaseFile.make_basic()

        # Should not raise, should handle gracefully
        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("diagnosis", report)
        self.assertEqual(report["diagnosis"]["confidence"], "unknown")

    def test_random_text_output_handled(self) -> None:
        """Random text output is handled without crash."""
        random_text = "asdfghjkl qwerty uiop"
        llm = FakeLLMProvider(random_text)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("diagnosis", report)
        self.assertIn("safety_notes", report)


class TestIncidentDiagnosisResponseDefaults(unittest.TestCase):
    """Tests for missing optional field defaults."""

    def test_missing_optional_fields_default_safely(self) -> None:
        """Missing optional model fields default safely."""
        minimal_json = '{"summary": "Minimal response"}'
        llm = FakeLLMProvider(minimal_json)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["diagnosis"]["likely_causes"], [])
        self.assertEqual(report["diagnosis"]["supporting_evidence"], [])
        self.assertEqual(report["diagnosis"]["recommended_investigations"], [])
        self.assertEqual(report["diagnosis"]["uncertainties"], [])  # JSON parsed OK, no fallback error
        self.assertEqual(report["diagnosis"]["confidence"], "unknown")

    def test_empty_json_object_handled(self) -> None:
        """Empty JSON object is handled gracefully."""
        llm = FakeLLMProvider("{}")
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("diagnosis", report)
        self.assertEqual(report["diagnosis"]["confidence"], "unknown")


class TestIncidentDiagnosisResponseDeterminism(unittest.TestCase):
    """Tests for output determinism with injected time."""

    def test_injected_now_makes_output_deterministic(self) -> None:
        """Injected now makes output deterministic."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        report1 = build_incident_diagnosis(case_file, llm=llm, now=now)
        report2 = build_incident_diagnosis(case_file, llm=llm, now=now)

        self.assertEqual(report1["generated_at"], report2["generated_at"])
        self.assertEqual(report1["generated_at"], "2024-06-01T12:00:00+00:00")

    def test_different_now_produces_different_timestamp(self) -> None:
        """Different now produces different timestamp."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()
        now1 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        now2 = datetime(2024, 6, 1, 13, 0, 0, tzinfo=UTC)

        report1 = build_incident_diagnosis(case_file, llm=llm, now=now1)
        report2 = build_incident_diagnosis(case_file, llm=llm, now=now2)

        self.assertNotEqual(report1["generated_at"], report2["generated_at"])


class TestIncidentDiagnosisResponseBounds(unittest.TestCase):
    """Tests for output bounds."""

    def test_raw_output_is_bounded(self) -> None:
        """raw_model_output is bounded by max_raw_output_chars."""
        long_output = "x" * 20000
        llm = FakeLLMProvider(long_output)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm, max_raw_output_chars=5000)

        self.assertLessEqual(len(report["raw_model_output"]), 5000 + len("\n\n[OUTPUT TRUNCATED]"))
        self.assertIn("[OUTPUT TRUNCATED]", report["raw_model_output"])

    def test_long_summary_truncated_in_fallback(self) -> None:
        """Long summary is truncated in plain text fallback."""
        long_text = "A" * 1000
        llm = FakeLLMProvider(long_text)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        # Should be truncated to 500 chars in fallback
        self.assertLessEqual(len(report["diagnosis"]["summary"]), 500)


class TestIncidentDiagnosisResponseMetadata(unittest.TestCase):
    """Tests for diagnosis report metadata."""

    def test_report_includes_incident_id(self) -> None:
        """Diagnosis report includes incident ID from case file."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["incident_id"], "test-incident-001")

    def test_report_includes_raw_model_output(self) -> None:
        """Diagnosis report includes raw model output."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("raw_model_output", report)
        self.assertIsInstance(report["raw_model_output"], str)

    def test_report_includes_safety_notes(self) -> None:
        """Diagnosis report includes safety notes."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("safety_notes", report)
        self.assertIsInstance(report["safety_notes"], list)
        self.assertGreater(len(report["safety_notes"]), 0)


class TestIncidentDiagnosisResponseSafetyMetadata(unittest.TestCase):
    """Tests for safety metadata preservation."""

    def test_report_has_read_only_true(self) -> None:
        """Diagnosis report has read_only: True."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["read_only"], True)

    def test_report_has_empty_allowed_actions(self) -> None:
        """Diagnosis report has allowed_actions: []."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertEqual(report["allowed_actions"], [])

    def test_report_has_disallowed_actions(self) -> None:
        """Diagnosis report has disallowed_actions list."""
        json_response = '{"summary": "Test", "likely_causes": [], "supporting_evidence": [], "recommended_investigations": [], "uncertainties": [], "confidence": "low"}'
        llm = FakeLLMProvider(json_response)
        case_file = FakeCaseFile.make_basic()

        report = build_incident_diagnosis(case_file, llm=llm)

        self.assertIn("disallowed_actions", report)
        self.assertIsInstance(report["disallowed_actions"], list)
        self.assertIn("execute", report["disallowed_actions"])
        self.assertIn("remediate", report["disallowed_actions"])


if __name__ == "__main__":
    unittest.main()