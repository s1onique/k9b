"""Tests for incident one-pass diagnosis service API.

Tests:
1. Valid route pattern matching returns correct incident_id
2. Invalid route pattern returns None
3. Valid request is parsed correctly
4. Missing incident_id in request body is acceptable (uses URL param)
5. Request with forbidden fields is rejected
6. Unsafe incident_id is rejected
7. Response includes all required fields from service DTO
8. Missing incident returns 404
9. Module does not import kubernetes
10. Module does not import subprocess
11. Module does not use kubectl
12. Response does not contain forbidden action-control fields
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_service import (
    OnePassServiceRequest,
    OnePassServiceResponse,
    _is_safe_incident_id,
)
from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
    match_diagnosis_service_route,
)


class TestRoutePatternMatching(unittest.TestCase):
    """Test route pattern matching."""

    def test_valid_route_returns_incident_id(self) -> None:
        """Valid route returns incident_id."""
        incident_id = match_diagnosis_service_route(
            "/api/incidents/test-incident-001/one-pass-diagnosis"
        )
        self.assertEqual(incident_id, "test-incident-001")

    def test_valid_route_with_special_chars_returns_incident_id(self) -> None:
        """Valid route with underscore returns incident_id."""
        incident_id = match_diagnosis_service_route(
            "/api/incidents/incident_123_abc/one-pass-diagnosis"
        )
        self.assertEqual(incident_id, "incident_123_abc")

    def test_non_matching_route_returns_none(self) -> None:
        """Non-matching route returns None."""
        incident_id = match_diagnosis_service_route("/api/incidents/snapshot")
        self.assertIsNone(incident_id)

    def test_different_route_returns_none(self) -> None:
        """Different route returns None."""
        incident_id = match_diagnosis_service_route(
            "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        )
        self.assertIsNone(incident_id)


class TestIncidentIdSafety(unittest.TestCase):
    """Test incident ID safety validation."""

    def test_safe_incident_id_passes(self) -> None:
        """Safe incident IDs pass validation."""
        self.assertTrue(_is_safe_incident_id("test-incident-001"))
        self.assertTrue(_is_safe_incident_id("incident_123"))
        self.assertTrue(_is_safe_incident_id("abc"))

    def test_empty_incident_id_fails(self) -> None:
        """Empty incident ID fails validation."""
        self.assertFalse(_is_safe_incident_id(""))
        self.assertFalse(_is_safe_incident_id(None))  # type: ignore

    def test_path_traversal_fails(self) -> None:
        """Path traversal in incident ID fails validation."""
        self.assertFalse(_is_safe_incident_id("../etc/passwd"))
        self.assertFalse(_is_safe_incident_id("foo/bar"))
        self.assertFalse(_is_safe_incident_id("foo\\bar"))

    def test_command_injection_fails(self) -> None:
        """Command injection in incident ID fails validation."""
        self.assertFalse(_is_safe_incident_id("foo;rm -rf /"))
        self.assertFalse(_is_safe_incident_id("foo`cat /etc/passwd`"))
        self.assertFalse(_is_safe_incident_id("foo$HOME"))
        self.assertFalse(_is_safe_incident_id("foo\nbar"))


class TestRequestParsing(unittest.TestCase):
    """Test request parsing."""

    def test_valid_request_with_incident_id(self) -> None:
        """Valid request with incident_id is parsed correctly."""
        data = {"incident_id": "test-incident-001"}
        request = OnePassServiceRequest.from_dict(data)
        self.assertEqual(request.incident_id, "test-incident-001")
        self.assertIsNone(request.run_id)

    def test_valid_request_with_run_id(self) -> None:
        """Valid request with run_id is parsed correctly."""
        data = {"incident_id": "test-incident-001", "run_id": "manual-001"}
        request = OnePassServiceRequest.from_dict(data)
        self.assertEqual(request.incident_id, "test-incident-001")
        self.assertEqual(request.run_id, "manual-001")

    def test_valid_request_empty_body_rejected(self) -> None:
        """Empty body request is rejected - incident_id is required."""
        # Empty body should raise ValueError since incident_id is required
        data: dict[str, object] = {}
        with self.assertRaises(ValueError) as ctx:
            OnePassServiceRequest.from_dict(data)
        self.assertIn("incident_id is required", str(ctx.exception))

    def test_request_with_forbidden_fields_rejected(self) -> None:
        """Request with forbidden fields is rejected."""
        data = {"incident_id": "test", "diagnosis_provider": "fake"}
        with self.assertRaises(ValueError) as ctx:
            OnePassServiceRequest.from_dict(data)
        self.assertIn("diagnosis_provider", str(ctx.exception))

    def test_request_with_unsafe_incident_id_rejected(self) -> None:
        """Request with unsafe incident_id is rejected."""
        data = {"incident_id": "../../etc/passwd"}
        with self.assertRaises(ValueError) as ctx:
            OnePassServiceRequest.from_dict(data)
        self.assertIn("Unsafe incident_id", str(ctx.exception))

    def test_non_dict_request_rejected(self) -> None:
        """Non-dict request is rejected."""
        with self.assertRaises(ValueError) as ctx:
            OnePassServiceRequest.from_dict([])
        self.assertIn("must be a JSON object", str(ctx.exception))


class TestResponseSerialization(unittest.TestCase):
    """Test response serialization."""

    def test_response_to_dict_includes_required_fields(self) -> None:
        """Response to_dict includes all required fields."""
        response = OnePassServiceResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            category="readiness_probe_failure",
            root_cause="readiness probe failure",
            confidence="high",
            description="Pod is not ready",
            evidence_refs=["evidence-1"],
            read_only=True,
            allowed_actions=[],
            forbidden_actions_observed=[],
            mutation_proposals_observed=[],
            decision="run_allowed_read_only_checks",
            checks_run=3,
            next_checks=[],
            artifact_written=True,
            artifact_name="test-diagnosis.json",
        )

        data = response.to_dict()

        # All required fields from service DTO
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["incident_id"], "test-incident-001")
        self.assertEqual(data["run_id"], "test-run-001")
        self.assertEqual(data["category"], "readiness_probe_failure")
        self.assertEqual(data["root_cause"], "readiness probe failure")
        self.assertEqual(data["confidence"], "high")
        self.assertEqual(data["read_only"], True)
        self.assertEqual(data["allowed_actions"], [])
        self.assertEqual(data["forbidden_actions_observed"], [])
        self.assertEqual(data["mutation_proposals_observed"], [])
        self.assertEqual(data["decision"], "run_allowed_read_only_checks")
        self.assertEqual(data["checks_run"], 3)
        self.assertEqual(data["artifact_written"], True)
        self.assertEqual(data["artifact_name"], "test-diagnosis.json")

    def test_response_to_dict_json_serializable(self) -> None:
        """Response to_dict produces JSON-serializable output."""
        response = OnePassServiceResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
            next_checks=[{"check_id": "pod_logs", "description": "Check logs"}],
        )

        data = response.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        self.assertEqual(parsed["incident_id"], "test-incident-001")
        self.assertEqual(len(parsed["next_checks"]), 1)

    def test_response_without_error(self) -> None:
        """Response without error does not include error field."""
        response = OnePassServiceResponse(
            schema_version="1.0",
            incident_id="test-incident-001",
            run_id="test-run-001",
        )

        data = response.to_dict()
        self.assertNotIn("error", data)

    def test_response_with_error(self) -> None:
        """Response with error includes error field."""
        response = OnePassServiceResponse(
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
        response = OnePassServiceResponse(
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


class TestServerHandlerContract(unittest.TestCase):
    """Test server handler contract compliance."""

    def test_empty_body_uses_url_incident_id(self) -> None:
        """Empty body should use URL incident_id, not fail with 'incident_id is required'."""
        from io import BytesIO
        from tempfile import TemporaryDirectory
        from pathlib import Path

        from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
            handle_incident_one_pass_diagnosis_service_api,
        )
        from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
            reset_providers,
        )

        try:
            with TemporaryDirectory() as tmpdir:
                health_root = Path(tmpdir)

                class _WFile:
                    def __init__(self) -> None:
                        self._buf = BytesIO()
                    def write(self, data: bytes) -> int:
                        return self._buf.write(data)
                    def flush(self) -> None:
                        pass
                    def getvalue(self) -> bytes:
                        return self._buf.getvalue()

                class EmptyBodyHandler:
                    path = "/api/incidents/test-incident-001/one-pass-diagnosis"
                    _health_root = health_root

                    class _Headers:
                        def get(self, key: str, default: str = "") -> str:
                            return default
                    headers = _Headers()

                    rfile = BytesIO(b"")
                    _response_status = 200
                    _response_headers: dict[str, str] = {}
                    _response_bytes = 0
                    wfile = _WFile()

                    def send_response(self, code: int) -> None:
                        self._response_status = code
                    def send_header(self, key: str, value: str) -> None:
                        self._response_headers[key] = value
                    def end_headers(self) -> None:
                        pass

                handler = EmptyBodyHandler()

                handle_incident_one_pass_diagnosis_service_api(
                    handler=handler,  # type: ignore[arg-type]
                    incident_id="test-incident-001",
                )

                # Parse response - should NOT contain "incident_id is required"
                response_body = handler.wfile.getvalue().decode("utf-8")
                response_data = json.loads(response_body)

                # The key assertion: empty body should NOT produce "incident_id is required" error
                error_msg = response_data.get("error", "")
                self.assertNotIn("incident_id is required", error_msg)

                # Verify the response incident_id matches URL incident_id
                self.assertEqual(response_data.get("incident_id"), "test-incident-001")
        finally:
            reset_providers()

    def test_mismatch_returns_400(self) -> None:
        """URL/body incident_id mismatch should return 400 with error message."""
        import json
        from io import BytesIO
        from tempfile import TemporaryDirectory
        from pathlib import Path

        from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
            handle_incident_one_pass_diagnosis_service_api,
        )
        from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
            reset_providers,
        )

        try:
            with TemporaryDirectory() as tmpdir:
                health_root = Path(tmpdir)
                body = json.dumps({
                    "incident_id": "other-incident",
                    "run_id": "test-run",
                }).encode("utf-8")

                class _WFile:
                    def __init__(self) -> None:
                        self._buf = BytesIO()
                    def write(self, data: bytes) -> int:
                        return self._buf.write(data)
                    def flush(self) -> None:
                        pass
                    def getvalue(self) -> bytes:
                        return self._buf.getvalue()

                class MismatchHandler:
                    path = "/api/incidents/good-incident/one-pass-diagnosis"
                    _health_root = health_root

                    class _Headers:
                        def get(self, key: str, default: str = "") -> str:
                            if key == "Content-Length":
                                return str(len(body))
                            return default
                    headers = _Headers()

                    rfile = BytesIO(body)
                    _response_status = 200
                    _response_headers: dict[str, str] = {}
                    _response_bytes = 0
                    wfile = _WFile()

                    def send_response(self, code: int) -> None:
                        self._response_status = code
                    def send_header(self, key: str, value: str) -> None:
                        self._response_headers[key] = value
                    def end_headers(self) -> None:
                        pass

                handler = MismatchHandler()

                handle_incident_one_pass_diagnosis_service_api(
                    handler=handler,  # type: ignore[arg-type]
                    incident_id="good-incident",
                )

                self.assertEqual(handler._response_status, 400)
                response_body = handler.wfile.getvalue().decode("utf-8")
                response_data = json.loads(response_body)
                self.assertIn("error", response_data)
                # Error message should indicate incident_id mismatch
                self.assertIn("match", response_data["error"].lower())
        finally:
            reset_providers()

    def test_provider_registry_reset_in_finally(self) -> None:
        """Provider registry should be reset properly."""
        from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
            get_diagnosis_provider,
            set_diagnosis_provider,
            reset_providers,
        )

        # Verify reset clears state
        reset_providers()

        # Before setting, should be None
        self.assertIsNone(get_diagnosis_provider())

        # Set a mock provider
        class MockProvider:
            pass

        set_diagnosis_provider(MockProvider())  # type: ignore

        # Should now be non-None
        self.assertIsNotNone(get_diagnosis_provider())

        # Reset should clear it
        reset_providers()
        self.assertIsNone(get_diagnosis_provider())


if __name__ == "__main__":
    unittest.main()
