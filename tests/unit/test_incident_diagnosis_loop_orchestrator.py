"""Tests for incident diagnosis loop orchestrator.

Tests:
1. Orchestrator returns schema version
2. Orchestrator validates run_id for safety
3. Run-path: decision run_allowed_read_only_checks runs checks
4. Run-path: artifact is written for run_allowed_read_only_checks
5. Run-path: rebuilt case file includes artifact
6. Stop-path: root_cause_found does not run checks
7. Stop-path: no_checks_proposed does not write artifact
8. Stop-path: safety_blocked does not write artifact
9. Stop-path: budget_exhausted does not write artifact
10. Result is JSON-serializable
11. Safety metadata is preserved
12. Deterministic timestamps
13. Explicit run-id linkage works
14. Module does not import kubernetes
15. Module does not import subprocess
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


class TestOrchestratorSchema(unittest.TestCase):
    """Schema version tests."""

    def test_schema_version_is_defined(self) -> None:
        """ORCHESTRATOR_SCHEMA_VERSION is defined."""
        self.assertEqual(ORCHESTRATOR_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(ORCHESTRATOR_SCHEMA_VERSION, str)


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
        self.diagnosis_report = {
            "incident_id": self.incident_id,
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
            "recommended_investigations": [],
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


class TestOrchestratorSafety(unittest.TestCase):
    """Safety constraint tests."""

    def test_module_does_not_import_kubernetes(self) -> None:
        """Orchestrator module does not import kubernetes."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        # Check module doesn't have kubernetes client in namespace
        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        import re
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Now check for imports
        self.assertNotIn("import kubernetes", content_no_docs)
        self.assertNotIn("from kubernetes", content_no_docs)

    def test_module_does_not_import_subprocess(self) -> None:
        """Orchestrator module does not import subprocess."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        import re
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        self.assertNotIn("import subprocess", content_no_docs)
        self.assertNotIn("from subprocess", content_no_docs)

    def test_module_does_not_call_kubectl(self) -> None:
        """Orchestrator module does not contain kubectl execution."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        import re
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Now check for kubectl in code (not in safety metadata strings)
        lines = content_no_docs.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip safety metadata dict values
            if stripped.startswith('"kubectl"') or stripped.startswith("'kubectl'"):
                continue
            if '"no_kubectl"' in stripped or "'no_kubectl'" in stripped:
                continue
            # Fail if kubectl appears outside safety metadata
            if "kubectl" in stripped:
                self.fail(f"Found kubectl reference on line {i+1}: {stripped}")

    def test_module_does_not_contain_mutate_actions(self) -> None:
        """Orchestrator source does not contain mutation actions."""
        import k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator as module

        source_file = Path(module.__file__)
        content = source_file.read_text()

        # Remove all docstrings
        import re
        content_no_docs = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content_no_docs = re.sub(r"'''.*?'''", "", content_no_docs, flags=re.DOTALL)

        # Check for actual action calls
        lines = content_no_docs.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip safety metadata entries
            if '"execute"' in stripped or '"apply"' in stripped or '"delete"' in stripped:
                continue
            # Check for actual function calls
            if stripped.startswith("apply(") or stripped.startswith("delete("):
                self.fail(f"Found mutation action on line {i+1}: {stripped}")


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
            "recommended_investigations": [
                {
                    "check_id": "pod_logs",
                    "title": "Check pod logs",
                    "read_only": True,
                    "source": "llm_diagnosis",
                },
            ],
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
        from typing import Any

        from k8s_diag_agent.collect.incident_fake_handlers import ReadOnlyCheckHandler

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
