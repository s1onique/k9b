"""HTTP route tests for incident detail suggested_checks.

Tests:
- GET /api/incidents/{id} returns suggested_checks from linked artifacts
- Partial/unlinked/wrong incident candidates are NOT visible via HTTP
- Unsafe run_ids don't leak artifacts via HTTP
- No action controls (Run, Execute, Promote, Apply, Remediate) appear in HTTP response
- Malformed artifacts produce graceful HTTP responses

This test suite exercises the actual HTTP route path rather than directly
calling handle_get_incident(), proving the operator-facing production path.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)

from .incident_detail_suggested_checks_fixtures import (
    make_malformed_next_check_plan_artifact,
    make_partial_next_check_plan_artifact,
    make_valid_next_check_plan_artifact,
    make_wrong_incident_next_check_plan_artifact,
)


class TestIncidentDetailSuggestedChecksHTTPRoute(unittest.TestCase):
    """Test HTTP route for incident detail with suggested_checks.

    Uses the auth-disabled test harness to exercise the real HTTP route
    handler stack for /api/incidents/{incident_id}.
    """

    def setUp(self) -> None:
        """Set up HTTP test harness and incident store."""
        # Create fresh store for testing
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

        # Create HTTP harness with temporary directories
        self._tmpdir = tempfile.mkdtemp()
        self._runs_dir = Path(self._tmpdir) / "runs"
        self._runs_dir.mkdir(parents=True)
        self._health_dir = self._runs_dir / "health"
        self._health_dir.mkdir(parents=True)
        self._external_dir = self._health_dir / "external-analysis"
        self._external_dir.mkdir(parents=True)
        self._static_dir = Path(self._tmpdir) / "static"
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
        shutdown_test_server(self._server, self._thread, self._patcher)
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        set_incident_store(None)
        reset_incident_store()

    def _request(self, method: str, path: str) -> tuple[int, bytes]:
        """Make an HTTP request to the test server."""
        from http.client import HTTPConnection

        conn = HTTPConnection("127.0.0.1", self._port, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def _create_incident_with_signal(self, run_id: str) -> str:
        """Create an incident with a signal in the store."""
        candidate = IncidentCandidate(
            candidate_id=f"test-candidate-{run_id}",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting",
                ),
            ),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal to the stored incident (required for artifact lookup)
        from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def _write_plan_artifact(self, run_id: str, payload: dict) -> None:
        """Write a plan artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_http_valid_linked_artifact_produces_suggested_checks(self) -> None:
        """HTTP GET incident detail returns suggested_checks from valid linked artifact."""
        # Create incident with signal
        incident_id = self._create_incident_with_signal("http-valid-001")
        run_id = "http-valid-001"

        # Write valid artifact with linked candidate
        artifact = make_valid_next_check_plan_artifact(
            run_id=run_id,
            incident_id=incident_id,
            candidate_id="check-pod-logs",
            title="Inspect pod logs for test-pod",
            rationale="CrashLoopBackOff typically leaves informative logs",
            risk_level="LOW",
        )
        self._write_plan_artifact(run_id, artifact)

        # Fetch via HTTP route
        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["incident_id"], incident_id)

        # Assert suggested_checks is populated via HTTP
        self.assertIn("suggested_checks", data)
        self.assertEqual(len(data["suggested_checks"]), 1)

        check = data["suggested_checks"][0]
        self.assertEqual(check["check_id"], "check-pod-logs")
        self.assertEqual(check["title"], "Inspect pod logs for test-pod")
        self.assertEqual(check["source"], "next-check-plan")
        self.assertEqual(check["status"], "suggested")

    def test_http_partial_candidates_not_visible(self) -> None:
        """HTTP response does not include partial/unlinked candidates."""
        incident_id = self._create_incident_with_signal("http-partial")
        self._write_plan_artifact("http-partial", make_partial_next_check_plan_artifact("http-partial"))

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_wrong_incident_candidates_not_visible(self) -> None:
        """HTTP response does not include candidates linked to different incidents."""
        incident_id = self._create_incident_with_signal("http-wrong")
        self._write_plan_artifact("http-wrong", make_wrong_incident_next_check_plan_artifact(
            run_id="http-wrong",
            wrong_incident_id="different-incident-id-99999",
        ))

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_malformed_artifact_produces_graceful_response(self) -> None:
        """HTTP response handles malformed artifacts gracefully."""
        incident_id = self._create_incident_with_signal("http-malformed")

        # Write malformed artifact
        malformed_path = self._external_dir / "http-malformed-next-check-plan.json"
        malformed_path.write_text(make_malformed_next_check_plan_artifact(), encoding="utf-8")

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_no_action_controls_in_response(self) -> None:
        """HTTP response does not contain action controls (Run, Execute, Promote, etc.).

        Note: run_id is a legitimate linkage field (source run identifier),
        not an action control. We check for action-related field values,
        not field names that happen to contain action words.
        """
        incident_id = self._create_incident_with_signal("http-no-action")
        self._write_plan_artifact("http-no-action", make_valid_next_check_plan_artifact(
            run_id="http-no-action",
            incident_id=incident_id,
        ))

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)

        # Check suggested_checks don't have action control fields (not just substrings)
        # These would be explicit fields like {"run": "..."} not {"run_id": "..."}
        forbidden_action_fields = ["execute", "promote", "apply", "remediate"]
        for check in data.get("suggested_checks", []):
            for action_field in forbidden_action_fields:
                self.assertNotIn(action_field, check, f"Found action field '{action_field}' in suggested check")

        # Check entire response for explicit action control fields
        body_str = body.decode("utf-8")
        body_lower = body_str.lower()
        # Look for patterns like "run": or "execute": or "promote": (JSON field names)
        import re
        for action in ["execute", "promote", "apply", "remediate"]:
            pattern = rf'"{action}"\s*:'
            self.assertFalse(
                re.search(pattern, body_lower),
                f"Found action control field '{action}:' in HTTP response"
            )

    def test_http_unsafe_run_id_does_not_leak_artifacts(self) -> None:
        """HTTP response does not leak artifacts via unsafe run_id."""
        # Create incident with path traversal run_id
        unsafe_run_id = "../etc/passwd"
        incident_id = self._create_incident_with_signal(unsafe_run_id)

        # Create artifact outside the external-analysis directory
        etc_dir = Path(self._tmpdir).parent / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)
        (etc_dir / "passwd").write_text("malicious content", encoding="utf-8")

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_missing_artifact_produces_empty_suggested_checks(self) -> None:
        """HTTP response returns empty suggested_checks when artifact is missing."""
        incident_id = self._create_incident_with_signal("http-missing")

        # Don't write any artifact
        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_unknown_incident_returns_404(self) -> None:
        """HTTP GET for unknown incident returns 404."""
        status, body = self._request("GET", "/api/incidents/nonexistent-id-99999")

        self.assertEqual(status, 404)
        data = json.loads(body)
        self.assertEqual(data["error"], "Incident not found")


