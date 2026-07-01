"""Regression tests for backend curl diagnostic wrapper parsing.

These tests verify that the curl helpers correctly parse the diagnostic wrapper
output from the curl pod, extracting only the HTTP response body and not the
DNS resolution diagnostics or curl metadata markers.

Bug: When P0b provider preflight was using _curl_service_pod(), the body
field was set to the entire pod logs output instead of just the HTTP response
body. This caused the provider preflight to report provider_health_invalid_json
even when the backend returned valid JSON with HTTP 200.

The diagnostic wrapper format is:
    RESOLVING_HOST=...
    ... nslookup output ...
    ---CURL_START---
    CURL_EXIT=0
    HTTP_CODE=200
    {actual JSON response body from cat}
    STDERR_BLOCK

Note: The shell script outputs CURL_EXIT and HTTP_CODE BEFORE the response body
(because curl writes the body to a file and we cat it after outputting metadata).
The parser handles this by capturing all non-marker lines after ---CURL_START---.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

import pytest


class TestDiagnosticWrapperBodyExtraction:
    """Tests for extracting body from diagnostic wrapper output."""

    def test_parses_body_from_diagnostic_backend_curl_output(self) -> None:
        """Body should be extracted from after ---CURL_START--- marker only."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod

        # Actual format from shell script:
        # ---CURL_START---
        # CURL_EXIT=...
        # HTTP_CODE=...
        # {response body from cat}
        # STDERR_BLOCK
        # So body comes AFTER the metadata markers.
        raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server: 10.43.0.10
Address: 10.43.0.10#53

Name: k9b-backend.k9b.svc.cluster.local
Address: 10.43.159.44

---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"diagnosis_provider":{"available":true,"phase":"models_list_ok"}}
STDERR_BLOCK
"""

        with self._mock_pod_execution(raw_output):
            result = _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details",
                timeout_seconds=5,
            )

        # Body should be just the JSON, not the diagnostic wrapper
        assert result.http_code == 200
        assert result.curl_rc == 0
        assert result.success is True

        # Body should be valid JSON
        parsed = json.loads(result.body)
        assert parsed["diagnosis_provider"]["available"] is True

    def test_body_does_not_contain_diagnostic_markers(self) -> None:
        """Body should NOT contain RESOLVING_HOST, CURL_EXIT, HTTP_CODE."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod

        raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server: 10.43.0.10
Address: 10.43.0.10#53

---CURL_START---
{"healthy":true}
CURL_EXIT=0
HTTP_CODE=200
"""

        with self._mock_pod_execution(raw_output):
            result = _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health",
                timeout_seconds=5,
            )

        # Body should NOT contain diagnostic markers
        assert "RESOLVING_HOST" not in result.body
        assert "CURL_EXIT" not in result.body
        assert "HTTP_CODE" not in result.body
        assert "Server:" not in result.body
        assert "Address:" not in result.body

    def test_invalid_json_reported_only_for_extracted_body(self) -> None:
        """Invalid JSON error should only apply to extracted body, not wrapper."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod

        # Raw output has valid HTTP 200 but invalid body JSON
        raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
---CURL_START---
not-json
CURL_EXIT=0
HTTP_CODE=200
"""

        with self._mock_pod_execution(raw_output):
            result = _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health",
                timeout_seconds=5,
            )

        # HTTP succeeded
        assert result.http_code == 200
        assert result.curl_rc == 0

        # But body is invalid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.body)

    def test_multiline_json_body_extracted_correctly(self) -> None:
        """Multiline JSON body should be extracted correctly."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod

        multiline_json = """{
  "status": "healthy",
  "dependencies": [
    {"name": "provider", "status": "available"}
  ]
}"""

        raw_output = f"""RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
---CURL_START---
{multiline_json}
CURL_EXIT=0
HTTP_CODE=200
"""

        with self._mock_pod_execution(raw_output):
            result = _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health",
                timeout_seconds=5,
            )

        assert result.http_code == 200
        parsed = json.loads(result.body)
        assert parsed["status"] == "healthy"
        assert len(parsed["dependencies"]) == 1

    def _mock_pod_execution(self, logs_output: str) -> AbstractContextManager[object]:
        """Create mock context for pod execution."""
        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            cmd = args[0] if args else kwargs.get("args", ())
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "apply" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "get" in cmd_str and "pod" in cmd_str:
                return MagicMock(returncode=0, stdout="Succeeded")
            elif "logs" in cmd_str:
                return MagicMock(returncode=0, stdout=logs_output, stderr="")
            elif "delete" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        return patch("subprocess.run", side_effect=run_side_effect)


