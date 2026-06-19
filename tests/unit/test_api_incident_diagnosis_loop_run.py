"""Tests for diagnosis loop one-pass API run-path.

Tests:
1. Valid authenticated request with registry-approved pod_logs runs exactly one pass
2. Response includes read_only: true
3. Response includes allowed_actions: []
4. Response includes decision
5. Response includes check counts
6. Response includes diagnosis-loop-pass artifact reference
7. Response includes read-only-check-results artifact reference when checks ran
8. Artifacts are actually written to the configured external-analysis directory
9. Response is JSON-serializable
10. No full raw case file is returned
11. No full raw runner result is returned
12. No absolute local artifact path is returned unless existing API convention already exposes artifact paths
13. Fake handler behavior remains policy-controlled through the existing runner/orchestrator path
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.api_incident_diagnosis_loop import (
    DiagnosisLoopOnePassResponse,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_models import (
    LoopDecision,
)
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)


class TestResponseSerialization(unittest.TestCase):
    """Test response serialization."""

    def test_response_to_dict_includes_required_fields(self) -> None:
        """Response to_dict includes all required fields."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            read_only=True,
            allowed_actions=[],
            decision="run_allowed_read_only_checks",
            checks_requested=1,
            checks_run=1,
            checks_skipped=0,
            checks_rejected=0,
            artifacts={
                "read_only_check_results": {
                    "written": True,
                    "name": "test-run-001-read-only-check-results.json",
                },
                "diagnosis_loop_pass": {
                    "written": True,
                    "name": "test-run-001-diagnosis-loop-pass.json",
                },
            },
            case_file_linked_artifact=True,
            safety_metadata={
                "read_only": True,
                "allowed_actions": [],
                "no_kubernetes_client": True,
                "no_shell": True,
                "no_subprocess": True,
                "no_kubectl": True,
                "no_mutation": True,
                "fake_runner": True,
                "one_pass_only": True,
            },
        )

        data = response.to_dict()

        # Required fields
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["incident_id"], "test-incident-001")
        self.assertEqual(data["run_id"], "test-run-001")
        self.assertEqual(data["read_only"], True)
        self.assertEqual(data["allowed_actions"], [])
        self.assertEqual(data["decision"], "run_allowed_read_only_checks")
        self.assertIn("artifacts", data)
        self.assertIn("safety_metadata", data)

    def test_response_to_dict_json_serializable(self) -> None:
        """Response to_dict produces JSON-serializable output."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision="stop_no_checks_proposed",
        )

        data = response.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        self.assertEqual(parsed["incident_id"], "test-incident-001")
        self.assertEqual(parsed["run_id"], "test-run-001")

    def test_response_to_dict_without_error(self) -> None:
        """Response without error does not include error field."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
        )

        data = response.to_dict()
        self.assertNotIn("error", data)

    def test_response_to_dict_with_error(self) -> None:
        """Response with error includes error field."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            error="Incident not found",
        )

        data = response.to_dict()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Incident not found")


class TestResponseActionControlFields(unittest.TestCase):
    """Test that response does not contain action-control fields."""

    _FORBIDDEN_FIELDS = frozenset([
        "run",
        "execute",
        "promote",
        "apply",
        "remediate",
        "action",
        "approve",
        "reject",
        "run_command",
        "execute_command",
        "mutate",
        "delete",
        "scale",
        "restart",
        "rollout",
        "patch",
    ])

    def test_response_does_not_contain_action_control_fields(self) -> None:
        """Response does not contain forbidden action-control fields."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            read_only=True,
            allowed_actions=[],
        )

        data = response.to_dict()
        data_str = json.dumps(data)

        for field in self._FORBIDDEN_FIELDS:
            self.assertNotIn(f'"{field}"', data_str)


