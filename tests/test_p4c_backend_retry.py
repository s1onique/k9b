"""Regression tests for P4c backend retry behavior.

These tests verify:
- fetch_backend_incident_detail_with_retry() retries transient failures
- Exponential backoff is applied correctly
- After retries exhausted, failures are classified based on curl_rc:
  - curl_rc=6  -> backend_dns_resolution_failed
  - curl_rc=7  -> backend_endpoint_not_ready
  - curl_rc=28 -> backend_incident_fetch_transport_error
  - http=000   -> backend_endpoint_not_ready
- curl_rc is never None when curl actually executed
- 404 not found is NOT retried
- HTTP errors are NOT retried
- Contract errors are NOT retried

Split into modules:
- test_p4c_backend_retry_constants.py: Constants tests
- test_p4c_backend_retry_curl_rc.py: curl_rc preservation tests
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
        fail_result.curl_rc = 7  # Connection refused

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


class TestNamespaceQualifiedURLs:
    """Tests for namespace-qualified backend URL construction.

    Ensures P4c uses namespace-qualified Kubernetes Service DNS,
    consistent with P0c backend connectivity preflight.
    """

    def test_build_backend_url_uses_namespace_qualified_service(self) -> None:
        """Backend URL should use namespace-qualified Kubernetes Service DNS."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            _build_backend_url,
        )

        url, api_path, encoded_id = _build_backend_url(
            namespace="k9b",
            incident_id="test-incident-123",
            backend_port=8080,
        )

        # Should use namespace-qualified Service DNS
        assert "k9b-backend.k9b.svc.cluster.local" in url
        assert ":8080" in url
        assert api_path == "/api/incidents/test-incident-123"
        assert encoded_id == "test-incident-123"

    def test_build_backend_url_with_different_namespace(self) -> None:
        """Backend URL should work with different namespaces."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            _build_backend_url,
        )

        url, _, _ = _build_backend_url(
            namespace="custom-namespace",
            incident_id="incident-456",
            backend_port=9090,
        )

        assert "k9b-backend.custom-namespace.svc.cluster.local:9090" in url

    def test_build_backend_url_encodes_special_chars(self) -> None:
        """Backend URL should URL-encode incident IDs with special characters."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            _build_backend_url,
        )

        url, api_path, encoded_id = _build_backend_url(
            namespace="k9b",
            incident_id="incident/with/slashes",
            backend_port=8080,
        )

        # Slashes should be encoded
        assert "%2F" in encoded_id or "/" not in encoded_id
        assert "incident%2Fwith%2Fslashes" in url or encoded_id == "incident%2Fwith%2Fslashes"

    def test_build_targeted_diagnosis_url(self) -> None:
        """Targeted diagnosis URL should use namespace-qualified Service DNS."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            _build_targeted_diagnosis_url,
        )

        url, api_path = _build_targeted_diagnosis_url(
            namespace="k9b",
            incident_id="diag-incident-789",
            backend_port=8080,
        )

        assert "k9b-backend.k9b.svc.cluster.local" in url
        assert "/automatic-diagnosis-loop/one-pass" in api_path
        assert "diag-incident-789" in api_path or "diag-incident-789" in url

    def test_p4c_and_p0c_use_same_namespace_qualified_service(self) -> None:
        """P4c and P0c should use the same namespace-qualified Service DNS pattern."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
            _build_backend_url,
        )

        # P0c pattern from k9b_otel_demo_lab_backend_connectivity.py:
        # backend_url = f"http://{backend_service}.{namespace}.svc.cluster.local:{backend_port}/api/incidents"
        # Where backend_service = K9B_BACKEND_SERVICE = "k9b-backend"

        namespace = "k9b"
        backend_port = 8080
        service = "k9b-backend"

        # P0c expected pattern
        p0c_expected = f"http://{service}.{namespace}.svc.cluster.local:{backend_port}/api/incidents"

        # P4c actual pattern
        url, _, _ = _build_backend_url(namespace, "test-id", backend_port)

        # Extract the host:port portion
        p4c_host_port = url.replace("http://", "").split("/")[0]
        p0c_host_port = p0c_expected.replace("http://", "").split("/")[0]

        assert p4c_host_port == p0c_host_port, (
            f"P4c and P0c should use same namespace-qualified Service DNS: "
            f"P4c={p4c_host_port}, P0c={p0c_host_port}"
        )
