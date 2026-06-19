"""Tests for diagnosis loop one-pass API validation.

Tests:
1. Missing run_id returns 400
2. Unsafe run_id returns 400
3. Malformed JSON returns 400
4. Missing diagnosis_report returns 400
5. Missing incident returns 404
6. Request body cannot specify external_analysis_dir
7. Request body cannot request remediation/action execution
8. Error responses are bounded and do not include tracebacks
9. Error responses use the project's existing JSON/content-type convention
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.api_incident_diagnosis_loop import (
    DiagnosisLoopOnePassRequest,
)
from k8s_diag_agent.ui.server_incident_diagnosis_loop import (
    handle_incident_diagnosis_loop_one_pass_api,
    match_diagnosis_loop_route,
)


class MockHandler:
    """Mock HTTP request handler for testing."""

    def __init__(
        self,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.path = path
        self.headers = headers or {}
        self._body = body
        self._status_code: int | None = None
        self._response_body: bytes = b""
        self._request_method = ""
        self._request_path = ""
        self._request_query = ""
        self._is_static = False
        self._health_root = Path(tempfile.mkdtemp())

    def _log_access_completion(self) -> None:
        pass

    def _send_text(self, code: int, message: str) -> None:
        self._status_code = code

    def _read_body(self) -> bytes:
        return self._body

    @property
    def rfile(self) -> MagicMock:
        """Mock file-like object for reading request body."""
        mock = MagicMock()
        mock.read = MagicMock(return_value=self._body)
        return mock


class TestDiagnosisLoopRouteMatching(unittest.TestCase):
    """Test route pattern matching."""

    def test_match_diagnosis_loop_route_valid(self) -> None:
        """Valid route returns incident_id."""
        incident_id = match_diagnosis_loop_route(
            "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        )
        self.assertEqual(incident_id, "test-incident-001")

    def test_match_diagnosis_loop_route_no_match(self) -> None:
        """Non-matching route returns None."""
        incident_id = match_diagnosis_loop_route(
            "/api/incidents/snapshot"
        )
        self.assertIsNone(incident_id)


class TestRequestValidation(unittest.TestCase):
    """Test request validation logic."""

    def test_missing_run_id_raises(self) -> None:
        """Missing run_id raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("run_id", str(ctx.exception))

    def test_empty_run_id_raises(self) -> None:
        """Empty run_id raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("run_id", str(ctx.exception))

    def test_unsafe_run_id_raises(self) -> None:
        """Unsafe run_id raises ValueError."""
        # run_id with path traversal characters
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "../../../etc/passwd",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_run_id_with_dots_raises(self) -> None:
        """run_id with .. raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "foo..bar",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            })
        self.assertIn("Unsafe run_id", str(ctx.exception))

    def test_missing_diagnosis_report_raises(self) -> None:
        """Missing diagnosis_report raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001"
            })
        self.assertIn("diagnosis_report", str(ctx.exception))

    def test_missing_diagnosis_raises(self) -> None:
        """Missing diagnosis raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {}
            })
        self.assertIn("diagnosis", str(ctx.exception))

    def test_valid_request_parses(self) -> None:
        """Valid request parses successfully."""
        request = DiagnosisLoopOnePassRequest.from_dict({
            "run_id": "test-run-001",
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
        })
        self.assertEqual(request.run_id, "test-run-001")
        self.assertIn("diagnosis", request.diagnosis_report)

    def test_request_with_external_analysis_dir_raises(self) -> None:
        """Request with external_analysis_dir raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "external_analysis_dir": "/malicious/path"
            })
        self.assertIn("external_analysis_dir", str(ctx.exception))

    def test_request_with_artifact_root_raises(self) -> None:
        """Request with artifact_root raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "artifact_root": "/malicious/path"
            })
        self.assertIn("artifact_root", str(ctx.exception))

    def test_request_with_mutate_raises(self) -> None:
        """Request with mutate field raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "mutate": True
            })
        self.assertIn("mutate", str(ctx.exception))

    def test_request_with_delete_raises(self) -> None:
        """Request with delete field raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                },
                "delete": True
            })
        self.assertIn("delete", str(ctx.exception))

    def test_request_with_too_many_investigations_raises(self) -> None:
        """Request with more than 100 investigations raises ValueError."""
        investigations = [
            {"check_id": f"check-{i}", "title": f"Check {i}", "read_only": True}
            for i in range(101)
        ]
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": investigations
                    }
                }
            })
        self.assertIn("exceeds maximum size", str(ctx.exception))

    def test_request_investigations_not_array_raises(self) -> None:
        """Non-array investigations raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": "not an array"
                    }
                }
            })
        self.assertIn("must be an array", str(ctx.exception))


class TestNonObjectJSONHandling(unittest.TestCase):
    """Test handling of valid JSON that is not an object (e.g., [], null)."""

    def test_non_object_json_raises(self) -> None:
        """Valid JSON array (not object) raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict([])
        self.assertIn("must be a JSON object", str(ctx.exception))

    def test_null_json_raises(self) -> None:
        """Valid JSON null (not object) raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict(None)
        self.assertIn("must be a JSON object", str(ctx.exception))

    def test_string_json_raises(self) -> None:
        """Valid JSON string (not object) raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            DiagnosisLoopOnePassRequest.from_dict("not an object")
        self.assertIn("must be a JSON object", str(ctx.exception))


