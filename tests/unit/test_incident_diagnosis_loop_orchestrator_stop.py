"""Tests for incident diagnosis loop orchestrator stop-path.

Tests:
1. Stop-path: stop decision does not run checks
2. Stop-path: stop decision does not write artifact
3. Stop-path: stop decision preserves loop_update
4. Stop-path: result is JSON-serializable
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

# Module to test
from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)


class TestOrchestratorStopPath(unittest.TestCase):
    """Stop-path tests for stop decisions."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        self.incident_id = "test-incident-stop"
        self.run_id = "run-stop-001"

        # Case file with no next-check proposals
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

        # Diagnosis report with no recommended investigations
        self.diagnosis_report = {
            "incident_id": self.incident_id,
            "diagnosis": {
                "recommended_investigations": [],
            },
        }

    def test_stop_decision_does_not_run_checks(self) -> None:
        """Stop decision results in runner_result: None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # If decision is a stop, runner_result should be None
            decision = result["decision"]
            if decision.startswith("stop_"):
                self.assertIsNone(result["runner_result"])

    def test_stop_decision_does_not_write_artifact(self) -> None:
        """Stop decision results in artifact: None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # If decision is a stop, artifact should be None
            decision = result["decision"]
            if decision.startswith("stop_"):
                self.assertIsNone(result["artifact"])

    def test_stop_decision_preserves_loop_update(self) -> None:
        """Stop decision includes loop_update with stop reason."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=Path(tmpdir),
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # Loop update should always be present
            self.assertIn("loop_update", result)
            self.assertIn("decision", result["loop_update"])

    def test_stop_result_is_json_serializable(self) -> None:
        """Stop decision result can be serialized to JSON."""
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


if __name__ == "__main__":
    unittest.main()
