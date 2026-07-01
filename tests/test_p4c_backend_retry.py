"""Regression tests for P4c backend retry behavior.

These tests verify:
- fetch_backend_incident_detail_with_retry() retries transient failures
- Exponential backoff is applied correctly
- After retries exhausted, failures are classified based on curl_rc:
  - curl_rc=6  -> backend_dns_resolution_failed
  - curl_rc=7  -> backend_endpoint_not_ready
  - curl_rc=28 -> backend_incident_fetch_transport_error
  - http=000   -> backend_endpoint_not_ready
- 404 not found is NOT retried
- HTTP errors are NOT retried
- Contract errors are NOT retried
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest


class TestBackendRetryBehavior:
    """Tests for P4c backend incident fetch retry behavior."""

    @pytest.fixture
    def temp_artifact_dir(self) -> Iterator[Path]:
        """Create a temporary artifact directory."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_success_on_first_attempt(self) -> None:
        """Successful fetch should return immediately without retry."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.incident = MagicMock()
        mock_result.incident.incident_id = "test-123"

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=mock_result,
        ) as mock_fetch:
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is True
        mock_fetch.assert_called_once()  # Only called once

    def test_retry_on_transport_failure(self) -> None:
        """HTTP 0 (transport failure) should be retried."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        # First two calls fail, third succeeds
        fail_result = MagicMock()
        fail_result.success = False
        fail_result.error_class = "backend_incident_fetch_transport_error"
        fail_result.http_status = 0
        fail_result.curl_rc = None

        success_result = MagicMock()
        success_result.success = True
        success_result.incident = MagicMock()
        success_result.incident.incident_id = "test-123"

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            side_effect=[fail_result, fail_result, success_result],
        ), patch("time.sleep") as mock_sleep:
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is True
        # Should have retried twice before success
        mock_sleep.assert_called()

    def test_no_retry_on_404(self) -> None:
        """404 not found should NOT be retried."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        not_found_result = MagicMock()
        not_found_result.success = False
        not_found_result.error_class = FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND
        not_found_result.http_status = 404
        not_found_result.curl_rc = 0

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=not_found_result,
        ), patch("time.sleep") as mock_sleep:
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="nonexistent",
            )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND
        mock_sleep.assert_not_called()  # No retry

    def test_no_retry_on_http_error(self) -> None:
        """HTTP 500 should NOT be retried."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        http_error_result = MagicMock()
        http_error_result.success = False
        http_error_result.error_class = FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR
        http_error_result.http_status = 500
        http_error_result.curl_rc = 0

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            return_value=http_error_result,
        ), patch("time.sleep") as mock_sleep:
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is False
        assert result.error_class == FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR
        mock_sleep.assert_not_called()  # No retry

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
        dns_fail_result.url = "http://localhost:8080/api/incidents/test"
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
        conn_fail_result.url = "http://localhost:8080/api/incidents/test"
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
        http_0_result.curl_rc = None  # No curl error, just no HTTP response
        http_0_result.url = "http://localhost:8080/api/incidents/test"
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

    def test_retry_on_invalid_json(self) -> None:
        """Invalid JSON should be retried (service may not be fully ready)."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_retry import (
            fetch_backend_incident_detail_with_retry,
        )

        # First call returns invalid JSON, second succeeds
        invalid_json_result = MagicMock()
        invalid_json_result.success = False
        invalid_json_result.error_class = "backend_incident_fetch_invalid_json"
        invalid_json_result.http_status = 200
        invalid_json_result.curl_rc = 0

        success_result = MagicMock()
        success_result.success = True
        success_result.incident = MagicMock()
        success_result.incident.incident_id = "test-123"

        with patch(
            "scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http.fetch_backend_incident_detail_result",
            side_effect=[invalid_json_result, success_result],
        ), patch("time.sleep") as mock_sleep:
            result = fetch_backend_incident_detail_with_retry(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                incident_id="test-123",
            )

        assert result.success is True
        mock_sleep.assert_called()  # Should have retried


class TestBackendRetryConstants:
    """Tests for P4c backend retry constants."""

    def test_retry_constants_exist(self) -> None:
        """P4c backend retry constants should be defined."""
        from scripts.lab_common.constants import (
            P4C_BACKEND_RETRY_DEADLINE_SECONDS,
            P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS,
            P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS,
        )

        assert P4C_BACKEND_RETRY_DEADLINE_SECONDS == 60
        assert P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS == 0.25
        assert P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS == 8

    def test_exponential_backoff_sequence(self) -> None:
        """Verify exponential backoff sequence matches requirements."""
        from scripts.lab_common.constants import (
            P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS,
            P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS,
        )

        # Expected backoff sequence: 0.25, 0.5, 1.0, 2.0, 4.0, 8.0
        backoff_sequence = []
        current = float(P4C_BACKEND_RETRY_INITIAL_SLEEP_SECONDS)
        max_sleep = float(P4C_BACKEND_RETRY_MAX_SLEEP_SECONDS)

        while current <= max_sleep * 2:  # Generate a few iterations
            backoff_sequence.append(current)
            current = min(current * 2, max_sleep)
            if current >= max_sleep:
                break

        expected_sequence = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        assert backoff_sequence == expected_sequence[:len(backoff_sequence)]


class TestBackendFailureConstants:
    """Tests for backend failure constants."""

    def test_dns_resolution_failed_constant(self) -> None:
        """FAILURE_BACKEND_DNS_RESOLUTION_FAILED should be defined."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_DNS_RESOLUTION_FAILED,
        )

        assert FAILURE_BACKEND_DNS_RESOLUTION_FAILED == "backend_dns_resolution_failed"

    def test_endpoint_not_ready_constant(self) -> None:
        """FAILURE_BACKEND_ENDPOINT_NOT_READY should be defined."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_BACKEND_ENDPOINT_NOT_READY,
        )

        assert FAILURE_BACKEND_ENDPOINT_NOT_READY == "backend_endpoint_not_ready"
