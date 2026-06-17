"""HTTP route tests for read-only incident API.

Tests:
- GET /api/incidents returns {"incidents": [...], "total": N}
- GET /api/incidents?status=open filters correctly
- GET /api/incidents/{incident_id} returns incident dict
- GET /api/incidents/{unknown} returns 404 {"error": "Incident not found"}
- handler does not require current run context
- malformed/internal errors do not leak raw exception strings
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from ..security.server_http_test_support import HTTPServerTestHarness


class TestIncidentReadRoutes(unittest.TestCase):
    """Test HTTP routes for incident read API."""

    def setUp(self) -> None:
        """Set up HTTP test harness and incident store."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        # Create fresh store for testing
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

        # Create HTTP harness with a temporary directory
        self._tmpdir = TemporaryDirectory()
        self._runs_dir = Path(self._tmpdir.name) / "runs"
        self._runs_dir.mkdir(parents=True)
        self._health_dir = self._runs_dir / "health"
        self._health_dir.mkdir(parents=True)
        self._static_dir = Path(self._tmpdir.name) / "static"
        self._static_dir.mkdir(parents=True)
        (self._static_dir / "index.html").write_text("<h1>Test</h1>")

        self._harness = HTTPServerTestHarness(
            runs_dir=self._runs_dir,
            static_dir=self._static_dir,
        )
        self._port = self._harness.start()

    def tearDown(self) -> None:
        """Clean up."""
        self._harness.stop()
        self._tmpdir.cleanup()
        set_incident_store(None)
        reset_incident_store()

    def test_get_incidents_list_returns_incidents_and_total(self) -> None:
        """GET /api/incidents returns incidents list and total."""
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        # Add an incident to the store
        candidate = IncidentCandidate(
            candidate_id="test-candidate-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(
                CandidateSignal(
                    source="test",
                    reason="CrashLoopBackOff",
                    message="Back-off",
                ),
            ),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        status, body, _ = self._harness.request("GET", "/api/incidents")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("incidents", data)
        self.assertIn("total", data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["incidents"]), 1)

    def test_get_incidents_empty_store_returns_empty_list(self) -> None:
        """GET /api/incidents returns empty list when store is empty."""
        status, body, _ = self._harness.request("GET", "/api/incidents")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["incidents"], [])
        self.assertEqual(data["total"], 0)

    def test_get_incidents_with_status_filter(self) -> None:
        """GET /api/incidents?status=open filters correctly."""
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        # Add two incidents
        for name in ["pod-1", "pod-2"]:
            candidate = IncidentCandidate(
                candidate_id=f"test-{name}",
                namespace="default",
                object_kind=ObjectKind.POD,
                object_name=name,
                candidate_class=CandidateClass.CRASH_LOOP,
                severity=Severity.ERROR,
                signals=(CandidateSignal(source="test", reason="Error", message="err"),),
                evidence_needed=(),
            )
            self._test_store.promote_candidates(
                [candidate],
                datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            )

        # Suppress one
        incidents = self._test_store.list_incidents()
        self._test_store.suppress(incidents[0].incident_id, "known issue")

        # Filter by open
        status, body, _ = self._harness.request("GET", "/api/incidents?status=open")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["total"], 1)

        # Filter by suppressed
        status, body, _ = self._harness.request("GET", "/api/incidents?status=suppressed")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["total"], 1)

        # Filter by investigating (none)
        status, body, _ = self._harness.request("GET", "/api/incidents?status=investigating")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["total"], 0)

    def test_get_incident_detail_returns_incident(self) -> None:
        """GET /api/incidents/{id} returns incident dict."""
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="test-detail-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="detail-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(CandidateSignal(source="test", reason="CrashLoop", message="back-off"),),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        status, body, _ = self._harness.request("GET", f"/api/incidents/{incident_id}")

        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["incident_id"], incident_id)
        self.assertEqual(data["namespace"], "default")
        self.assertEqual(data["object_name"], "detail-pod")

    def test_get_incident_unknown_returns_404(self) -> None:
        """GET /api/incidents/{unknown} returns 404 with error envelope."""
        status, body, _ = self._harness.request("GET", "/api/incidents/nonexistent-id-12345")

        self.assertEqual(status, 404)
        data = json.loads(body)
        self.assertEqual(data["error"], "Incident not found")

    def test_no_post_route_for_incidents_list(self) -> None:
        """Verify no POST endpoint exists for /api/incidents."""
        status, body, _ = self._harness.request(
            "POST",
            "/api/incidents",
            headers={"Content-Type": "application/json"},
        )

        # Should return 404 (not found) or 405 (method not allowed) or 501 (not implemented)
        self.assertIn(status, [404, 405, 501])


class TestIncidentRouteSecurity(unittest.TestCase):
    """Test security properties of incident routes."""

    def setUp(self) -> None:
        """Set up HTTP test harness."""
        from k8s_diag_agent.collect.incident_store import IncidentStore

        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

        self._tmpdir = TemporaryDirectory()
        self._runs_dir = Path(self._tmpdir.name) / "runs"
        self._runs_dir.mkdir(parents=True)
        self._static_dir = Path(self._tmpdir.name) / "static"
        self._static_dir.mkdir(parents=True)
        (self._static_dir / "index.html").write_text("<h1>Test</h1>")

        self._harness = HTTPServerTestHarness(
            runs_dir=self._runs_dir,
            static_dir=self._static_dir,
        )
        self._port = self._harness.start()

    def tearDown(self) -> None:
        """Clean up."""
        self._harness.stop()
        self._tmpdir.cleanup()
        set_incident_store(None)
        reset_incident_store()

    def test_error_response_does_not_leak_exception(self) -> None:
        """Internal errors must not leak raw exception strings."""
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="test-sec-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="sec-pod",
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
        incident_id = incidents[0].incident_id

        # Inject an exception that would leak sensitive info
        with patch(
            "k8s_diag_agent.collect.api_incident_reads.get_incident_store",
            side_effect=RuntimeError("SECRET_TOKEN=abc123 INTERNAL_ERROR"),
        ):
            status, body, _ = self._harness.request("GET", f"/api/incidents/{incident_id}")

        # Should return 500 with generic error
        self.assertEqual(status, 500)
        data = json.loads(body)
        self.assertEqual(data["error"], "Failed to get incident")
        # Ensure no raw exception in response
        body_str = body.decode("utf-8")
        self.assertNotIn("SECRET_TOKEN", body_str)
        self.assertNotIn("INTERNAL_ERROR", body_str)

    def test_response_contains_no_remediation_fields(self) -> None:
        """Response must not contain remediation-related fields."""
        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="test-fields-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="fields-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(CandidateSignal(source="test", reason="Error", message="err"),),
            evidence_needed=(),
        )
        self._test_store.promote_candidates(
            [candidate],
            datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        # Test list endpoint
        status, body, _ = self._harness.request("GET", "/api/incidents")
        self.assertEqual(status, 200)
        data = json.loads(body)

        forbidden = ["remediate", "fix", "apply", "execute", "action", "mutate", "kubectl"]
        for incident in data["incidents"]:
            for field in incident.keys():
                field_lower = field.lower()
                for forb in forbidden:
                    self.assertNotIn(
                        forb,
                        field_lower,
                        f"Found forbidden field: {field}",
                    )


if __name__ == "__main__":
    unittest.main()
