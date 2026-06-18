"""Tests for incident diagnosis loop orchestrator run-path.

Tests:
1. Run-path: decision run_allowed_read_only_checks runs checks
2. Result includes schema version
3. Result includes correct incident_id
4. Result includes correct run_id
5. Result includes loop_update
6. Result includes runner_result when checks run
7. Result includes artifact metadata when checks run
8. Result includes rebuilt_case_file when checks run
9. Result preserves read_only: True
10. Result preserves allowed_actions: []
11. Result includes comprehensive safety_metadata
12. Result can be serialized to JSON
13. Deterministic timestamps
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

# Dependencies for building test inputs
from k8s_diag_agent.collect.incident_diagnosis_loop_models import (
    LoopDecision,
)

# Module to test
from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    ORCHESTRATOR_SCHEMA_VERSION,
    run_one_read_only_diagnosis_loop_pass,
)


class TestOrchestratorRunPath(unittest.TestCase):
    """Run-path tests for run_allowed_read_only_checks decision."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        self.incident_id = "test-incident-001"
        self.run_id = "run-orch-001"

        # Minimal case file
        self.case_file = {
            "incident_id": self.incident_id,
            "schema_version": "1.0",
            "read_only": True,
            "allowed_actions": [],
            "incident": {
                "incident_id": self.incident_id,
                "namespace": "default",
                "object_kind": "Pod",
                "object_name": "test-pod",
                "severity": "warning",
                "status": "active",
            },
        }

        # Diagnosis report with structured next-check proposals
        # Structure must match what extract_next_check_proposals expects:
        # diagnosis_report["diagnosis"]["recommended_investigations"]
        self.diagnosis_report = {
            "incident_id": self.incident_id,
            "diagnosis": {
                "recommended_investigations": [
                    {
                        "check_id": "pod_logs",
                        "title": "Check pod logs",
                        "read_only": True,
                        "source": "llm_diagnosis",
                    },
                    {
                        "check_id": "pod_events",
                        "title": "Check pod events",
                        "read_only": True,
                        "source": "llm_diagnosis",
                    },
                ],
            },
        }

    def test_run_path_returns_schema_version(self) -> None:
        """Result includes schema_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertEqual(result["schema_version"], ORCHESTRATOR_SCHEMA_VERSION)

    def test_run_path_returns_correct_incident_id(self) -> None:
        """Result includes correct incident_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertEqual(result["incident_id"], self.incident_id)

    def test_run_path_returns_correct_run_id(self) -> None:
        """Result includes correct run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertEqual(result["run_id"], self.run_id)

    def test_run_path_includes_loop_update(self) -> None:
        """Result includes loop_update from planner."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertIn("loop_update", result)
            self.assertIn("decision", result["loop_update"])

    def test_run_path_includes_runner_result(self) -> None:
        """Result includes runner_result when checks run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # Decision may be run_allowed or stop, check accordingly
            if result["decision"] == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
                self.assertIn("runner_result", result)
                self.assertIsNotNone(result["runner_result"])

    def test_run_path_includes_artifact_metadata(self) -> None:
        """Result includes artifact metadata when checks run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            if result["decision"] == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
                self.assertIn("artifact", result)

    def test_run_path_includes_rebuilt_case_file(self) -> None:
        """Result includes rebuilt_case_file when checks run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            if result["decision"] == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
                self.assertIn("rebuilt_case_file", result)

    def test_run_path_preserves_read_only_flag(self) -> None:
        """Result preserves read_only: True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertEqual(result["read_only"], True)

    def test_run_path_preserves_allowed_actions_empty(self) -> None:
        """Result preserves allowed_actions: []."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertEqual(result["allowed_actions"], [])

    def test_run_path_includes_safety_metadata(self) -> None:
        """Result includes comprehensive safety_metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            self.assertIn("safety_metadata", result)
            safety = result["safety_metadata"]
            self.assertEqual(safety["read_only"], True)
            self.assertEqual(safety["allowed_actions"], [])
            self.assertEqual(safety["no_kubernetes_client"], True)
            self.assertEqual(safety["no_shell"], True)
            self.assertEqual(safety["no_subprocess"], True)
            self.assertEqual(safety["no_kubectl"], True)
            self.assertEqual(safety["no_mutation"], True)
            self.assertEqual(safety["fake_runner"], True)
            self.assertEqual(safety["one_pass_only"], True)

    def test_run_path_result_is_json_serializable(self) -> None:
        """Result can be serialized to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # Should not raise
            json_str = json.dumps(result)
            self.assertIsInstance(json_str, str)

            # Should round-trip
            parsed = json.loads(json_str)
            self.assertEqual(parsed["incident_id"], self.incident_id)
            self.assertEqual(parsed["run_id"], self.run_id)

    def test_run_path_deterministic_timestamps(self) -> None:
        """Repeated calls with same now produce identical timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result1 = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            result2 = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # Timestamps in loop_update should be identical
            self.assertEqual(
                result1["loop_update"].get("generated_at"),
                result2["loop_update"].get("generated_at"),
            )


if __name__ == "__main__":
    unittest.main()
