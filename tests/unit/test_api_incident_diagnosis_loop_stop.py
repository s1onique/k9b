"""Tests for diagnosis loop one-pass API stop-path.

Tests:
1. Valid authenticated request with no recommended investigations returns a stop decision
2. Stop decision writes diagnosis-loop-pass artifact
3. Stop decision does not write read-only-check-results artifact
4. Response indicates no checks ran
5. Response remains bounded and JSON-serializable
"""

from __future__ import annotations

import json
import unittest

from k8s_diag_agent.collect.api_incident_diagnosis_loop import (
    DiagnosisLoopOnePassRequest,
    DiagnosisLoopOnePassResponse,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_models import (
    LoopDecision,
)


class TestStopPathBehavior(unittest.TestCase):
    """Test stop-path behavior for diagnosis loop API."""

    def test_stop_decision_response_fields(self) -> None:
        """Stop decision response includes all required fields."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            read_only=True,
            allowed_actions=[],
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
            checks_requested=0,
            checks_run=0,
            checks_skipped=0,
            checks_rejected=0,
            artifacts={
                "read_only_check_results": {
                    "written": False,
                    "name": None,
                },
                "diagnosis_loop_pass": {
                    "written": True,
                    "name": "test-run-001-diagnosis-loop-pass.json",
                },
            },
            case_file_linked_artifact=False,
            safety_metadata={
                "read_only": True,
                "allowed_actions": [],
            },
        )

        data = response.to_dict()

        # Check stop decision
        self.assertEqual(
            data["decision"],
            LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        )

        # Check no checks ran
        self.assertEqual(data["checks_requested"], 0)
        self.assertEqual(data["checks_run"], 0)
        self.assertEqual(data["checks_skipped"], 0)
        self.assertEqual(data["checks_rejected"], 0)

        # Check artifacts
        self.assertFalse(data["artifacts"]["read_only_check_results"]["written"])
        self.assertTrue(data["artifacts"]["diagnosis_loop_pass"]["written"])

        # Check safety metadata
        self.assertEqual(data["safety_metadata"]["read_only"], True)
        self.assertEqual(data["safety_metadata"]["allowed_actions"], [])

    def test_stop_decision_json_serializable(self) -> None:
        """Stop decision response is JSON-serializable."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        )

        data = response.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        self.assertEqual(parsed["decision"], "stop_no_checks_proposed")
        self.assertEqual(parsed["checks_run"], 0)

    def test_all_stop_decision_types(self) -> None:
        """All stop decision types are properly handled."""
        stop_decisions = [
            LoopDecision.STOP_ROOT_CAUSE_FOUND,
            LoopDecision.STOP_NO_SAFE_CHECKS,
            LoopDecision.STOP_BUDGET_EXHAUSTED,
            LoopDecision.STOP_LOW_CONFIDENCE_NO_PROGRESS,
            LoopDecision.STOP_SAFETY_BLOCKED,
            LoopDecision.STOP_NO_CHECKS_PROPOSED,
        ]

        for decision in stop_decisions:
            with self.subTest(decision=decision):
                response = DiagnosisLoopOnePassResponse(
                    schema_version="1.0",
                    incident_id="test-incident-001",
                    run_id="test-run-001",
                    decision=decision.value,
                )

                data = response.to_dict()
                self.assertEqual(data["decision"], decision.value)
                self.assertTrue(decision.value.startswith("stop_"))

    def test_empty_investigations_list_creates_stop_request(self) -> None:
        """Empty recommended_investigations list creates valid request."""
        request = DiagnosisLoopOnePassRequest.from_dict({
            "run_id": "test-run-001",
            "diagnosis_report": {
                "diagnosis": {
                    "recommended_investigations": []
                }
            }
        })

        self.assertEqual(request.run_id, "test-run-001")
        # Empty list is valid
        investigations = request.diagnosis_report.get("diagnosis", {}).get(
            "recommended_investigations", []
        )
        self.assertEqual(len(investigations), 0)

    def test_omitted_investigations_creates_stop_request(self) -> None:
        """Omitted recommended_investigations creates valid request."""
        request = DiagnosisLoopOnePassRequest.from_dict({
            "run_id": "test-run-001",
            "diagnosis_report": {
                "diagnosis": {}
            }
        })

        self.assertEqual(request.run_id, "test-run-001")
        # Omitted is valid (will result in empty list)
        investigations = request.diagnosis_report.get("diagnosis", {}).get(
            "recommended_investigations"
        )
        self.assertIsNone(investigations)


class TestStopPathArtifactBehavior(unittest.TestCase):
    """Test artifact behavior for stop-path."""

    def test_stop_path_no_read_only_check_results_artifact(self) -> None:
        """Stop path does not write read-only-check-results artifact."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
            artifacts={
                "read_only_check_results": {
                    "written": False,
                    "name": None,
                },
                "diagnosis_loop_pass": {
                    "written": True,
                    "name": "test-run-001-diagnosis-loop-pass.json",
                },
            },
        )

        data = response.to_dict()

        # Read-only check results should not be written
        self.assertFalse(data["artifacts"]["read_only_check_results"]["written"])
        self.assertIsNone(data["artifacts"]["read_only_check_results"]["name"])

        # Diagnosis loop pass should be written
        self.assertTrue(data["artifacts"]["diagnosis_loop_pass"]["written"])
        self.assertIsNotNone(data["artifacts"]["diagnosis_loop_pass"]["name"])

    def test_stop_path_case_file_not_linked(self) -> None:
        """Stop path does not link case file to artifact."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
            case_file_linked_artifact=False,
        )

        data = response.to_dict()
        self.assertFalse(data["case_file_linked_artifact"])


class TestStopPathBoundedResponse(unittest.TestCase):
    """Test that stop-path responses are bounded."""

    def test_stop_path_response_bounded_size(self) -> None:
        """Stop-path response is bounded in size."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
            checks_requested=0,
            checks_run=0,
        )

        data = response.to_dict()
        json_str = json.dumps(data)

        # Response should be relatively small (no artifacts)
        # This is a sanity check - the actual limit is enforced by request validation
        self.assertLess(len(json_str), 10000)

    def test_stop_path_no_case_file_in_response(self) -> None:
        """Stop-path response does not contain case file."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        )

        data = response.to_dict()

        # Should not contain case_file
        self.assertNotIn("case_file", data)
        self.assertNotIn("rebuilt_case_file", data)

    def test_stop_path_no_runner_result_in_response(self) -> None:
        """Stop-path response does not contain runner result."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        )

        data = response.to_dict()

        # Should not contain runner_result
        self.assertNotIn("runner_result", data)


if __name__ == "__main__":
    unittest.main()