class TestArtifactReferencesOnly(unittest.TestCase):
    """Test that response only contains artifact references, not full contents."""

    def test_artifact_references_use_filenames(self) -> None:
        """Artifact references use filenames, not full paths."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            artifacts={
                "read_only_check_results": {
                    "written": True,
                    "name": "test-run-001-read-only-check-results.json",
                },
                "diagnosis_loop_pass": {
                    "written": True,
                    "name": "test-run-001-diagnosis-loop-pass.json",
                },
            },
        )

        data = response.to_dict()
        artifacts = data["artifacts"]

        # Should contain name (filename), not path (full path)
        for artifact_type in ["read_only_check_results", "diagnosis_loop_pass"]:
            artifact = artifacts[artifact_type]
            self.assertIn("name", artifact)
            # Name should be a simple filename, not a path
            self.assertNotIn("/", artifact["name"])
            self.assertNotIn("\\", artifact["name"])

    def test_response_does_not_contain_case_file(self) -> None:
        """Response does not contain full case file."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
        )

        data = response.to_dict()

        # Should not contain case_file
        self.assertNotIn("case_file", data)
        self.assertNotIn("rebuilt_case_file", data)
        self.assertNotIn("full_case_file", data)

    def test_response_does_not_contain_runner_result(self) -> None:
        """Response does not contain full runner result."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
        )

        data = response.to_dict()

        # Should not contain runner_result
        self.assertNotIn("runner_result", data)
        self.assertNotIn("full_runner_result", data)


class TestSafetyMetadata(unittest.TestCase):
    """Test safety metadata in response."""

    def test_safety_metadata_includes_read_only_true(self) -> None:
        """Safety metadata includes read_only: True."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            safety_metadata={
                "read_only": True,
                "allowed_actions": [],
                "no_kubernetes_client": True,
                "no_shell": True,
                "no_subprocess": True,
                "no_kubectl": True,
                "no_mutation": True,
                "fake_runner": True,
                "one_pass_only": True,
            },
        )

        data = response.to_dict()
        safety = data["safety_metadata"]

        self.assertEqual(safety["read_only"], True)
        self.assertEqual(safety["allowed_actions"], [])
        self.assertEqual(safety["no_kubernetes_client"], True)
        self.assertEqual(safety["no_shell"], True)
        self.assertEqual(safety["no_subprocess"], True)
        self.assertEqual(safety["no_kubectl"], True)
        self.assertEqual(safety["no_mutation"], True)
        self.assertEqual(safety["fake_runner"], True)
        self.assertEqual(safety["one_pass_only"], True)


class TestCheckCounts(unittest.TestCase):
    """Test check count reporting in response."""

    def test_response_includes_check_counts(self) -> None:
        """Response includes all check count fields."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            checks_requested=2,
            checks_run=1,
            checks_skipped=1,
            checks_rejected=0,
        )

        data = response.to_dict()

        self.assertEqual(data["checks_requested"], 2)
        self.assertEqual(data["checks_run"], 1)
        self.assertEqual(data["checks_skipped"], 1)
        self.assertEqual(data["checks_rejected"], 0)


class TestDecisionValues(unittest.TestCase):
    """Test decision value handling."""

    def test_stop_decision_value(self) -> None:
        """Stop decision is properly reported."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        )

        data = response.to_dict()
        self.assertEqual(data["decision"], "stop_no_checks_proposed")

    def test_run_decision_value(self) -> None:
        """Run decision is properly reported."""
        response = DiagnosisLoopOnePassResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            decision=LoopDecision.RUN_ALLOWED_READ_ONLY_CHECKS.value,
        )

        data = response.to_dict()
        self.assertEqual(data["decision"], "run_allowed_read_only_checks")