class TestProviderPreflightDiagnosticWrapperFix:
    """Tests verifying P0b provider preflight works with diagnostic wrapper."""

    def test_provider_preflight_parses_body_from_diagnostic_wrapper(self) -> None:
        """Provider preflight should correctly parse body from diagnostic wrapper."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # This is the exact raw output that was causing provider_health_invalid_json
        raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server: 10.43.0.10
Address: 10.43.0.10#53

Name: k9b-backend.k9b.svc.cluster.local
Address: 10.43.159.44

---CURL_START---
{"healthy":true,"primary_failure_class":"","provider_enabled":true,"dependencies":[{"dependency_name":"diagnosis_provider","status":"available","phase":"models_list_ok"}]}
CURL_EXIT=0
HTTP_CODE=200
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            cmd = args[0] if args else kwargs.get("args", ())
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "apply" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            elif "get" in cmd_str and "pod" in cmd_str:
                return MagicMock(returncode=0, stdout="Succeeded")
            elif "logs" in cmd_str:
                return MagicMock(returncode=0, stdout=raw_output, stderr="")
            elif "delete" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=run_side_effect):
            from pathlib import Path
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should pass now that body is correctly extracted
        assert result.passed is True, f"Expected pass but got: {result.message}"
        assert result.failure_class is None
        assert result.check_method == "service"
        assert result.provider_configured is True


class TestP4cBackendRetryDiagnosticWrapper:
    """Tests for P4c backend retry with diagnostic wrapper output.

    Note: P4c uses curl_backend_exec which uses kubectl exec inside the backend pod.
    This function does NOT produce the diagnostic wrapper format (RESOLVING_HOST, etc.)
    because it's executing directly inside the pod, not via a separate curl pod.

    The P4c bug described in the task was about _curl_service_pod, not curl_backend_exec.
    """

    def test_p4c_incident_fetch_succeeds_with_valid_json_response(self) -> None:
        """P4c incident fetch should succeed with valid JSON from backend."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            fetch_backend_incident_detail_result,
        )

        # curl_backend_exec format: CURL_EXIT, HTTP_CODE, then body
        raw_output = """CURL_EXIT=0
HTTP_CODE=200
{"incident_id":"otel-demo-deployment-shipping-deployment_unavailable","status":"discovered","evidence_count":0,"review_packet":{"status":"pending"},"automatic_diagnosis_loop_summary":{"status":"pending"},"automatic_diagnosis_review":{"available":false}}
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            return MagicMock(returncode=0, stdout=raw_output, stderr="")

        with patch("subprocess.run", side_effect=run_side_effect):
            result = fetch_backend_incident_detail_result(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="otel-demo-deployment-shipping-deployment_unavailable",
                backend_port=8080,
            )

        # Should succeed
        assert result.success is True, f"Expected success but got: {result.error_class}"
        assert result.error_class is None
        assert result.http_status == 200
        assert result.curl_rc == 0

        # Incident should be parsed correctly
        assert result.incident is not None
        assert result.incident.incident_id == "otel-demo-deployment-shipping-deployment_unavailable"

    def test_p4c_incident_fetch_reports_transport_error_correctly(self) -> None:
        """P4c incident fetch should report transport error for connection failures."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            fetch_backend_incident_detail_result,
        )

        # Connection refused format
        raw_output = """CURL_EXIT=7
HTTP_CODE=000
curl: (7) Failed to connect to localhost port 8080: Connection refused
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            return MagicMock(returncode=0, stdout=raw_output, stderr="Connection refused")

        with patch("subprocess.run", side_effect=run_side_effect):
            result = fetch_backend_incident_detail_result(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-incident",
                backend_port=8080,
            )

        # Should report transport error
        assert result.success is False
        assert result.error_class == "backend_incident_fetch_transport_error"
        assert result.http_status == 0
        assert result.curl_rc == 7


class TestCurlExecPodDiagnosticWrapper:
    """Tests for _curl_exec_pod diagnostic wrapper handling."""

    def test_exec_curl_parses_body_correctly(self) -> None:
        """_curl_exec_pod should parse body from CURL_EXIT/HTTP_CODE markers."""
        from scripts.lab_common.provider_curl_helpers import _curl_exec_pod

        # The _curl_exec_pod shell command outputs ---CURL_START--- first,
        # then CURL_EXIT, HTTP_CODE, body, and STDERR_BLOCK
        raw_output = """---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"healthy":true,"version":"1.0.0"}
STDERR_BLOCK
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            return MagicMock(returncode=0, stdout=raw_output, stderr="")

        with patch("subprocess.run", side_effect=run_side_effect):
            result = _curl_exec_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
                container="backend",
                target_url="http://localhost:8080/api/health",
                timeout_seconds=5,
            )

        assert result.http_code == 200
        assert result.curl_rc == 0
        assert result.success is True

        # Body should be valid JSON
        parsed = json.loads(result.body)
        assert parsed["healthy"] is True
        assert parsed["version"] == "1.0.0"
