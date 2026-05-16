"""Unit tests for vmalert HTTP client module.

Tests cover:
- fetch_vmalert_rules() - happy path and error handling
- fetch_vmalert_alerts() - happy path and error handling
- VmalertFetchResult properties
- Error status mapping (HTTPError, URLError, TimeoutError)
- Invalid JSON handling
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_client import (
    DEFAULT_TIMEOUT_SECONDS,
    VmalertFetchResult,
    VmalertFetchStatus,
    fetch_vmalert_alerts,
    fetch_vmalert_rules,
)


def _make_mock_response(body_bytes: bytes) -> MagicMock:
    """Create a mock response that works as a context manager."""
    mock_response = MagicMock()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_response.read.return_value = body_bytes
    return mock_response


# --- Test Fixtures ---


@pytest.fixture
def valid_rules_response() -> dict[str, Any]:
    """Valid vmalert /api/v1/rules response."""
    return {
        "status": "success",
        "data": {
            "groups": [
                {
                    "name": "test-group",
                    "file": "/etc/vmalert/rules.yaml",
                    "interval": "30s",
                    "rules": [
                        {
                            "name": "TestAlert",
                            "type": "alerting",
                            "health": "ok",
                            "alerts": [
                                {
                                    "state": "firing",
                                    "labels": {
                                        "alertname": "TestAlert",
                                        "severity": "critical",
                                    },
                                }
                            ],
                        },
                    ],
                }
            ]
        },
    }


@pytest.fixture
def valid_alerts_response() -> dict[str, Any]:
    """Valid vmalert /api/v1/alerts response."""
    return {
        "status": "success",
        "data": {
            "alerts": [
                {
                    "state": "firing",
                    "labels": {
                        "alertname": "HighMemoryUsage",
                        "severity": "warning",
                    },
                    "annotations": {
                        "summary": "High memory usage detected",
                        "description": "Memory usage above threshold",
                    },
                },
                {
                    "state": "pending",
                    "labels": {
                        "alertname": "DiskSpaceLow",
                        "severity": "warning",
                    },
                },
            ]
        },
    }


# --- fetch_vmalert_rules Tests ---


class TestFetchVmalertRules:
    """Tests for fetch_vmalert_rules()."""

    def test_returns_ok_on_valid_json(self, valid_rules_response: dict[str, Any]) -> None:
        """fetch_vmalert_rules() returns OK status on valid JSON response."""
        mock_response = _make_mock_response(json.dumps(valid_rules_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.OK
        assert result.raw_response is not None
        assert result.raw_response["status"] == "success"
        assert result.captured_at is not None

    def test_returns_ok_empty_groups(self) -> None:
        """fetch_vmalert_rules() returns OK for empty groups response."""
        response = {"status": "success", "data": {"groups": []}}
        mock_response = _make_mock_response(json.dumps(response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.OK
        assert result.raw_response is not None

    def test_returns_upstream_error_on_vmalert_error(self) -> None:
        """fetch_vmalert_rules() returns UPSTREAM_ERROR on vmalert error response."""
        response = {"status": "error", "error": "some vmalert error"}
        mock_response = _make_mock_response(json.dumps(response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.UPSTREAM_ERROR
        assert result.error is not None
        assert "some vmalert error" in result.error

    def test_returns_invalid_response_on_malformed_json(self) -> None:
        """fetch_vmalert_rules() returns INVALID_RESPONSE on malformed JSON."""
        mock_response = _make_mock_response(b"not valid json{")

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.INVALID_RESPONSE
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_returns_upstream_error_on_http_error(self) -> None:
        """fetch_vmalert_rules() returns UPSTREAM_ERROR on HTTPError."""
        import urllib.error

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://vmalert.test:8080/api/v1/rules",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            ),
        ):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.UPSTREAM_ERROR
        assert result.error is not None
        assert "500" in result.error

    def test_returns_fetch_error_on_url_error(self) -> None:
        """fetch_vmalert_rules() returns FETCH_ERROR on URLError."""
        import urllib.error

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.FETCH_ERROR
        assert result.error is not None
        assert "Connection failed" in result.error

    def test_returns_timeout_on_timeout(self) -> None:
        """fetch_vmalert_rules() returns TIMEOUT on TimeoutError."""
        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", side_effect=TimeoutError()):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.TIMEOUT
        assert result.error == "Request timed out"

    def test_includes_fetch_duration(self, valid_rules_response: dict[str, Any]) -> None:
        """fetch_vmalert_rules() includes fetch_duration_ms in result."""
        mock_response = _make_mock_response(json.dumps(valid_rules_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_rules("http://vmalert.test:8080")

        assert result.fetch_duration_ms is not None
        assert result.fetch_duration_ms >= 0

    def test_uses_custom_timeout(self, valid_rules_response: dict[str, Any]) -> None:
        """fetch_vmalert_rules() respects custom timeout parameter."""
        mock_response = _make_mock_response(json.dumps(valid_rules_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            fetch_vmalert_rules("http://vmalert.test:8080", timeout=10.0)

            # Check the timeout was passed
            mock_urlopen.assert_called_once()
            call_kwargs = mock_urlopen.call_args[1]
            assert call_kwargs.get("timeout") == 10.0

    def test_endpoint_trailing_slash_normalized(self, valid_rules_response: dict[str, Any]) -> None:
        """fetch_vmalert_rules() normalizes endpoint with trailing slash."""
        mock_response = _make_mock_response(json.dumps(valid_rules_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            fetch_vmalert_rules("http://vmalert.test:8080/")

            # Check the URL was constructed correctly
            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args[0]
            request = call_args[0]
            assert request.full_url == "http://vmalert.test:8080/api/v1/rules"


# --- fetch_vmalert_alerts Tests ---


class TestFetchVmalertAlerts:
    """Tests for fetch_vmalert_alerts()."""

    def test_returns_ok_on_valid_json(self, valid_alerts_response: dict[str, Any]) -> None:
        """fetch_vmalert_alerts() returns OK status on valid JSON response."""
        mock_response = _make_mock_response(json.dumps(valid_alerts_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.OK
        assert result.raw_response is not None
        assert result.raw_response["status"] == "success"

    def test_returns_empty_on_empty_alerts(self) -> None:
        """fetch_vmalert_alerts() returns OK for empty alerts array."""
        response = {"status": "success", "data": {"alerts": []}}
        mock_response = _make_mock_response(json.dumps(response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.OK
        assert result.raw_response is not None

    def test_returns_upstream_error_on_vmalert_error(self) -> None:
        """fetch_vmalert_alerts() returns UPSTREAM_ERROR on vmalert error response."""
        response = {"status": "error", "error": "Alert query failed"}
        mock_response = _make_mock_response(json.dumps(response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.UPSTREAM_ERROR

    def test_returns_invalid_response_on_malformed_json(self) -> None:
        """fetch_vmalert_alerts() returns INVALID_RESPONSE on malformed JSON."""
        mock_response = _make_mock_response(b"invalid json")

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.INVALID_RESPONSE

    def test_returns_upstream_error_on_http_404(self) -> None:
        """fetch_vmalert_alerts() returns UPSTREAM_ERROR on HTTPError 404."""
        import urllib.error

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="http://vmalert.test:8080/api/v1/alerts",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None,
            ),
        ):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.UPSTREAM_ERROR
        assert "404" in result.error

    def test_returns_fetch_error_on_connection_refused(self) -> None:
        """fetch_vmalert_alerts() returns FETCH_ERROR on connection refused."""
        import urllib.error

        with patch(
            "k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.FETCH_ERROR
        assert "Connection failed" in result.error

    def test_returns_timeout_on_timeout(self) -> None:
        """fetch_vmalert_alerts() returns TIMEOUT on TimeoutError."""
        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", side_effect=TimeoutError()):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.status == VmalertFetchStatus.TIMEOUT

    def test_includes_source_endpoint(self, valid_alerts_response: dict[str, Any]) -> None:
        """fetch_vmalert_alerts() includes source_endpoint in result."""
        mock_response = _make_mock_response(json.dumps(valid_alerts_response).encode("utf-8"))

        with patch("k8s_diag_agent.external_analysis.vmalert_client.urllib.request.urlopen", return_value=mock_response):
            result = fetch_vmalert_alerts("http://vmalert.test:8080")

        assert result.source_endpoint == "http://vmalert.test:8080"


# --- VmalertFetchResult Tests ---


class TestVmalertFetchResult:
    """Tests for VmalertFetchResult properties and methods."""

    def test_is_ok_true_for_ok_status(self) -> None:
        """VmalertFetchResult.is_ok returns True for OK status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.OK,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
        )
        assert result.is_ok is True

    def test_is_ok_true_for_empty_status(self) -> None:
        """VmalertFetchResult.is_ok returns True for EMPTY status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.EMPTY,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
        )
        assert result.is_ok is True

    def test_is_ok_false_for_timeout(self) -> None:
        """VmalertFetchResult.is_ok returns False for TIMEOUT status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.TIMEOUT,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
            error="Request timed out",
        )
        assert result.is_ok is False

    def test_is_ok_false_for_upstream_error(self) -> None:
        """VmalertFetchResult.is_ok returns False for UPSTREAM_ERROR status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.UPSTREAM_ERROR,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
            error="HTTP 500",
        )
        assert result.is_ok is False

    def test_is_ok_false_for_fetch_error(self) -> None:
        """VmalertFetchResult.is_ok returns False for FETCH_ERROR status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.FETCH_ERROR,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
            error="Connection failed",
        )
        assert result.is_ok is False

    def test_is_ok_false_for_invalid_response(self) -> None:
        """VmalertFetchResult.is_ok returns False for INVALID_RESPONSE status."""
        result = VmalertFetchResult(
            status=VmalertFetchStatus.INVALID_RESPONSE,
            source_endpoint="http://test:8080",
            captured_at="2024-01-01T00:00:00Z",
            error="Invalid JSON",
        )
        assert result.is_ok is False


# --- Default Timeout Test ---


def test_default_timeout_is_5_seconds() -> None:
    """DEFAULT_TIMEOUT_SECONDS should be 5.0."""
    assert DEFAULT_TIMEOUT_SECONDS == 5.0