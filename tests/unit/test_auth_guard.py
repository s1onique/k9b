"""Tests for authentication guard middleware.

These tests verify that the auth guard correctly:
- Identifies public vs protected routes
- Extracts session IDs from requests
"""

from __future__ import annotations

from k8s_diag_agent.ui.auth_config import reset_auth_config
from k8s_diag_agent.ui.auth_guard import (
    get_session_id_from_request,
    is_public_route,
)
from k8s_diag_agent.ui.auth_provider import reset_auth_provider


class TestIsPublicRoute:
    """Tests for is_public_route function."""

    def test_public_routes_auth_endpoints(self) -> None:
        """Test that auth endpoints are public."""
        assert is_public_route("/api/auth/login") is True
        assert is_public_route("/api/auth/logout") is True
        assert is_public_route("/api/auth/me") is True
        assert is_public_route("/api/auth/status") is True

    def test_public_routes_health_check(self) -> None:
        """Test that health check routes are public."""
        assert is_public_route("/health") is True
        assert is_public_route("/ready") is True

    def test_public_routes_debug(self) -> None:
        """Test that specific debug routes are public."""
        assert is_public_route("/api/debug/diagnostics-enabled") is True

    def test_public_routes_non_api(self) -> None:
        """Test that non-API routes are public (static assets, SPA)."""
        assert is_public_route("/static/app.js") is True
        assert is_public_route("/static/chunk.js") is True
        assert is_public_route("/assets/logo.png") is True
        assert is_public_route("/") is True
        assert is_public_route("/some/path") is True

    def test_protected_routes_api_reads(self) -> None:
        """Test that API read endpoints are protected."""
        assert is_public_route("/api/fleet") is False
        assert is_public_route("/api/proposals") is False
        assert is_public_route("/api/cluster-detail") is False
        assert is_public_route("/api/run") is False
        assert is_public_route("/api/notifications") is False

    def test_protected_routes_artifact(self) -> None:
        """Test that artifact routes are protected."""
        assert is_public_route("/artifact") is False
        assert is_public_route("/artifact/some/path") is False

    def test_protected_routes_runs(self) -> None:
        """Test that runs list is protected."""
        assert is_public_route("/api/runs") is False

    def test_protected_routes_incidents(self) -> None:
        """Test that incidents routes are protected."""
        assert is_public_route("/api/incidents") is False

    def test_protected_routes_next_checks(self) -> None:
        """Test that next-check routes are protected."""
        assert is_public_route("/api/next-check-plan") is False
        assert is_public_route("/api/next-check-queue") is False

    def test_protected_routes_runtime_status(self) -> None:
        """Test that runtime-status is protected."""
        assert is_public_route("/api/runtime-status") is False

    def test_protected_routes_vmalert(self) -> None:
        """Test that vmalert routes are protected."""
        assert is_public_route("/api/vmalert/rules") is False

    def test_protected_routes_batch(self) -> None:
        """Test that batch execution routes are protected."""
        assert is_public_route("/api/run-batch-execute") is False


class TestGetSessionIdFromRequest:
    """Tests for get_session_id_from_request function."""

    def setup_method(self) -> None:
        """Reset auth state before each test."""
        reset_auth_config()
        reset_auth_provider()

    def test_get_session_from_cookie(self) -> None:
        """Test extracting session from cookie header."""
        mock_handler = MockHandler()
        mock_handler.headers = {"Cookie": "k9b_session=test_session_123"}

        session_id = get_session_id_from_request(mock_handler)

        assert session_id == "test_session_123"

    def test_get_session_no_cookie(self) -> None:
        """Test that missing cookie returns None."""
        mock_handler = MockHandler()
        mock_handler.headers = {}

        session_id = get_session_id_from_request(mock_handler)

        assert session_id is None

    def test_get_session_different_cookie_name(self) -> None:
        """Test that non-session cookies are ignored."""
        mock_handler = MockHandler()
        mock_handler.headers = {"Cookie": "other=value; session=abc; k9b_session=xyz"}

        session_id = get_session_id_from_request(mock_handler)

        assert session_id == "xyz"

    def test_get_session_cookie_spacing(self) -> None:
        """Test handling of cookie spacing."""
        mock_handler = MockHandler()
        mock_handler.headers = {"Cookie": "  k9b_session=value  "}

        session_id = get_session_id_from_request(mock_handler)

        assert session_id == "value"


class MockHandler:
    """Mock HTTP request handler for testing auth guard."""

    def __init__(self) -> None:
        self.path: str = "/"
        self.headers: dict[str, str] = {}


class TestPublicRouteClassification:
    """Tests for route classification correctness."""

    def test_auth_routes_pattern(self) -> None:
        """Test that auth route pattern matches correctly."""
        # All /api/auth/* routes should be public
        auth_routes = [
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/me",
            "/api/auth/status",
            "/api/auth/something-else",
        ]
        for route in auth_routes:
            assert is_public_route(route) is True, f"Expected {route} to be public"

    def test_static_routes_are_public(self) -> None:
        """Test that static asset routes are public."""
        static_routes = [
            "/static/js/app.js",
            "/static/css/style.css",
            "/assets/images/logo.png",
            "/favicon.ico",
        ]
        for route in static_routes:
            assert is_public_route(route) is True, f"Expected {route} to be public"

    def test_root_is_public(self) -> None:
        """Test that root path is public (for SPA)."""
        assert is_public_route("/") is True
        assert is_public_route("") is True
