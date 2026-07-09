"""Tests for SchedulerClient.list_incidents() method.

These tests are in a separate file to keep test file sizes manageable
for llm-friendly code review.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

from k8s_diag_agent.ui.server_incident_internal_client import (
    SchedulerClient,
    create_scheduler_client,
)


class MockHTTPError(urllib.error.HTTPError):
    """Mock HTTP error for testing - inherits from urllib.error.HTTPError."""

    def __init__(self, code: int, message: str, body: str = ""):
        from email.message import Message

        super().__init__(
            url="http://localhost",
            code=code,
            msg=message,
            hdrs=Message(),
            fp=None,
        )
        self._body = body
        self._body_bytes = body.encode("utf-8") if body else b""

    def read(self, n: int | None = None) -> bytes:
        if n is None:
            return self._body_bytes
        return self._body_bytes[:n]


class TestSchedulerClientListIncidents:
    """Test list_incidents method uses canonical /api/internal/incidents endpoint."""

    def test_list_incidents_uses_canonical_endpoint(self) -> None:
        """list_incidents should call /api/internal/incidents (canonical path)."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "incidents": [],
                "total": 0,
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            client.list_incidents()

            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert "/api/internal/incidents" in request.full_url
            assert "/api/internal/incidents/list" not in request.full_url

    def test_list_incidents_with_status_filter(self) -> None:
        """list_incidents should include status filter in query params."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "incidents": [],
                "total": 0,
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            client.list_incidents(status="open")

            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert "status=open" in request.full_url

    def test_list_incidents_with_limit(self) -> None:
        """list_incidents should include limit in query params."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "incidents": [],
                "total": 0,
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            client.list_incidents(limit=10)

            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert "limit=10" in request.full_url

    def test_list_incidents_401_returns_structured_error(self) -> None:
        """401 unauthorized should return structured error with error_type=unauthorized."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="bad-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                401,
                "Unauthorized",
                body=json.dumps({"message": "Authentication required"}),
            )

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "unauthorized"
        assert result["status_code"] == 401
        assert result["incidents"] == []
        assert result["total"] == 0

    def test_list_incidents_403_returns_forbidden(self) -> None:
        """403 forbidden should return structured error with error_type=forbidden."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="bad-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                403,
                "Forbidden",
                body=json.dumps({"message": "Forbidden"}),
            )

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "forbidden"
        assert result["status_code"] == 403

    def test_list_incidents_404_returns_not_found(self) -> None:
        """404 not found should return structured error with error_type=not_found."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="bad-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                404,
                "Not Found",
                body=json.dumps({"message": "Not found"}),
            )

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "not_found"
        assert result["status_code"] == 404

    def test_list_incidents_timeout_returns_timeout(self) -> None:
        """Timeout should return structured error with error_type=timeout."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Request timed out")

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "timeout"
        assert result["status_code"] is None
        assert result["incidents"] == []
        assert result["total"] == 0

    def test_list_incidents_connection_refused_returns_unreachable(self) -> None:
        """Connection refused should return error_type=backend_unreachable."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "backend_unreachable"
        assert result["incidents"] == []
        assert result["total"] == 0

    def test_list_incidents_success_parses_response(self) -> None:
        """Successful response should parse incidents correctly."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "incidents": [
                    {"incident_id": "inc-1", "status": "open"},
                    {"incident_id": "inc-2", "status": "collecting_evidence"},
                ],
                "total": 2,
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "incidents" in result
        assert result["total"] == 2
        assert len(result["incidents"]) == 2
        assert "error" not in result

    def test_list_incidents_empty_response_is_not_failure(self) -> None:
        """Empty incident list should not be treated as failure."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "incidents": [],
                "total": 0,
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "error" not in result
        assert result["incidents"] == []
        assert result["total"] == 0

    def test_list_incidents_invalid_json_returns_invalid_json(self) -> None:
        """Invalid JSON response should return error_type=invalid_json."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"not valid json {"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "invalid_json"

    def test_list_incidents_missing_backend_url_returns_error(self) -> None:
        """Missing backend URL should return error_type=missing_backend_url."""
        client = SchedulerClient(base_url="", token="test-token")

        result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "missing_backend_url"
        assert result["incidents"] == []
        assert result["total"] == 0

    def test_list_incidents_token_not_logged(self) -> None:
        """Token should never appear in error messages."""
        test_token = "super-secret-list-token-12345"
        client = SchedulerClient(base_url="http://localhost:8080", token=test_token)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Some error")

            result = client.list_incidents()

        assert test_token not in str(result.get("error", ""))

    def test_list_incidents_missing_token_returns_missing_token_error(self) -> None:
        """Missing internal API token should return error_type=missing_internal_token."""
        client = SchedulerClient(base_url="http://localhost:8080", token="")

        result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "missing_internal_token"

    def test_list_incidents_response_is_list_returns_unexpected_shape(self) -> None:
        """Response with list instead of dict should return error_type=unexpected_shape."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps([]).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "unexpected_shape"
        assert "expected dict" in result["error"]

    def test_list_incidents_response_missing_incidents_returns_unexpected_shape(self) -> None:
        """Response missing 'incidents' field should return error_type=unexpected_shape."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({"total": 0}).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "unexpected_shape"
        assert "missing 'incidents'" in result["error"]

    def test_list_incidents_response_incidents_not_list_returns_unexpected_shape(self) -> None:
        """Response with non-list 'incidents' field should return error_type=unexpected_shape."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="test-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({"incidents": {}, "total": 0}).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "unexpected_shape"
        assert "not a list" in result["error"]

    def test_list_incidents_error_body_has_error_field(self) -> None:
        """HTTP error with 'error' field (not 'message') should parse correctly."""
        client = create_scheduler_client(
            "http://localhost:8080",
            token="bad-token",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                401,
                "Unauthorized",
                body=json.dumps({"error": "Authentication required"}),
            )

            result = client.list_incidents()

        assert "error" in result
        assert result["error"] == "Authentication required"
        assert result["error_type"] == "unauthorized"
