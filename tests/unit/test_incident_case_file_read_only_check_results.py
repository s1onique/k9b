"""Tests for read-only check results integration in incident case-file.

Tests prove:
1. build_incident_case_file() includes read-only check results when matching artifacts exist
2. No matching artifacts gives empty section
3. Case file includes run_id traceability
4. Case file includes check_id/status/summary for each result
5. Case file does not include executable fields
6. Case file remains read-only
7. Case file remains JSON-serializable
8. Existing suggested-check and prior-analysis behavior still works
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.incident_case_file import build_incident_case_file
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_read_only_check_artifacts import (
    write_read_only_check_result_artifact,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_lifecycle_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    make_candidate,
)


class TestCaseFileReadOnlyCheckResults(unittest.TestCase):
    """Test read-only check results integration in case file."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_incident_with_signal(self, run_id: str) -> str:
        """Create an incident with a signal in the store."""
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Get the stored incident (mutable) and add signal with run_id
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_2,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def test_case_file_includes_read_only_check_results(self) -> None:
        """Case file includes read-only check results when matching artifacts exist."""
        run_id = "run-001"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact
        runner_result: dict[str, object] = {
            "checks_requested": 2,
            "checks_run": 2,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "test log"}
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        self.assertIn("read_only_check_results", case_file)
        results = case_file["read_only_check_results"]  # type: ignore[arg-type]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["run_id"], run_id)

    def test_case_file_empty_without_artifacts(self) -> None:
        """No matching artifacts gives empty section."""
        candidate = make_candidate(name="test-pod-002")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Build case file without writing any artifacts
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        self.assertIn("read_only_check_results", case_file)
        self.assertEqual(case_file["read_only_check_results"], [])

    def test_case_file_includes_run_id_traceability(self) -> None:
        """Case file includes run_id traceability."""
        run_id = "run-003"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact
        runner_result: dict[str, object] = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        results = case_file["read_only_check_results"]  # type: ignore[arg-type]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["run_id"], run_id)

    def test_case_file_includes_check_details(self) -> None:
        """Case file includes check_id/status/summary for each result."""
        run_id = "run-004"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact
        runner_result: dict[str, object] = {
            "checks_requested": 2,
            "checks_run": 2,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "log summary"},
                {"check_id": "pod_events", "status": "completed", "summary": "events summary"},
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        results = case_file["read_only_check_results"]  # type: ignore[arg-type]
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]["results"]), 2)
        self.assertEqual(results[0]["results"][0]["check_id"], "pod_logs")
        self.assertEqual(results[0]["results"][0]["status"], "completed")

    def test_case_file_no_executable_fields(self) -> None:
        """Case file does not include executable fields."""
        run_id = "run-005"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact with action fields
        runner_result: dict[str, object] = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {
                    "check_id": "pod_logs",
                    "status": "completed",
                    "summary": "test",
                    "run": "kubectl exec",
                    "execute": "shell",
                    "action": "delete",
                }
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        results = case_file["read_only_check_results"]  # type: ignore[arg-type]
        self.assertEqual(len(results), 1)
        for result in results[0]["results"]:
            self.assertNotIn("run", result)
            self.assertNotIn("execute", result)
            self.assertNotIn("action", result)

    def test_case_file_remains_read_only(self) -> None:
        """Case file remains read-only."""
        run_id = "run-006"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        self.assertTrue(case_file["read_only"])
        self.assertEqual(case_file["allowed_actions"], [])

    def test_case_file_remains_json_serializable(self) -> None:
        """Case file remains JSON-serializable."""
        run_id = "run-007"
        incident_id = self._create_incident_with_signal(run_id)

        # Write check result artifact
        runner_result: dict[str, object] = {
            "checks_requested": 2,
            "checks_run": 2,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "test"}
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=self._external_dir,
            run_id=run_id,
            incident_id=incident_id,
            runner_result=runner_result,
        )

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        # Should not raise
        json_str = json.dumps(case_file, default=str)
        parsed = json.loads(json_str)
        self.assertIn("read_only_check_results", parsed)

    def test_suggested_checks_still_work(self) -> None:
        """Existing suggested-check behavior still works."""
        candidate = make_candidate(name="test-pod-008")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        # Suggested checks should still be present
        self.assertIn("suggested_checks", case_file)

    def test_prior_analysis_still_work(self) -> None:
        """Existing prior-analysis behavior still works."""
        candidate = make_candidate(name="test-pod-009")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Build case file
        case_file = build_incident_case_file(
            incident_id, external_analysis_dir=self._external_dir
        )

        self.assertIsNotNone(case_file)
        assert case_file is not None
        # Prior analysis should still be present (may be empty if no artifacts)
        self.assertIn("prior_analysis", case_file)
        # Read-only check results should be present
        self.assertIn("read_only_check_results", case_file)
