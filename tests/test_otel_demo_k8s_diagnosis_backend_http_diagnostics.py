"""Unit tests for backend HTTP - Diagnostics and error classification tests.

Tests polling behavior, backend error handling, malformed/empty response behavior,
and HTTP contract edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    fetch_backend_incident_detail_result,
    invoke_targeted_automatic_diagnosis_loop,
)


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


class TestFetchBackendIncidentDetailDiagnostics:
    """Tests for fetch_backend_incident_detail_result error classification."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_transport_error_classification(self, mock_curl: MagicMock) -> None:
        """Test transport error (http_code=0) is classified as TRANSPORT_ERROR."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=7,
            stderr="Connection refused",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR
        assert result.http_status == 0
        assert result.curl_rc == 7
        assert result.incident is None
        assert "Transport error" in (result.error_detail or "")

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_curl_rc_nonzero_is_transport_error(self, mock_curl: MagicMock) -> None:
        """Test nonzero curl_rc is classified as TRANSPORT_ERROR."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=0,
            body="",
            curl_rc=6,  # DNS resolution failed
            stderr="Could not resolve host",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_404_not_found_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP 404 is classified as NOT_FOUND."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=404,
            body='{"error": "incident not found"}',
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-nonexistent",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND
        assert result.http_status == 404
        assert result.incident is None

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_http_500_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP 500 is classified as HTTP_ERROR."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=500,
            body="Internal Server Error",
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR
        assert result.http_status == 500
        assert "HTTP error" in (result.error_detail or "")

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_http_200_with_html_body_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP 200 with HTML body is classified as INVALID_JSON."""
        html_body = "<!doctype html><html><body>Login Page</body></html>"
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body=html_body,
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON
        assert result.http_status == 200
        assert result.body_prefix == html_body[:200]
        assert result.json_error is not None

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_http_200_with_json_array_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP 200 with JSON array (not object) is classified as CONTRACT_ERROR."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body="[1, 2, 3]",
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR
        assert result.http_status == 200

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_http_200_with_json_string_classification(self, mock_curl: MagicMock) -> None:
        """Test HTTP 200 with JSON string (not object) is classified as CONTRACT_ERROR."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body='"just a string"',
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_CONTRACT_ERROR
        assert result.http_status == 200
