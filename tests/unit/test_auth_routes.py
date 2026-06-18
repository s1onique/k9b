"""Tests for authentication routes.

These tests verify that the authentication HTTP handler functions correctly:
- Cookie building functions
- Session cookie parsing
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

from k8s_diag_agent.ui.auth_routes import (
    _build_clear_cookie,
    _build_session_cookie,
    _get_session_cookie,
)


class MockHandler:
    """Mock HTTP request handler for testing auth routes."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.rfile = BytesIO()

    def set_headers(self, headers: dict[str, str]) -> None:
        """Set request headers."""
        self.headers = headers

    def set_body(self, body: str | bytes) -> None:
        """Set request body."""
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.rfile = BytesIO(body)


class TestBuildSessionCookie:
    """Tests for _build_session_cookie function."""

    def test_build_session_cookie_basic(self) -> None:
        """Test basic session cookie building."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "k9b_session"
        mock_config.session_max_age = 3600
        mock_config.secure_cookie = False

        cookie = _build_session_cookie("test_session_id", mock_config)

        assert "k9b_session=test_session_id" in cookie
        assert "HttpOnly" in cookie
        assert "Path=/" in cookie
        assert "Max-Age=3600" in cookie
        assert "SameSite=Lax" in cookie
        assert "Secure" not in cookie

    def test_build_session_cookie_secure(self) -> None:
        """Test session cookie with Secure flag."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "k9b_session"
        mock_config.session_max_age = 7200
        mock_config.secure_cookie = True

        cookie = _build_session_cookie("test_session_id", mock_config)

        assert "Secure" in cookie

    def test_build_session_cookie_custom_name(self) -> None:
        """Test session cookie with custom name."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "custom_session"
        mock_config.session_max_age = 1800
        mock_config.secure_cookie = False

        cookie = _build_session_cookie("session_abc123", mock_config)

        assert "custom_session=session_abc123" in cookie


class TestBuildClearCookie:
    """Tests for _build_clear_cookie function."""

    def test_build_clear_cookie_basic(self) -> None:
        """Test basic clear cookie building."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "k9b_session"
        mock_config.secure_cookie = False

        cookie = _build_clear_cookie("k9b_session", mock_config)

        assert "k9b_session=" in cookie
        assert "HttpOnly" in cookie
        assert "Path=/" in cookie
        assert "Max-Age=0" in cookie
        assert "Expires=Thu, 01 Jan 1970 00:00:00 GMT" in cookie

    def test_build_clear_cookie_secure(self) -> None:
        """Test clear cookie with Secure flag."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "k9b_session"
        mock_config.secure_cookie = True

        cookie = _build_clear_cookie("k9b_session", mock_config)

        assert "Secure" in cookie


class TestGetSessionCookie:
    """Tests for _get_session_cookie function."""

    def test_get_session_cookie_found(self) -> None:
        """Test extracting session cookie when present."""
        handler = MockHandler()
        handler.set_headers({"Cookie": "k9b_session=test_session_123"})

        session_id = _get_session_cookie(handler, "k9b_session")

        assert session_id == "test_session_123"

    def test_get_session_cookie_not_found(self) -> None:
        """Test extracting session cookie when not present."""
        handler = MockHandler()
        handler.set_headers({"Cookie": "other=value"})

        session_id = _get_session_cookie(handler, "k9b_session")

        assert session_id is None

    def test_get_session_cookie_no_headers(self) -> None:
        """Test extracting session cookie with no cookie header."""
        handler = MockHandler()
        handler.set_headers({})

        session_id = _get_session_cookie(handler, "k9b_session")

        assert session_id is None

    def test_get_session_cookie_multiple(self) -> None:
        """Test extracting session cookie with multiple cookies."""
        handler = MockHandler()
        handler.set_headers({"Cookie": "a=1; k9b_session=abc123; b=2"})

        session_id = _get_session_cookie(handler, "k9b_session")

        assert session_id == "abc123"

    def test_get_session_cookie_whitespace_handling(self) -> None:
        """Test cookie parsing handles whitespace correctly."""
        handler = MockHandler()
        handler.set_headers({"Cookie": "  k9b_session=value  "})

        session_id = _get_session_cookie(handler, "k9b_session")

        assert session_id == "value"


class TestCookieSecurityAttributes:
    """Tests for security attributes in cookies."""

    def test_session_cookie_has_httponly(self) -> None:
        """Test that session cookies have HttpOnly flag."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "test"
        mock_config.session_max_age = 3600
        mock_config.secure_cookie = False

        cookie = _build_session_cookie("id", mock_config)

        assert "HttpOnly" in cookie

    def test_session_cookie_has_samesite(self) -> None:
        """Test that session cookies have SameSite attribute."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "test"
        mock_config.session_max_age = 3600
        mock_config.secure_cookie = False

        cookie = _build_session_cookie("id", mock_config)

        assert "SameSite=Lax" in cookie

    def test_clear_cookie_expires_immediately(self) -> None:
        """Test that clear cookies expire immediately."""
        mock_config = MagicMock()
        mock_config.session_cookie_name = "test"
        mock_config.secure_cookie = False

        cookie = _build_clear_cookie("test", mock_config)

        assert "Max-Age=0" in cookie
        assert "Expires=Thu, 01 Jan 1970 00:00:00 GMT" in cookie
