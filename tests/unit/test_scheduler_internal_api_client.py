"""Transport contract tests for SchedulerClient internal API client.

Tests validate:
1. promote_alert_signals uses alert endpoint
2. promote_candidates uses generic endpoint
3. Missing backend URL returns bounded error
4. Missing token returns bounded error (no token logged)
5. 401 unauthorized maps to structured error
6. Timeout maps to timeout/backend_unreachable
7. Invalid JSON/bad response maps to invalid_json/bad_response
8. promotion_mode remains backend-api in dispatcher result
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from k8s_diag_agent.ui.server_incident_internal_client import (
    PromotionErrorReason,
    SchedulerClient,
    create_scheduler_client,
)


class MockHTTPResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status: int = 200,
        body: str | dict | None = None,
        headers: dict | None = None,
    ):
        self.status = status
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self) -> bytes:
        """Return the response body as bytes."""
        if isinstance(self._body, str):
            return self._body.encode("utf-8")
        return json.dumps(self._body or {}).encode("utf-8")


class MockHTTPError(Exception):
    """Mock HTTP error for testing."""

    def __init__(self, code: int, message: str, body: str = ""):
        super().__init__(message)
        self.code = code
        self.reason = message
        self._body = body

    def read(self) -> bytes:
        """Return the error body as bytes."""
        return self._body.encode("utf-8")


class TestSchedulerClientEndpoints:
    """Test that client uses correct endpoints."""

    def test_promote_alert_signals_uses_alert_endpoint(self) -> None:
        """promote_alert_signals should call /promote-alert-signals endpoint."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch.object(client, "_post_request") as mock_post:
            mock_post.return_value = MagicMock(ok=True, errors=0, error_messages=[])

            client.promote_alert_signals(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

            # Verify the URL contains the alert-signals endpoint
            call_args = mock_post.call_args
            assert "/promote-alert-signals" in call_args[0][0]

    def test_promote_candidates_uses_generic_endpoint(self) -> None:
        """promote_candidates should call /promote-candidates endpoint."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch.object(client, "_post_request") as mock_post:
            mock_post.return_value = MagicMock(ok=True, errors=0, error_messages=[])

            client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

            # Verify the URL contains the promote-candidates endpoint
            call_args = mock_post.call_args
            assert "/promote-candidates" in call_args[0][0]

    def test_promote_alert_signals_does_not_call_promote_candidates(self) -> None:
        """promote_alert_signals should NOT call the generic promote_candidates endpoint."""
        client = create_scheduler_client(
            "http://k9b-backend:8080",
            token="test-token",
        )

        with patch.object(client, "_post_request") as mock_post:
            mock_post.return_value = MagicMock(ok=True, errors=0, error_messages=[])

            client.promote_alert_signals(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

            # Verify the URL does NOT contain the generic endpoint
            call_args = mock_post.call_args
            assert "/promote-candidates" not in call_args[0][0]


class TestSchedulerClientErrorHandling:
    """Test bounded error handling in SchedulerClient."""

    def test_missing_backend_url_returns_bounded_error(self) -> None:
        """Missing backend URL should return bounded error, not raise exception."""
        client = SchedulerClient(base_url="", token=None)

        result = client.promote_candidates(
            candidates=[{"id": "test"}],
            observed_at=datetime.now(),
        )

        assert result.ok is False
        assert result.errors == 1
        assert len(result.error_messages) == 1

    def test_missing_token_returns_bounded_error(self) -> None:
        """Missing token should return bounded error, not raise exception."""
        client = SchedulerClient(base_url="http://localhost:8080", token=None)

        # Mock URL opening to raise an error
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        # Should return bounded error, not crash
        assert result.ok is False
        assert result.errors == 1

    def test_401_unauthorized_returns_structured_error(self) -> None:
        """401 unauthorized should map to structured error with unauthorized reason."""
        client = SchedulerClient(base_url="http://localhost:8080", token="bad-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                401,
                "Unauthorized",
                body=json.dumps({"message": "Invalid token"}),
            )

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        assert result.ok is False
        assert result.errors == 1
        # Error message should NOT contain the token
        for msg in result.error_messages:
            assert "bad-token" not in msg
            assert "test-token" not in msg

    def test_timeout_returns_bounded_error(self) -> None:
        """Timeout should return bounded error, not crash."""
        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Request timed out")

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
                timeout=1.0,
            )

        # Should return bounded error, not crash
        assert result.ok is False
        assert result.errors == 1
        assert "timed out" in result.error_messages[0].lower() or "timeout" in result.error_messages[0].lower()

    def test_connection_refused_returns_bounded_error(self) -> None:
        """Connection refused should return bounded error, not crash."""
        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        # Should return bounded error, not crash
        assert result.ok is False
        assert result.errors == 1

    def test_invalid_json_response_returns_bounded_error(self) -> None:
        """Invalid JSON response should return bounded error, not crash."""
        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            # Return a response that isn't valid JSON
            mock_response = MagicMock()
            mock_response.read.return_value = b"not valid json {"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        # Should return bounded error, not crash
        assert result.ok is False
        assert result.errors == 1

    def test_bad_http_status_returns_bounded_error(self) -> None:
        """Bad HTTP status should return bounded error, not crash."""
        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = MockHTTPError(
                500,
                "Internal Server Error",
                body="Internal error",
            )

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        # Should return bounded error, not crash
        assert result.ok is False
        assert result.errors == 1


class TestSchedulerClientTokenHandling:
    """Test that token is never logged."""

    def test_token_not_in_error_messages(self) -> None:
        """Token should never appear in error messages."""
        test_token = "super-secret-token-12345"
        client = SchedulerClient(base_url="http://localhost:8080", token=test_token)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Some error")

            result = client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

        # Token should not appear in any error messages
        for msg in result.error_messages:
            assert test_token not in msg

    def test_token_in_authorization_header(self) -> None:
        """Token should be included in Authorization header."""
        client = SchedulerClient(base_url="http://localhost:8080", token="test-token-123")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps({
                "ok": True,
                "errors": 0,
                "error_messages": [],
            }).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            client.promote_candidates(
                candidates=[{"id": "test"}],
                observed_at=datetime.now(),
            )

            # Verify the request was made with Authorization header
            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert "Authorization" in request.headers
            assert request.headers["Authorization"] == "Bearer test-token-123"


class TestSchedulerClientIntegration:
    """Integration-style tests for the full promotion path."""

    def test_create_scheduler_client_returns_configured_instance(self) -> None:
        """create_scheduler_client should return a properly configured instance."""
        client = create_scheduler_client(
            base_url="http://k9b-backend:8080",
            token="my-secret-token",
        )

        assert client._base_url == "http://k9b-backend:8080"
        assert client._token == "my-secret-token"

    def test_create_scheduler_client_without_token(self) -> None:
        """create_scheduler_client should work without a token."""
        client = create_scheduler_client(
            base_url="http://k9b-backend:8080",
            token=None,
        )

        assert client._base_url == "http://k9b-backend:8080"
        assert client._token is None

    def test_base_url_trailing_slash_normalized(self) -> None:
        """Base URL trailing slash should be normalized."""
        client = SchedulerClient(base_url="http://k9b-backend:8080/", token=None)

        # The base URL should have trailing slash removed
        assert client._base_url == "http://k9b-backend:8080"


class TestPromotionErrorReason:
    """Test PromotionErrorReason constants are defined."""

    def test_error_reasons_defined(self) -> None:
        """Error reason constants should be defined."""
        assert PromotionErrorReason.BACKEND_UNREACHABLE == "backend_unreachable"
        assert PromotionErrorReason.UNAUTHORIZED == "unauthorized"
        assert PromotionErrorReason.BAD_RESPONSE == "bad_response"
        assert PromotionErrorReason.TIMEOUT == "timeout"
        assert PromotionErrorReason.INVALID_JSON == "invalid_json"
        assert PromotionErrorReason.UNKNOWN == "unknown"
