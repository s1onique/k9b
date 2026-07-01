"""Unit tests for backend HTTP - Incident fetching tests.

Tests incident list/detail HTTP and snapshot/review-packet HTTP tests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    fetch_backend_incident_detail,
    fetch_backend_incident_detail_result,
)


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


class TestFetchBackendIncidentDetailResult:
    """Tests for fetch_backend_incident_detail_result with precise error classification."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_successful_fetch_returns_incident(self, mock_curl: MagicMock) -> None:
        """Test successful fetch returns incident detail."""
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

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        assert result.success is True
        assert result.incident is not None
        assert result.incident.incident_id == "inc-123"
        assert result.error_class is None
        assert result.http_status == 200
        assert result.curl_rc == 0

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_result_contains_diagnostic_metadata(self, mock_curl: MagicMock) -> None:
        """Test result contains URL, path, encoded ID, and other metadata."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body=json.dumps({
                "status": "collecting_evidence",
                "evidence_count": 5,
            }),
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="test-inc-123",
        )

        assert result.api_path == "/api/incidents/test-inc-123"
        assert result.encoded_incident_id == "test-inc-123"
        assert "localhost" in result.url

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_to_dict_contains_failure_fields_on_error(self, mock_curl: MagicMock) -> None:
        """Test to_dict includes error fields when fetch fails."""
        mock_curl.return_value = MagicMock(
            success=False,
            http_code=404,
            body='{"error": "not found"}',
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        d = result.to_dict()
        assert d["success"] is False
        assert d["http_status"] == 404
        assert "body_prefix" in d
        assert "error_detail" in d

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec")
    def test_to_dict_compact_on_success(self, mock_curl: MagicMock) -> None:
        """Test to_dict is compact on success (no error fields)."""
        mock_curl.return_value = MagicMock(
            success=True,
            http_code=200,
            body=json.dumps({
                "status": "collecting_evidence",
                "evidence_count": 5,
            }),
            curl_rc=0,
            stderr="",
        )

        result = fetch_backend_incident_detail_result(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
        )

        d = result.to_dict()
        assert d["success"] is True
        assert "error_class" not in d
        assert "body_prefix" not in d
        assert "error_detail" not in d

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
