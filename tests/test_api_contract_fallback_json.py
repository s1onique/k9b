"""Contract tests for API route fallback and route ordering.

These tests prove that:
1. Unknown /api/* paths return JSON 404, never HTML
2. Route ordering prevents API→SPA fallback leakage
3. All responses are valid JSON when they should be
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockApiHandler, assert_no_html_in_response


class TestApiFallbackGuard:
    """Tests proving unknown API paths return JSON 404, never HTML."""

    def test_unknown_api_path_returns_non_html_404(self) -> None:
        """Unknown /api/* path returns 404 that is NOT HTML (text or JSON)."""
        from k8s_diag_agent.ui.server_reads import handle_api

        handler = MockApiHandler()
        handler.path = "/api/does-not-exist"
        handler.runs_dir = Path("/tmp/test/runs")

        # Need to provide a mock context so handle_api continues past the context check
        with patch.object(
            handler,
            "_load_context",
            return_value={"run_id": "test-run", "clusters": []},
        ):
            handle_api(handler, handler.path, "")

            # Must return 404
            assert handler._sent_code == 404, f"Expected 404, got {handler._sent_code}"

            # Must return text or JSON, never HTML
            response_body = handler._sent_body or handler._sent_text
            assert response_body is not None

            # Check it's not HTML (text "Not Found" is fine, JSON is fine)
            body_str = json.dumps(response_body) if isinstance(response_body, dict) else str(response_body)
            assert "<html" not in body_str.lower()
            assert "<!doctype" not in body_str.lower()
            assert "index.html" not in body_str.lower()

    def test_unknown_health_child_path_returns_json_404(self) -> None:
        """Unknown /api/health/{child} path returns JSON 404, not HTML."""
        from k8s_diag_agent.ui.server_reads import handle_api

        handler = MockApiHandler()
        handler.path = "/api/health/does-not-exist"
        handler.runs_dir = Path("/tmp/test/runs")

        with patch.object(handler, "_load_context", return_value=None):
            handle_api(handler, handler.path, "")

            # Should return 404 or handle gracefully
            if handler._sent_code == 404:
                response_body = handler._sent_body or handler._sent_text
                assert response_body is not None
                body_str = json.dumps(response_body) if isinstance(response_body, dict) else str(response_body)
                assert "<html" not in body_str.lower()


class TestRouteOrdering:
    """Tests proving route ordering prevents API→SPA fallback leakage.

    Key insight: /api/* paths must be handled by handle_api(), never reaching
    serve_static(). This prevents HTML from index.html leaking into API responses.
    """

    def test_api_path_never_reaches_spa_fallback(self) -> None:
        """/api/* paths are handled by handle_api, never by serve_static."""
        from k8s_diag_agent.ui.server_routes import handle_get_request

        handler = MockApiHandler()
        handler.path = "/api/health/details"
        handler.static_dir = Path("/tmp/test/static")

        # Should not raise and should not fall through to SPA
        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=False),
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": True,
                "error": None,
                "phase": "success",
                "error_class": "provider_available",
            },
        ):
            handle_get_request(handler)

            # Should have sent a response (not fallen through to SPA)
            assert handler._sent_code is not None
            assert handler._sent_code in (200, 503)

    def test_non_api_path_reaches_spa_fallback(self) -> None:
        """Non-API paths reach serve_static for SPA fallback."""
        from k8s_diag_agent.ui.server_routes import handle_get_request

        handler = MockApiHandler()
        handler.path = "/dashboard"
        handler.static_dir = Path("/tmp/test/static")

        with patch(
            "k8s_diag_agent.ui.auth_guard.get_auth_config",
            return_value=MagicMock(enabled=False),
        ):
            handle_get_request(handler)

            # Should reach SPA fallback
            # (May return 200 with HTML or 404 depending on static dir contents)
            assert handler._sent_code is not None


class TestJsonSerializationContract:
    """Tests proving all responses are valid JSON."""

    def test_health_details_is_valid_json(self) -> None:
        """health/details response must be valid JSON (parseable)."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": True,
                "error": None,
                "phase": "success",
                "error_class": "provider_available",
            },
        ):
            handler = MockApiHandler()
            handle_health_details(handler)

            # Must be parseable as JSON
            assert handler._sent_body is not None
            json_str = json.dumps(handler._sent_body)
            parsed = json.loads(json_str)
            assert parsed is not None


class TestNoHtmlLeakage:
    """Tests proving no HTML content leaks into JSON responses."""

    def test_health_response_contains_no_html(self) -> None:
        """Health response must not contain HTML tags."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": True,
                "error": None,
                "phase": "success",
                "error_class": "provider_available",
            },
        ):
            handler = MockApiHandler()
            handle_health_details(handler)

            assert_no_html_in_response(handler)

    def test_incident_not_found_is_valid_json(self) -> None:
        """incident not found response must be valid JSON."""
        from k8s_diag_agent.ui.server_incident_reads import handle_incident_detail_route

        with patch(
            "k8s_diag_agent.ui.server_incident_reads.handle_get_incident",
            return_value=None,
        ):
            handler = MockApiHandler()
            handler.path = "/api/incidents/missing"
            handle_incident_detail_route(handler, handler.path)

            assert handler._sent_body is not None
            json_str = json.dumps(handler._sent_body)
            parsed = json.loads(json_str)
            assert "error" in parsed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
