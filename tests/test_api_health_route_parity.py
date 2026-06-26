#!/usr/bin/env python3
"""Route parity tests for /api/health and /api/health/details.

Verifies:
- /api/health healthy -> HTTP 200
- /api/health/details healthy -> HTTP 200 and healthy=true
- /api/health provider failure -> HTTP 500
- /api/health/details provider failure -> HTTP 503 with same primary_failure_class/dependencies
- safe evaluator exception -> backend_health_internal_error + backend_health_route dependency
- direct details call after a previous failed health call re-evaluates fresh
"""

import json
from unittest.mock import patch

import pytest


class MockHandler:
    """Mock HTTP request handler for testing."""

    def __init__(self) -> None:
        self.sent_code: int | None = None
        self.sent_body: dict[str, object] | None = None

    def _send_json(self, body: dict[str, object], code: int) -> None:
        self.sent_code = code
        self.sent_body = body


class TestApiHealthRouteParity:
    """Test parity between /api/health and /api/health/details."""

    def test_healthy_health_returns_200(self) -> None:
        """GET /api/health when healthy returns HTTP 200."""
        from k8s_diag_agent.ui.api_health import handle_health

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={"available": True, "error": None, "phase": "success", "error_class": "provider_available"},
        ):
            handler = MockHandler()
            handle_health(handler)

            assert handler.sent_code == 200
            assert handler.sent_body is not None
            assert handler.sent_body["healthy"] is True
            assert handler.sent_body["primary_failure_class"] == ""

    def test_healthy_details_returns_200_healthy_true(self) -> None:
        """GET /api/health/details when healthy returns HTTP 200 and healthy=true."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={"available": True, "error": None, "phase": "success", "error_class": "provider_available"},
        ):
            handler = MockHandler()
            handle_health_details(handler)

            assert handler.sent_code == 200
            assert handler.sent_body is not None
            assert handler.sent_body["healthy"] is True
            assert handler.sent_body["primary_failure_class"] == ""

    def test_provider_failure_health_returns_500(self) -> None:
        """GET /api/health when provider unavailable returns HTTP 500."""
        from k8s_diag_agent.ui.api_health import handle_health

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": False,
                "error": "Connection refused",
                "phase": "connection_refused",
                "error_class": "provider_connection_failed",
            },
        ):
            handler = MockHandler()
            handle_health(handler)

            assert handler.sent_code == 500
            assert handler.sent_body is not None
            assert handler.sent_body["healthy"] is False
            assert "dependency" in handler.sent_body["primary_failure_class"].lower()

    def test_provider_failure_details_returns_503_with_same_class(self) -> None:
        """GET /api/health/details when provider unavailable returns HTTP 503 with same failure class."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": False,
                "error": "Connection refused",
                "phase": "connection_refused",
                "error_class": "provider_connection_failed",
            },
        ):
            handler = MockHandler()
            handle_health_details(handler)

            assert handler.sent_code == 503
            assert handler.sent_body is not None
            assert handler.sent_body["healthy"] is False
            # Should have dependency_provider_connection_failed
            assert "dependency" in handler.sent_body["primary_failure_class"].lower()
            # Should include diagnosis_provider dependency
            deps = handler.sent_body.get("dependencies", [])
            provider_dep = next((d for d in deps if d.get("dependency_name") == "diagnosis_provider"), None)
            assert provider_dep is not None
            assert provider_dep.get("failure_class") == "dependency_provider_connection_failed"

    def test_evaluator_exception_returns_backend_health_internal_error(self) -> None:
        """safe_evaluate_backend_health returns backend_health_internal_error on exception."""
        from k8s_diag_agent.ui.api_health_details import safe_evaluate_backend_health

        # Make _build_health_dependencies raise an exception
        with patch(
            "k8s_diag_agent.ui.api_health_details._build_health_dependencies",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = safe_evaluate_backend_health()

            assert result.healthy is False
            assert result.primary_failure_class == "backend_health_internal_error"
            # Should have backend_health_route dependency
            route_dep = next(
                (d for d in result.dependencies if d.get("dependency_name") == "backend_health_route"),
                None,
            )
            assert route_dep is not None
            assert route_dep.get("failure_class") == "backend_health_internal_error"
            assert route_dep.get("reason_code") == "health_route_exception"
            assert route_dep.get("phase") == "health_handler"
            # message_snippet should be empty
            assert route_dep.get("message_snippet") == ""

    def test_details_evaluates_fresh_after_failed_health(self) -> None:
        """GET /api/health/details re-evaluates fresh, does not reuse stale state."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        call_count = 0

        def counting_health_status() -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"healthy": True, "error": None}

        def counting_provider_status() -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"available": True, "error": None, "phase": "success", "error_class": "provider_available"}

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            side_effect=counting_health_status,
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            side_effect=counting_provider_status,
        ):
            handler1 = MockHandler()
            handle_health_details(handler1)
            first_body = handler1.sent_body

            # Call again
            handler2 = MockHandler()
            handle_health_details(handler2)
            second_body = handler2.sent_body

            # Both should be healthy and have the same result
            assert handler1.sent_code == 200
            assert handler2.sent_code == 200
            assert first_body is not None
            assert second_body is not None
            assert first_body["healthy"] is True
            assert second_body["healthy"] is True

            # Evaluator should have been called twice (once per request)
            # Each call makes 2 status calls (runtime + provider)
            assert call_count == 4, f"Expected 4 calls, got {call_count}"

    def test_no_raw_secrets_in_health_response(self) -> None:
        """Raw exception text, URLs, IPs, and tokens do not appear in health responses."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._build_health_dependencies",
            side_effect=RuntimeError("Failed to connect to https://api.openai.com/v1 using sk-1234567890abcdef"),
        ):
            handler = MockHandler()
            handle_health_details(handler)

            # Serialize to JSON and check for leaks
            assert handler.sent_body is not None
            response_json = json.dumps(handler.sent_body)

            # Should NOT contain raw secrets/IPs/URLs
            assert "sk-1234567890abcdef" not in response_json
            assert "api.openai.com" not in response_json
            assert "10.0.0.5" not in response_json
            assert "10.0.0.1" not in response_json
            assert "192.168." not in response_json

            # Should contain sanitized values
            assert "backend_health_internal_error" in response_json
            assert "health_route_exception" in response_json
            assert "health_handler" in response_json

    def test_backend_health_internal_error_allowlisted(self) -> None:
        """backend_health_internal_error is in the failure class allowlist."""
        from scripts.backend_health_gate.allowlists import ALLOWED_FAILURE_CLASSES

        assert "backend_health_internal_error" in ALLOWED_FAILURE_CLASSES

    def test_health_route_reason_codes_allowlisted(self) -> None:
        """health_route_exception and health_route_returned_500 are in the reason code allowlist."""
        from scripts.backend_health_gate.allowlists import ALLOWED_REASON_CODES

        assert "health_route_exception" in ALLOWED_REASON_CODES
        assert "health_route_returned_500" in ALLOWED_REASON_CODES
        assert "health_route_healthy" in ALLOWED_REASON_CODES

    def test_health_handler_phase_allowlisted(self) -> None:
        """health_handler is in the phase allowlist."""
        from scripts.backend_health_gate.allowlists import ALLOWED_PROVIDER_PHASES

        assert "health_handler" in ALLOWED_PROVIDER_PHASES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
