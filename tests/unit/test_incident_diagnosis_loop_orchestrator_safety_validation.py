"""Tests for incident diagnosis loop orchestrator safety validation.

Tests:
1. Safe run_id values are accepted
2. Unsafe run_id values are rejected
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# Module to test
from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)


class TestOrchestratorSafetyValidation(unittest.TestCase):
    """Safety validation tests."""

    def test_safe_run_id_is_accepted(self) -> None:
        """Safe run_id values are accepted."""
        # These should not raise
        run_ids = [
            "run-001",
            "run_test_001",
            "Run.Test-001",
            "a",
            "A1",
        ]
        for run_id in run_ids:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = run_one_read_only_diagnosis_loop_pass(
                    incident_id="test-incident",
                    external_analysis_dir=Path(tmpdir),
                    case_file={"incident_id": "test-incident"},
                    diagnosis_report={"hypotheses": []},
                    run_id=run_id,
                )
                # Should complete without raising
                self.assertIn("decision", result)

    def test_unsafe_run_id_is_rejected(self) -> None:
        """Unsafe run_id values are rejected."""
        unsafe_run_ids = [
            "../etc/passwd",
            "run;rm -rf",
            "run$(whoami)",
            "run`whoami`",
            "/etc/passwd",
            "..\\windows\\system32",
            "",
            None,
        ]
        # Only string run_ids can be validated
        string_unsafe = [r for r in unsafe_run_ids if isinstance(r, str)]
        for run_id in string_unsafe:
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(ValueError):
                    run_one_read_only_diagnosis_loop_pass(
                        incident_id="test-incident",
                        external_analysis_dir=Path(tmpdir),
                        case_file={"incident_id": "test-incident"},
                        diagnosis_report={"hypotheses": []},
                        run_id=run_id,
                    )


if __name__ == "__main__":
    unittest.main()
