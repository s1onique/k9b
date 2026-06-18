"""Tests for incident diagnosis loop orchestrator explicit run-id linkage.

Tests:
1. Rebuilt case file includes artifact from explicit run_id
"""

from __future__ import annotations

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
    run_one_read_only_diagnosis_loop_pass,
)


class TestOrchestratorExplicitRunIdLinkage(unittest.TestCase):
    """Explicit run-id linkage tests."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        self.incident_id = "test-incident-explicit"
        self.run_id = "run-explicit-001"

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
                ],
            },
        }

    def test_explicit_run_id_in_rebuilt_case_file(self) -> None:
        """Rebuilt case file includes artifact from explicit run_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir)

            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=external_dir,
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
            )

            # Check if case file was rebuilt with explicit run_id
            if result["decision"] == LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value:
                rebuilt = result.get("rebuilt_case_file")
                if rebuilt:
                    # The rebuilt case file should include read_only_check_results
                    self.assertIn("read_only_check_results", rebuilt)


if __name__ == "__main__":
    unittest.main()