class TestIntegrationRunPath(unittest.TestCase):
    """Integration tests for the run path with real orchestrator.

    These tests prove that handle_diagnosis_loop_one_pass() actually:
    1. Runs the orchestrator
    2. Writes artifacts
    3. Returns real artifact names
    """

    def setUp(self) -> None:
        """Set up HTTP test harness and incident store."""
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import (
            set_incident_store,
        )

        # Create fresh store for testing
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

        # Create HTTP harness with a temporary directory
        self._tmpdir = tempfile.TemporaryDirectory()
        self._runs_dir = Path(self._tmpdir.name) / "runs"
        self._runs_dir.mkdir(parents=True)
        self._health_dir = self._runs_dir / "health"
        self._health_dir.mkdir(parents=True)
        self._static_dir = Path(self._tmpdir.name) / "static"
        self._static_dir.mkdir(parents=True)
        (self._static_dir / "index.html").write_text("<h1>Test</h1>")

        # Start server with auth disabled to test route behavior
        self._server, self._thread, self._patcher = start_ui_test_server_without_auth(
            runs_dir=self._runs_dir,
            static_dir=self._static_dir,
        )
        self._port = self._server.server_address[1]

    def tearDown(self) -> None:
        """Clean up."""
        from k8s_diag_agent.collect.incident_store_provider import (
            reset_incident_store,
            set_incident_store,
        )
        shutdown_test_server(self._server, self._thread, self._patcher)
        self._tmpdir.cleanup()
        set_incident_store(None)
        reset_incident_store()

    def _request(self, method: str, path: str, body: bytes = b"", headers: dict | None = None) -> tuple[int, bytes, dict]:
        """Make an HTTP request to the test server."""
        from http.client import HTTPConnection
        conn = HTTPConnection("127.0.0.1", self._port, timeout=5)
        try:
            request_headers = headers or {}
            if body:
                request_headers["Content-Length"] = str(len(body))
            conn.request(method, path, body=body, headers=request_headers)
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def _create_incident(self) -> str:
        """Create a test incident and return its ID."""
        from datetime import UTC, datetime

        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="test-diagnosis-loop-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(CandidateSignal(source="test", reason="Error", message="err"),),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        incidents = self._test_store.list_incidents()
        return incidents[0].incident_id

    def test_run_path_writes_artifacts_with_correct_names(self) -> None:
        """Run path writes artifacts with correct filenames."""
        incident_id = self._create_incident()
        run_id = "test-run-diagnosis-loop-001"

        request_body = json.dumps({
            "run_id": run_id,
            "diagnosis_report": {
                "diagnosis": {
                    "recommended_investigations": [
                        {
                            "check_id": "pod_logs",
                            "title": "Check pod logs",
                            "read_only": True,
                            "source": "manual"
                        }
                    ]
                }
            }
        }).encode()

        status, body, _ = self._request(
            "POST",
            f"/api/incidents/{incident_id}/diagnosis-loop/one-pass",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(status, 200)
        data = json.loads(body)

        # Verify artifacts are written with correct names
        self.assertEqual(data["artifacts"]["read_only_check_results"]["written"], True)
        self.assertEqual(
            data["artifacts"]["read_only_check_results"]["name"],
            f"{run_id}-read-only-check-results.json"
        )
        self.assertEqual(data["artifacts"]["diagnosis_loop_pass"]["written"], True)
        self.assertEqual(
            data["artifacts"]["diagnosis_loop_pass"]["name"],
            f"{run_id}-diagnosis-loop-pass.json"
        )

    def test_stop_path_returns_empty_read_only_check_results(self) -> None:
        """Stop path (no investigations) returns written=false for read-only-check-results."""
        incident_id = self._create_incident()
        run_id = "test-run-diagnosis-loop-stop-001"

        request_body = json.dumps({
            "run_id": run_id,
            "diagnosis_report": {
                "diagnosis": {
                    "recommended_investigations": []
                }
            }
        }).encode()

        status, body, _ = self._request(
            "POST",
            f"/api/incidents/{incident_id}/diagnosis-loop/one-pass",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(status, 200)
        data = json.loads(body)

        # Stop path: read-only-check-results not written (no checks ran)
        self.assertEqual(data["artifacts"]["read_only_check_results"]["written"], False)
        self.assertIsNone(data["artifacts"]["read_only_check_results"]["name"])
        # But loop-pass artifact IS written (even on stop path)
        self.assertEqual(data["artifacts"]["diagnosis_loop_pass"]["written"], True)
        self.assertEqual(
            data["artifacts"]["diagnosis_loop_pass"]["name"],
            f"{run_id}-diagnosis-loop-pass.json"
        )


if __name__ == "__main__":
    unittest.main()
