"""Regression tests for P4c backend curl_rc preservation.

These tests verify:
- curl_rc is never None when curl actually executed
- curl_rc=6 (DNS) is preserved and classified correctly
- curl_rc=7 (connect) is preserved and classified correctly
- curl_rc=28 (timeout) is preserved and classified correctly
- HTTP 0 is classified as endpoint_not_ready
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest


class TestCurlRcPreservation:
    """Tests for curl_rc preservation in P4c backend fetch."""

    def test_curl_rc_never_none_after_curl_executed(self) -> None:
        """curl_rc should never be None when curl actually executed (only for not-executed case)."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            fetch_backend_incident_detail_result,
        )

        # Test that when curl fails with rc=6, curl_rc is preserved
        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec"
        ) as mock_curl:
            # Mock curl returning DNS resolution failure
            mock_curl.return_value = MagicMock(
                success=False,
                body="",
                http_code=0,
                curl_rc=6,  # DNS resolution failed
                stderr="Could not resolve host",
            )

            result = fetch_backend_incident_detail_result(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

            assert result.success is False
            assert result.curl_rc == 6  # curl_rc is preserved, not None
            assert result.error_detail is not None
            assert "DNS resolution failure" in result.error_detail
            assert "curl_rc=6" in result.error_detail

    def test_curl_rc_preserved_on_connection_refused(self) -> None:
        """curl_rc should be preserved when connection refused."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            fetch_backend_incident_detail_result,
        )

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec"
        ) as mock_curl:
            mock_curl.return_value = MagicMock(
                success=False,
                body="",
                http_code=0,
                curl_rc=7,  # Connection refused
                stderr="Connection refused",
            )

            result = fetch_backend_incident_detail_result(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

            assert result.success is False
            assert result.curl_rc == 7  # curl_rc is preserved
            assert result.error_detail is not None
            assert "endpoint/connect failure" in result.error_detail
            assert "curl_rc=7" in result.error_detail

    def test_curl_rc_preserved_on_timeout(self) -> None:
        """curl_rc should be preserved when timeout occurs."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            fetch_backend_incident_detail_result,
        )

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.curl_backend_exec"
        ) as mock_curl:
            mock_curl.return_value = MagicMock(
                success=False,
                body="",
                http_code=0,
                curl_rc=28,  # Timeout
                stderr="Connection timed out",
            )

            result = fetch_backend_incident_detail_result(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

            assert result.success is False
            assert result.curl_rc == 28  # curl_rc is preserved
            assert result.error_detail is not None
            assert "timeout" in result.error_detail.lower()
            assert "curl_rc=28" in result.error_detail


class TestCurlRcClassification:
    """Tests for curl_rc classification in P4c backend retry."""

    @pytest.fixture
    def temp_artifact_dir(self) -> Iterator[Path]:
        """Create a temporary artifact directory."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_classify_dns_failure_after_retries(self) -> None:
        """After retries exhausted, DNS failure (curl_rc=6) should be classified as dns_resolution_failed."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        # All attempts fail with DNS resolution error
        dns_fail_result = MagicMock()
        dns_fail_result.success = False
        dns_fail_result.error_class = "backend_incident_fetch_transport_error"
        dns_fail_result.http_status = 0
        dns_fail_result.curl_rc = 6  # DNS resolution failed
        dns_fail_result.url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/incidents/test"
        dns_fail_result.api_path = "/api/incidents/test"
        dns_fail_result.encoded_incident_id = "test"
        dns_fail_result.body_prefix = ""
        dns_fail_result.stderr_prefix = "Could not resolve host"

        # Reduce deadline for faster test
        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=dns_fail_result,
        ), patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry.P4C_BACKEND_RETRY_DEADLINE_SECONDS",
            1,  # 1 second deadline for faster test
        ):
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_DNS_RESOLUTION_FAILED

    def test_classify_endpoint_not_ready_after_retries(self) -> None:
        """After retries exhausted, connection refused (curl_rc=7) should be classified as endpoint_not_ready."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_ENDPOINT_NOT_READY,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        # All attempts fail with connection refused
        conn_fail_result = MagicMock()
        conn_fail_result.success = False
        conn_fail_result.error_class = "backend_incident_fetch_transport_error"
        conn_fail_result.http_status = 0
        conn_fail_result.curl_rc = 7  # Connection refused
        conn_fail_result.url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/incidents/test"
        conn_fail_result.api_path = "/api/incidents/test"
        conn_fail_result.encoded_incident_id = "test"
        conn_fail_result.body_prefix = "Connection refused"
        conn_fail_result.stderr_prefix = "Connection refused"

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=conn_fail_result,
        ), patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry.P4C_BACKEND_RETRY_DEADLINE_SECONDS",
            1,
        ):
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_ENDPOINT_NOT_READY

    def test_classify_http_0_as_endpoint_not_ready(self) -> None:
        """HTTP 0 (no response) should be classified as endpoint_not_ready after retries."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_ENDPOINT_NOT_READY,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        # HTTP 0 indicates service not reachable
        http_0_result = MagicMock()
        http_0_result.success = False
        http_0_result.error_class = "backend_incident_fetch_transport_error"
        http_0_result.http_status = 0
        http_0_result.curl_rc = 7  # Connection refused (curl_rc=7 for HTTP 0 with connection failure)
        http_0_result.url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/incidents/test"
        http_0_result.api_path = "/api/incidents/test"
        http_0_result.encoded_incident_id = "test"
        http_0_result.body_prefix = ""
        http_0_result.stderr_prefix = ""

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=http_0_result,
        ), patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry.P4C_BACKEND_RETRY_DEADLINE_SECONDS",
            1,
        ):
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_ENDPOINT_NOT_READY
