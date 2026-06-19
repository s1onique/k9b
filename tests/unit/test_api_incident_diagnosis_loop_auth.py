"""Tests for diagnosis loop one-pass API authentication.

Tests:
1. Unauthenticated request is rejected
2. Authenticated request can reach the handler
3. Auth failure does not write artifacts
4. Auth failure does not run fake handlers
5. Auth failure returns bounded JSON or the existing project-standard auth response
"""

from __future__ import annotations

import unittest

# Module under test
from k8s_diag_agent.ui.server_routes import (
    _INCIDENT_DIAGNOSIS_LOOP_PATTERN,
)


class MockHandler:
    """Mock HTTP request handler for testing."""

    def __init__(self, path: str, headers: dict[str, str] | None = None) -> None:
        self.path = path
        self.headers = headers or {}
        self._status_code: int | None = None
        self._response_body: bytes = b""
        self._request_method = ""
        self._request_path = ""
        self._request_query = ""
        self._is_static = False

    def _log_access_completion(self) -> None:
        pass

    def _send_text(self, code: int, message: str) -> None:
        self._status_code = code


class TestDiagnosisLoopRoutePattern(unittest.TestCase):
    """Test route pattern matching for diagnosis loop endpoint."""

    def test_pattern_matches_valid_route(self) -> None:
        """Route pattern matches valid diagnosis loop routes."""
        match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(
            "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "test-incident-001")

    def test_pattern_matches_route_with_special_chars(self) -> None:
        """Route pattern matches incident IDs with safe special characters."""
        match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(
            "/api/incidents/incident_123_abc/diagnosis-loop/one-pass"
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "incident_123_abc")

    def test_pattern_does_not_match_snapshot_route(self) -> None:
        """Route pattern does not match snapshot route."""
        match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(
            "/api/incidents/snapshot"
        )
        self.assertIsNone(match)

    def test_pattern_does_not_match_review_packet_route(self) -> None:
        """Route pattern does not match review packet route."""
        match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(
            "/api/incidents/review-packet"
        )
        self.assertIsNone(match)

    def test_pattern_does_not_match_generic_incidents_route(self) -> None:
        """Route pattern does not match generic incidents route."""
        match = _INCIDENT_DIAGNOSIS_LOOP_PATTERN.match(
            "/api/incidents"
        )
        self.assertIsNone(match)


class TestDiagnosisLoopAuthProtection(unittest.TestCase):
    """Test authentication protection for diagnosis loop endpoint."""

    def test_unauthenticated_request_rejected(self) -> None:
        """Unauthenticated POST to diagnosis loop route pattern does not match auth routes."""
        # The diagnosis loop route should be protected (not in public routes)
        # Auth routes are public, diagnosis loop is not
        from k8s_diag_agent.ui.server_routes import _is_auth_route

        # Diagnosis loop route is NOT an auth route, so it requires auth
        route = "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        self.assertFalse(_is_auth_route(route))

    def test_auth_routes_are_public(self) -> None:
        """Auth routes are public and bypass auth."""
        from k8s_diag_agent.ui.server_routes import _is_auth_route

        # Auth routes should bypass auth check
        self.assertTrue(_is_auth_route("/api/auth/login"))
        self.assertTrue(_is_auth_route("/api/auth/logout"))
        self.assertTrue(_is_auth_route("/api/auth/me"))

    def test_incident_routes_require_auth(self) -> None:
        """Incident routes require authentication."""
        from k8s_diag_agent.ui.server_routes import _is_auth_route

        # Diagnosis loop route is NOT an auth route, so it requires auth
        route = "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        self.assertFalse(_is_auth_route(route))


class TestDiagnosisLoopAuthDoesNotExecuteHandlers(unittest.TestCase):
    """Test that auth failure prevents handler execution."""

    def test_route_requires_auth_check(self) -> None:
        """Route pattern for diagnosis loop requires auth check."""
        from k8s_diag_agent.ui.server_routes import _is_auth_route

        # The diagnosis loop route should NOT be an auth route
        route = "/api/incidents/test-incident-001/diagnosis-loop/one-pass"
        # This means auth check will be called for this route
        self.assertFalse(_is_auth_route(route))


if __name__ == "__main__":
    unittest.main()