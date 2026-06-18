"""Tests for incident diagnosis loop orchestrator fake handler injection.

Tests:
1. Custom fake handler is invoked through orchestrator
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Dependencies for building test inputs
from k8s_diag_agent.collect.incident_diagnosis_loop_models import LoopDecision

# Module to test
from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    run_one_read_only_diagnosis_loop_pass,
)
from k8s_diag_agent.collect.incident_fake_handlers import ReadOnlyCheckHandler


class TestOrchestratorFakeHandlerInjection(unittest.TestCase):
    """Test that custom fake handlers are invoked through the orchestrator."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.fixed_now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        self.incident_id = "test-incident-handler"
        self.run_id = "run-handler-001"

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

        # Use registry-approved check_id "pod_logs" so decision is deterministic
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
                        "source": "test",
                    },
                ],
            },
        }

    def test_custom_fake_handler_is_invoked(self) -> None:
        """Custom fake handler is invoked through orchestrator."""
        # Create a custom fake handler that returns unique evidence
        custom_evidence = {
            "summary": "Custom handler was invoked!",
            "custom_marker": "TEST_INVOKED",
        }

        def custom_handler(
            check: dict[str, Any], *, now: datetime | None = None
        ) -> dict[str, Any]:
            return custom_evidence

        # Override the registry-approved "pod_logs" handler
        custom_handlers: dict[str, ReadOnlyCheckHandler] = {
            "pod_logs": custom_handler,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir)

            result = run_one_read_only_diagnosis_loop_pass(
                incident_id=self.incident_id,
                external_analysis_dir=external_dir,
                case_file=self.case_file,
                diagnosis_report=self.diagnosis_report,
                run_id=self.run_id,
                now=self.fixed_now,
                fake_handlers=custom_handlers,
            )

            # Verify the orchestrator ran and returned results
            self.assertIn("decision", result)
            self.assertIn("runner_result", result)

            # Unconditionally assert decision is run_allowed
            self.assertEqual(
                result["decision"],
                LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value,
                "Expected run_allowed_read_only_checks decision",
            )

            runner_result = result["runner_result"]
            self.assertIsNotNone(runner_result)

            # Check that the custom handler's evidence appears in results
            results = runner_result.get("results", [])
            self.assertTrue(len(results) > 0, "Expected at least one result")

            # Find the result for our overridden check
            custom_result = None
            for r in results:
                if r.get("check_id") == "pod_logs":
                    custom_result = r
                    break

            self.assertIsNotNone(
                custom_result,
                "Expected result for pod_logs",
            )

            # Verify custom handler's evidence is in the result
            evidence = custom_result.get("evidence", {})
            self.assertEqual(
                evidence.get("summary"),
                "Custom handler was invoked!",
                "Custom handler was not invoked",
            )
            self.assertEqual(
                evidence.get("custom_marker"),
                "TEST_INVOKED",
                "Custom handler marker not found",
            )


if __name__ == "__main__":
    unittest.main()
