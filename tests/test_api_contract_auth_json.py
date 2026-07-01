"""Contract tests for auth failure JSON responses.

These tests prove that auth failures return JSON 401, never HTML/login page.
They test the auth guard directly and also verify the route-dispatch level behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockApiHandler, assert_json_response, assert_no_html_in_response


class TestAuthGuardJsonResponse:
    """Tests proving auth failures return JSON 401, never HTML/login page.

    These tests verify that:
    1. Unauthenticated requests return JSON 401 with proper error field
    2. Invalid/expired sessions return JSON 401
    3. Only ONE response is sent (no double-send)
    4. Response contains no HTML
    """

    def test_unauthenticated_request_returns_json_401(self) -> None:
        """Unauthenticated request to protected route returns JSON 401 with error field."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        # Mock auth as enabled and no session
        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value=None,
        ):
            result = check_route_auth(handler)  # type: ignore[arg-type]

            # Should return False (not authenticated)
            assert result is False, "check_route_auth should return False for unauthenticated request"

            # Auth guard should have sent exactly ONE JSON 401 response
            assert handler._sent_code == 401, f"Expected 401, got {handler._sent_code}"
            assert_json_response(handler, expected_code=401)

            # Response should have error field (not HTML)
            assert handler._sent_body is not None
            assert "error" in handler._sent_body, "Auth failure response must have 'error' field"
            assert_no_html_in_response(handler)

    def test_invalid_session_returns_json_401(self) -> None:
        """Invalid/expired session returns JSON 401 with error field."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value="invalid-session-id",
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_principal_for_session",
            return_value=None,  # Invalid session
        ):
            result = check_route_auth(handler)  # type: ignore[arg-type]

            # Should return False
            assert result is False

            # Should have sent exactly ONE JSON 401 response
            assert handler._sent_code == 401, f"Expected 401, got {handler._sent_code}"
            assert_json_response(handler, expected_code=401)

            # Response should have error field
            assert handler._sent_body is not None
            assert "error" in handler._sent_body
            assert_no_html_in_response(handler)

    def test_auth_disabled_returns_dev_principal(self) -> None:
        """When auth is disabled, request proceeds (dev mode)."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/health/details"  # Protected but auth disabled

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=False),  # Auth disabled
        ):
            result = check_route_auth(handler)  # type: ignore[arg-type]

            # Should return True (auth disabled means allow all)
            assert result is True, "check_route_auth should return True when auth is disabled"

    def test_no_double_send_on_auth_failure(self) -> None:
        """Auth failure sends exactly one response, not two."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value=None,
        ):
            check_route_auth(handler)  # type: ignore[arg-type]

            # Exactly ONE response should be sent
            assert handler._send_count == 1, (
                f"Expected exactly 1 response sent, got {handler._send_count}. "
                "This indicates a double-send bug in auth guard."
            )


class TestAuthResponseContract:
    """Tests for auth response structure contract."""

    def test_auth_error_response_has_error_field(self) -> None:
        """Auth failure response must have 'error' field with descriptive message."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value=None,
        ):
            check_route_auth(handler)  # type: ignore[arg-type]

            # Response must have 'error' field
            assert handler._sent_body is not None
            assert "error" in handler._sent_body, "Auth failure must have 'error' field"
            assert isinstance(handler._sent_body["error"], str), "error field must be a string"
            assert len(handler._sent_body["error"]) > 0, "error field must not be empty"

    def test_auth_error_no_html(self) -> None:
        """Auth failure response must not contain HTML/login page."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value=None,
        ):
            check_route_auth(handler)  # type: ignore[arg-type]

            # Must not contain HTML
            assert_no_html_in_response(handler)

    def test_session_expired_error_message(self) -> None:
        """Expired session should have descriptive error message."""
        from k8s_diag_agent.ui.auth_guard import check_route_auth

        handler = MockApiHandler()
        handler.path = "/api/incidents"

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=True),
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_session_id_from_request",
            return_value="expired-session-id",
        ), patch(
            "k8s_diag_agent.ui.auth_guard.get_principal_for_session",
            return_value=None,  # Session expired/invalid
        ):
            check_route_auth(handler)  # type: ignore[arg-type]

            # Error message should be descriptive
            assert handler._sent_body is not None
            assert "error" in handler._sent_body
            error_msg = handler._sent_body["error"].lower()
            # Should indicate session issue
            assert "session" in error_msg or "expired" in error_msg or "invalid" in error_msg, (
                f"Expected session-related error message, got: {handler._sent_body['error']}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