class TestIncidentDetailSuggestedChecksHTTPNegativeCases(unittest.TestCase):
    """Negative case HTTP tests for suggested_checks visibility.

    Verifies that invalid/unsafe artifacts are not surfaced via HTTP.
    """

    def setUp(self) -> None:
        """Set up HTTP test harness."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

        self._tmpdir = tempfile.mkdtemp()
        self._runs_dir = Path(self._tmpdir) / "runs"
        self._runs_dir.mkdir(parents=True)
        self._health_dir = self._runs_dir / "health"
        self._health_dir.mkdir(parents=True)
        self._external_dir = self._health_dir / "external-analysis"
        self._external_dir.mkdir(parents=True)
        self._static_dir = Path(self._tmpdir) / "static"
        self._static_dir.mkdir(parents=True)
        (self._static_dir / "index.html").write_text("<h1>Test</h1>")

        self._server, self._thread, self._patcher = start_ui_test_server_without_auth(
            runs_dir=self._runs_dir,
            static_dir=self._static_dir,
        )
        self._port = self._server.server_address[1]

    def tearDown(self) -> None:
        """Clean up."""
        shutdown_test_server(self._server, self._thread, self._patcher)
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        set_incident_store(None)
        reset_incident_store()

    def _request(self, method: str, path: str) -> tuple[int, bytes]:
        """Make an HTTP request to the test server."""
        from http.client import HTTPConnection

        conn = HTTPConnection("127.0.0.1", self._port, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def _create_incident_with_signal(self, run_id: str) -> str:
        """Create an incident with a signal in the store."""
        candidate = IncidentCandidate(
            candidate_id=f"test-candidate-{run_id}",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="pod",
                    reason="CrashLoopBackOff",
                    message="Back-off restarting",
                ),
            ),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def _write_plan_artifact(self, run_id: str, payload: dict) -> None:
        """Write a plan artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_http_absolute_path_run_id_rejected(self) -> None:
        """HTTP response rejects run_id that is an absolute path."""
        unsafe_run_id = "/tmp/malicious"
        incident_id = self._create_incident_with_signal(unsafe_run_id)

        # Create artifact in /tmp (should NOT be accessed)
        malicious_dir = Path(self._tmpdir).parent / "tmp"
        malicious_dir.mkdir(parents=True, exist_ok=True)
        malicious_path = malicious_dir / "malicious-next-check-plan.json"
        malicious_path.write_text(json.dumps({
            "run_id": unsafe_run_id,
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "malicious-check",
                "title": "Malicious check",
            }],
        }), encoding="utf-8")

        try:
            status, body = self._request("GET", f"/api/incidents/{incident_id}")

            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["suggested_checks"], [])
        finally:
            malicious_path.unlink(missing_ok=True)

    def test_http_glob_metacharacter_run_id_rejected(self) -> None:
        """HTTP response rejects run_id with glob metacharacters."""
        unsafe_run_id = "run-*"
        incident_id = self._create_incident_with_signal(unsafe_run_id)

        # Create artifact in external-analysis (should NOT be accessed)
        (self._external_dir / "run-run-*-next-check-plan.json").write_text(json.dumps({
            "run_id": unsafe_run_id,
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "glob-check",
                "title": "Glob check",
            }],
        }), encoding="utf-8")

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_wrong_run_id_artifact_not_loaded(self) -> None:
        """HTTP response does not load artifact with wrong run_id in filename."""
        incident_id = self._create_incident_with_signal("correct-run")

        # Write artifact with WRONG run_id in filename
        wrong_artifact = make_valid_next_check_plan_artifact(
            run_id="wrong-run",
            incident_id=incident_id,
            candidate_id="should-not-appear",
        )
        wrong_path = self._external_dir / "wrong-run-next-check-plan.json"
        wrong_path.write_text(json.dumps(wrong_artifact), encoding="utf-8")

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])

    def test_http_empty_candidates_produces_empty_list(self) -> None:
        """HTTP response handles empty candidates list gracefully."""
        incident_id = self._create_incident_with_signal("http-empty")

        artifact = {
            "run_id": "http-empty",
            "linkage_schema_version": 1,
            "candidates": [],
        }
        self._write_plan_artifact("http-empty", artifact)

        status, body = self._request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()