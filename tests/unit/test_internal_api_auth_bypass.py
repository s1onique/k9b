"""Regression test for internal API auth-layer ordering bug.

Tests that /api/internal/* routes bypass UI/session auth guard and are
protected only by bearer token auth in the handlers.

Bug: Internal routes were being rejected by the UI/session auth guard
before the internal bearer token auth could run, causing 401 with
"Authentication required" (the UI auth error, not the internal token error).

Fix: _is_session_auth_exempt_route() returns True for explicitly
allowlisted internal routes, bypassing the session auth check.
The internal handlers themselves call _validate_internal_token() to
enforce bearer token auth.

Security model: Each internal route is explicitly allowlisted in
_INTERNAL_AUTH_EXEMPT_ROUTES to ensure no accidental auth bypass.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from k8s_diag_agent.ui.server_routes import (
    _INTERNAL_AUTH_EXEMPT_ROUTES,
    _is_session_auth_exempt_route,
)


class TestInternalApiAuthAllowlist:
    """Test that internal routes are explicitly allowlisted (Option A)."""

    def test_known_internal_routes_are_allowlisted(self) -> None:
        """Verify known internal routes are in the allowlist."""
        expected_routes = {
            "/api/internal/incidents/promote-alert-signals",
            "/api/internal/incidents/promote-candidates",
        }
        assert _INTERNAL_AUTH_EXEMPT_ROUTES == expected_routes

    def test_allowlisted_routes_bypass_ui_auth(self) -> None:
        """Verify allowlisted internal routes bypass UI auth."""
        for route in _INTERNAL_AUTH_EXEMPT_ROUTES:
            assert _is_session_auth_exempt_route(route) is True, f"Route {route} should bypass UI auth"

    def test_unknown_internal_routes_require_ui_auth(self) -> None:
        """Verify unknown internal routes still require UI auth (security)."""
        unknown_routes = [
            "/api/internal/foo/bar",
            "/api/internal/unknown/route",
            "/api/internal/admin/config",
        ]
        for route in unknown_routes:
            assert _is_session_auth_exempt_route(route) is False, f"Route {route} should require UI auth"


class TestInternalApiAuthFlow:
    """Test the full auth flow for internal routes."""

    def test_internal_route_bypasses_session_auth(self) -> None:
        """Verify internal routes bypass session auth path."""
        for route in _INTERNAL_AUTH_EXEMPT_ROUTES:
            assert _is_session_auth_exempt_route(route) is True, f"Route {route} should bypass UI auth"

    def test_non_internal_routes_require_ui_auth(self) -> None:
        """Verify non-internal routes still require UI auth."""
        # Auth routes are public
        assert _is_session_auth_exempt_route("/api/auth/login") is True
        assert _is_session_auth_exempt_route("/api/auth/logout") is True
        # Regular API routes should NOT bypass UI auth
        assert _is_session_auth_exempt_route("/api/incidents") is False
        assert _is_session_auth_exempt_route("/api/runs") is False
        assert _is_session_auth_exempt_route("/api/next-check-execution") is False

    def test_handler_validates_bearer_token_format(self) -> None:
        """Test that _validate_internal_token checks for Bearer prefix."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_incident_internal_auth import (
            _validate_internal_token,
        )

        with patch.dict(
            "os.environ",
            {"K9B_INCIDENT_STORE_BACKEND": "sqlite", "K9B_INTERNAL_API_TOKEN": "secret"},
        ):
            mock_handler = MagicMock()
            mock_handler.headers = {"Authorization": "Basic secret"}  # Wrong scheme

            result = _validate_internal_token(mock_handler)
            assert result is False

    def test_handler_accepts_correct_bearer_token(self) -> None:
        """Test that _validate_internal_token accepts correct Bearer token."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_incident_internal_auth import (
            _validate_internal_token,
        )

        with patch.dict(
            "os.environ",
            {"K9B_INCIDENT_STORE_BACKEND": "sqlite", "K9B_INTERNAL_API_TOKEN": "secret"},
        ):
            mock_handler = MagicMock()
            mock_handler.headers = {"Authorization": "Bearer secret"}

            result = _validate_internal_token(mock_handler)
            assert result is True

    def test_handler_rejects_missing_bearer_prefix(self) -> None:
        """Test that _validate_internal_token rejects tokens without Bearer prefix."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_incident_internal_auth import (
            _validate_internal_token,
        )

        with patch.dict(
            "os.environ",
            {"K9B_INCIDENT_STORE_BACKEND": "sqlite", "K9B_INTERNAL_API_TOKEN": "secret"},
        ):
            mock_handler = MagicMock()
            mock_handler.headers = {"Authorization": "Token secret"}  # Not Bearer

            result = _validate_internal_token(mock_handler)
            assert result is False

    def test_sqlite_mode_requires_token(self) -> None:
        """Test that SQLite mode (production) fails when token is missing."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_incident_internal_auth import (
            _validate_internal_token,
        )

        with patch.dict("os.environ", {"K9B_INCIDENT_STORE_BACKEND": "sqlite"}):
            mock_handler = MagicMock()
            mock_handler.headers = {}

            result = _validate_internal_token(mock_handler)
            assert result is False

    def test_dev_mode_allows_missing_token_when_configured(self) -> None:
        """Test that dev mode (non-SQLite) allows request when token is missing but Bearer is present."""
        from unittest.mock import patch

        from k8s_diag_agent.ui.server_incident_internal_auth import (
            _validate_internal_token,
        )

        # Dev mode allows with Bearer header present but no token configured
        with patch.dict("os.environ", {"K9B_INCIDENT_STORE_BACKEND": "memory"}):
            mock_handler = MagicMock()
            mock_handler.headers = {"Authorization": "Bearer any-value"}

            result = _validate_internal_token(mock_handler)
            # Dev mode allows request when token not configured
            assert result is True
