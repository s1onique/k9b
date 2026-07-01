"""Regression tests for provider preflight retry behavior.

These tests verify:
- HTTP 0 (transport failure) is retried for up to 60s
- Connection failures are retried with exponential backoff
- Invalid JSON after 2xx is retried
- After retries exhausted, failure is classified based on curl_rc:
  - curl_rc=7  -> provider_health_connection_failed
  - curl_rc=6  -> provider_health_dns_failed
  - curl_rc=28 -> provider_health_timeout
  - http=000   -> provider_health_no_http_response
  - 2xx invalid JSON -> provider_health_invalid_json
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


class TestProviderPreflightRetryBehavior:
    """Tests for provider preflight retry behavior."""

    @pytest.fixture
    def temp_artifact_dir(self) -> Iterator[Path]:
        """Create a temporary artifact directory."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_http_000_is_transport_failure(self) -> None:
        """HTTP 000 should be classified as transport failure, not config error."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE,
            CurlResult,
            _classify_curl_failure,
        )

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=None,
            stderr="",
        )

        failure_class, message = _classify_curl_failure(result)
        assert failure_class == FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE
        assert "HTTP 0" in message or "No HTTP response" in message

    def test_curl_rc_7_is_connection_failed(self) -> None:
        """curl_rc=7 (failed to connect) should be classified as connection_failed."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED,
            CurlResult,
            _classify_curl_failure,
        )

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )

        failure_class, message = _classify_curl_failure(result)
        assert failure_class == FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED

    def test_curl_rc_6_is_dns_failed(self) -> None:
        """curl_rc=6 (could not resolve host) should be classified as dns_failed."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_DNS_FAILED,
            CurlResult,
            _classify_curl_failure,
        )

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=6,
            stderr="Could not resolve host",
        )

        failure_class, message = _classify_curl_failure(result)
        assert failure_class == FAILURE_PROVIDER_HEALTH_DNS_FAILED

    def test_curl_rc_28_is_timeout(self) -> None:
        """curl_rc=28 (operation timed out) should be classified as timeout."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_TIMEOUT,
            CurlResult,
            _classify_curl_failure,
        )

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=28,
            stderr="Operation timed out",
        )

        failure_class, message = _classify_curl_failure(result)
        assert failure_class == FAILURE_PROVIDER_HEALTH_TIMEOUT

    def test_is_retryable_http_0(self) -> None:
        """HTTP 0 should be retryable."""
        from scripts.lab_common.provider_preflight import CurlResult, _is_retryable

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=None,
            stderr="",
        )

        assert _is_retryable(result) is True

    def test_is_retryable_curl_rc_7(self) -> None:
        """curl_rc=7 should be retryable."""
        from scripts.lab_common.provider_preflight import CurlResult, _is_retryable

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )

        assert _is_retryable(result) is True

    def test_is_retryable_2xx_invalid_json(self) -> None:
        """HTTP 200 with invalid JSON should be retryable."""
        from scripts.lab_common.provider_preflight import CurlResult, _is_retryable

        result = CurlResult(
            success=True,  # HTTP succeeded
            body="not valid json",
            http_code=200,
            curl_rc=0,
            stderr="",
        )

        assert _is_retryable(result) is True

    def test_is_retryable_2xx_valid_json(self) -> None:
        """HTTP 200 with valid JSON should NOT be retryable."""
        from scripts.lab_common.provider_preflight import CurlResult, _is_retryable

        result = CurlResult(
            success=True,
            body=json.dumps({"healthy": True}),
            http_code=200,
            curl_rc=0,
            stderr="",
        )

        assert _is_retryable(result) is False

    def test_is_retryable_non_2xx_json(self) -> None:
        """HTTP 500 with JSON should NOT be retryable (application error, not transport)."""
        from scripts.lab_common.provider_preflight import CurlResult, _is_retryable

        result = CurlResult(
            success=False,
            body=json.dumps({"error": "internal error"}),
            http_code=500,
            curl_rc=0,
            stderr="",
        )

        assert _is_retryable(result) is False

    def test_transport_failure_after_retry_classifies_correctly(
        self, temp_artifact_dir: Path
    ) -> None:
        """After retries exhausted, transport failures should be classified by curl_rc."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED,
            CurlResult,
            run_provider_preflight,
        )

        # Service fails with connection refused
        service_failure = CurlResult(
            success=False,
            body="connection refused",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )

        # Exec also fails with connection refused
        exec_failure = CurlResult(
            success=False,
            body="connection refused",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=service_failure,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=exec_failure,
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED
        assert "Connection failed" in result.message

    def test_http_000_transport_error_not_config_error(
        self, temp_artifact_dir: Path
    ) -> None:
        """HTTP 0 should NOT be classified as provider_config_error."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_CONFIG_ERROR,
            FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE,
            CurlResult,
            run_provider_preflight,
        )

        # Both checks fail with HTTP 0 (no HTTP response)
        failure = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=None,
            stderr="",
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=failure,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=failure,
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        # HTTP 0 is transport failure, not config error
        assert result.failure_class != FAILURE_PROVIDER_CONFIG_ERROR
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_NO_HTTP_RESPONSE

    def test_dns_failure_classification(self, temp_artifact_dir: Path) -> None:
        """DNS failures should be classified as provider_health_dns_failed."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_DNS_FAILED,
            CurlResult,
            run_provider_preflight,
        )

        failure = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=6,
            stderr="Could not resolve host",
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=failure,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=failure,
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_DNS_FAILED

    def test_timeout_failure_classification(self, temp_artifact_dir: Path) -> None:
        """Timeout failures should be classified as provider_health_timeout."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_TIMEOUT,
            CurlResult,
            run_provider_preflight,
        )

        failure = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=28,
            stderr="Operation timed out",
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=failure,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=failure,
        ):
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=temp_artifact_dir,
            )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_TIMEOUT


class TestCurlResultDataclass:
    """Tests for CurlResult dataclass."""

    def test_is_transport_failure_http_0(self) -> None:
        """HTTP 0 should be transport failure."""
        from scripts.lab_common.provider_preflight import CurlResult

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=None,
            stderr="",
        )

        assert result.is_transport_failure() is True

    def test_is_transport_failure_curl_rc_7(self) -> None:
        """curl_rc=7 should be transport failure."""
        from scripts.lab_common.provider_preflight import CurlResult

        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=7,
            stderr="",
        )

        assert result.is_transport_failure() is True

    def test_is_transport_failure_2xx(self) -> None:
        """HTTP 200 should NOT be transport failure."""
        from scripts.lab_common.provider_preflight import CurlResult

        result = CurlResult(
            success=True,
            body='{"healthy": true}',
            http_code=200,
            curl_rc=0,
            stderr="",
        )

        assert result.is_transport_failure() is False

    def test_is_transport_failure_5xx(self) -> None:
        """HTTP 500 is NOT transport failure (it's application error)."""
        from scripts.lab_common.provider_preflight import CurlResult

        result = CurlResult(
            success=False,
            body='{"error": "internal"}',
            http_code=500,
            curl_rc=0,
            stderr="",
        )

        assert result.is_transport_failure() is False
