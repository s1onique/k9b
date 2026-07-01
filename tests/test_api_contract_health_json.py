"""Contract tests for /api/health/details JSON responses.

These tests prove that /api/health/details always returns JSON (200 or 503),
never HTML. They test the route handler directly without requiring a live cluster.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.helpers import MockApiHandler, assert_json_response, assert_no_html_in_response


class TestHealthDetailsJsonContract:
    """Tests proving /api/health/details returns JSON, never HTML."""

    def test_healthy_returns_json_200(self) -> None:
        """GET /api/health/details when healthy returns HTTP 200 with JSON body."""
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

            # Must return 200 when healthy
            assert handler._sent_code == 200, f"Expected 200, got {handler._sent_code}"

            # Must return JSON-serializable body
            assert_json_response(handler, expected_code=200)
            assert handler._sent_body is not None
            assert "healthy" in handler._sent_body
            assert "primary_failure_class" in handler._sent_body
            assert "dependencies" in handler._sent_body
            assert handler._sent_body["healthy"] is True

    def test_unhealthy_returns_json_503(self) -> None:
        """GET /api/health/details when unhealthy returns HTTP 503 with JSON body."""
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
            handler = MockApiHandler()
            handle_health_details(handler)

            # Must return 503 when unhealthy
            assert handler._sent_code == 503, f"Expected 503, got {handler._sent_code}"

            # Must return JSON body
            assert_json_response(handler, expected_code=503)
            assert handler._sent_body is not None

            # Must have unhealthy status
            assert handler._sent_body["healthy"] is False
            assert handler._sent_body["primary_failure_class"] != ""

    def test_provider_unavailable_returns_structured_json(self) -> None:
        """Provider unavailable still returns structured JSON, not HTML/text."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={
                "available": False,
                "error": "provider_unavailable",
                "phase": "unknown",
                "error_class": "provider_unavailable",
            },
        ):
            handler = MockApiHandler()
            handle_health_details(handler)

            # Must return JSON, not HTML
            assert handler._sent_code in (200, 503)
            assert_json_response(handler)
            assert handler._sent_body is not None
            assert "healthy" in handler._sent_body

            # Must not contain HTML markers
            assert_no_html_in_response(handler)

    def test_evaluator_exception_returns_json_not_html(self) -> None:
        """Evaluator exception returns JSON error, not HTML."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        with patch(
            "k8s_diag_agent.ui.api_health_details._unsafe_evaluate_backend_health",
            side_effect=RuntimeError("Unexpected error"),
        ):
            handler = MockApiHandler()
            handle_health_details(handler)

            # Must still return JSON, not crash
            assert handler._sent_code in (200, 503)
            assert_json_response(handler)


class TestHealthDetailsPreflightContract:
    """Tests for provider preflight diagnostic content in health details."""

    def test_health_details_has_required_preflight_fields(self) -> None:
        """Health details must have fields consumed by provider preflight."""
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

            # Provider preflight expects these fields
            assert_json_response(handler, expected_body_keys=["healthy", "primary_failure_class", "dependencies"])
            assert handler._sent_body is not None

            # Dependencies should contain diagnosis_provider
            deps = handler._sent_body.get("dependencies", [])
            provider_dep = next(
                (d for d in deps if d.get("dependency_name") == "diagnosis_provider"),
                None,
            )
            assert provider_dep is not None, "diagnosis_provider dependency must be present"
            assert "status" in provider_dep
            assert "reason_code" in provider_dep

    def test_health_details_on_provider_failure_has_failure_class(self) -> None:
        """Provider failure must set primary_failure_class for preflight."""
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
            handler = MockApiHandler()
            handle_health_details(handler)

            # primary_failure_class must be set for preflight classification
            assert handler._sent_body is not None
            failure_class = handler._sent_body.get("primary_failure_class", "")
            assert failure_class != "", "primary_failure_class must be set on provider failure"
            assert "provider" in failure_class.lower() or "connection" in failure_class.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
