"""Unit tests for k9b_otel_demo_lab_k8s_diagnosis_backend_http.py.

These tests validate the HTTP helpers for backend-targeted diagnosis.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    curl_backend_exec,
    fetch_backend_incident_detail,
    invoke_targeted_automatic_diagnosis_loop,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
)


# =============================================================================
# Test curl_backend_exec
# =============================================================================


class TestCurlBackendExec:
    """Tests for curl_backend_exec with mocked kubectl."""

    @patch("subprocess.run")
    def test_successful_get(self, mock_run: MagicMock) -> None:
        """Test successful GET request."""
        mock_run.return_value = MagicMock(
            stdout="HTTP_CODE=200\n{\"id\": \"inc-123\", \"status\": \"ok\"}\n",
            stderr="",
            returncode=0,
        )

        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-123",
        )

        assert result.http_code == 200
        assert "inc-123" in result.body
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "kubectl" in call_args
        assert "--kubeconfig" in call_args

    @patch("subprocess.run")
    def test_transport_error(self, mock_run: MagicMock) -> None:
        """Test transport error (curl rc != 0)."""
        mock_run.return_value = MagicMock(
            stdout="CURL_EXIT=7\nHTTP_CODE=0\n",
            stderr="Could not resolve host",
            returncode=1,
        )

        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-123",
        )

        assert result.http_code == 0
        assert result.curl_rc == 7
        assert result.success is False

    @patch("subprocess.run")
    def test_http_error(self, mock_run: MagicMock) -> None:
        """Test HTTP error (non-2xx)."""
        mock_run.return_value = MagicMock(
            stdout="HTTP_CODE=404\n{\"error\": \"not found\"}\n",
            stderr="",
            returncode=0,
        )

        result = curl_backend_exec(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            target_url="http://localhost:8080/api/incidents/inc-missing",
        )

        assert result.http_code == 404
        assert result.success is False


# =============================================================================
# Test invoke_targeted_diagnosis_loop
# =============================================================================


class TestInvokeTargetedDiagnosisLoop:
    """Tests for invoke_targeted_diagnosis_loop."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_successful_invocation(self, mock_curl: MagicMock) -> None:
        """Test successful one-pass invocation."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body='{"status": "diagnosis_pass_completed", "pass_number": 1}',
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is True
        assert result.http_status == 200
        assert result.json_parsed is True
        assert "pass_number" in result.response_data
        assert result.error_class is None

        # Verify POST was used and NEW endpoint is called (not fake-runner)
        call_kwargs = mock_curl.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert "automatic-diagnosis-loop/one-pass" in call_kwargs["target_url"]

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_http_error_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=500,
            body="Internal Server Error",
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR
        assert "500" in (result.error_detail or "")

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_transport_error_classification(self, mock_curl: MagicMock) -> None:
        """Test transport error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=7,
            stderr="Could not resolve host",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_invalid_json_classification(self, mock_curl: MagicMock) -> None:
        """Test JSON parse error is properly classified."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body="not valid json {",
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_TARGETED_INVOCATION_INVALID_JSON

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_incident_not_found(self, mock_curl: MagicMock) -> None:
        """Test incident not found (404)."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=404,
            body='{"error": "incident not found"}',
            curl_rc=0,
            stderr="",
        )

        result = invoke_targeted_automatic_diagnosis_loop(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-nonexistent",
        )

        assert result.success is False
        assert result.http_status == 404
        assert result.error_class == FAILURE_TARGETED_INVOCATION_HTTP_ERROR


# =============================================================================
# Test fetch_backend_incident_detail
# =============================================================================


class TestFetchBackendIncidentDetail:
    """Tests for fetch_backend_incident_detail."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_successful_fetch(self, mock_curl: MagicMock) -> None:
        """Test successful incident fetch."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body=json.dumps({
                "status": "collecting_evidence",
                "evidence_count": 5,
                "review_packet": {"status": "ready"},
            }),
            curl_rc=0,
            stderr="",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is not None
        assert detail.incident_id == "inc-123"
        assert detail.status == "collecting_evidence"
        assert detail.evidence_count == 5

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_transport_failure_returns_none(self, mock_curl: MagicMock) -> None:
        """Test transport failure returns None."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=7,
            stderr="Connection refused",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is None

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_invalid_json_returns_none(self, mock_curl: MagicMock) -> None:
        """Test invalid JSON returns None."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body="not json",
            curl_rc=0,
            stderr="",
        )

        detail = fetch_backend_incident_detail(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert detail is None