class TestMalformedJSONHandling(unittest.TestCase):
    """Test handling of malformed JSON in requests."""

    def test_malformed_json_returns_400(self) -> None:
        """Malformed JSON returns 400 response."""
        handler = MockHandler(
            path="/api/incidents/test-incident-001/diagnosis-loop/one-pass",
            headers={"Content-Length": str(len(b"not valid json"))},
            body=b"not valid json",
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_diagnosis_loop_one_pass_api(
                handler,
                "test-incident-001",
            )

            # Verify 400 was returned
            call_args = mock_send.call_args
            self.assertEqual(call_args.kwargs.get("code"), 400)


class TestMissingIncidentHandling(unittest.TestCase):
    """Test handling of missing incident."""

    def test_missing_incident_returns_404(self) -> None:
        """Missing incident returns 404 response."""
        handler = MockHandler(
            path="/api/incidents/nonexistent-incident/diagnosis-loop/one-pass",
            headers={"Content-Length": "100"},
            body=json.dumps({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            }).encode(),
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_diagnosis_loop_one_pass_api(
                handler,
                "nonexistent-incident",
            )

            # Verify 404 was returned
            call_args = mock_send.call_args
            self.assertEqual(call_args.kwargs.get("code"), 404)


class TestErrorResponseBounds(unittest.TestCase):
    """Test that error responses are bounded and safe."""

    def test_error_response_does_not_contain_traceback(self) -> None:
        """Error response does not contain raw traceback."""
        handler = MockHandler(
            path="/api/incidents/test-incident-001/diagnosis-loop/one-pass",
            headers={"Content-Length": "100"},
            body=json.dumps({
                "run_id": "test-run-001",
                "diagnosis_report": {
                    "diagnosis": {
                        "recommended_investigations": []
                    }
                }
            }).encode(),
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_diagnosis_loop_one_pass_api(
                handler,
                "test-incident-001",
            )

            # Get the response body
            response_body = mock_send.call_args.kwargs.get("body", {})
            response_str = json.dumps(response_body)

            # Verify no traceback
            self.assertNotIn("Traceback", response_str)
            self.assertNotIn("traceback", response_str)
            self.assertNotIn("  File ", response_str)

    def test_error_response_uses_json_content_type(self) -> None:
        """Error responses use JSON content type."""
        handler = MockHandler(
            path="/api/incidents/test-incident-001/diagnosis-loop/one-pass",
            headers={"Content-Length": "0"},
            body=b"{}",
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_diagnosis_loop_one_pass_api(
                handler,
                "test-incident-001",
            )

            # send_json_response is called - it sets Content-Type: application/json
            self.assertTrue(mock_send.called)


class TestRequestBodySizeLimit(unittest.TestCase):
    """Test request body size limiting."""

    def test_oversized_body_returns_400(self) -> None:
        """Request body larger than 64KB returns 400."""
        # Create a large body (> 64KB)
        large_body = b"x" * (65 * 1024)

        handler = MockHandler(
            path="/api/incidents/test-incident-001/diagnosis-loop/one-pass",
            headers={"Content-Length": str(len(large_body))},
            body=large_body,
        )

        with patch(
            "k8s_diag_agent.ui.server_incident_diagnosis_loop.send_json_response"
        ) as mock_send:
            handle_incident_diagnosis_loop_one_pass_api(
                handler,
                "test-incident-001",
            )

            # Verify 400 was returned
            call_args = mock_send.call_args
            self.assertEqual(call_args.kwargs.get("code"), 400)


if __name__ == "__main__":
    unittest.main()