"""Unit tests for backend HTTP - Runtime/status tests.

Tests runtime status endpoint, debug diagnostics enabled/disabled,
and execution state diagnostics download tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    curl_backend_exec,
)


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
