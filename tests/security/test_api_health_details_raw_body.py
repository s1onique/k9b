"""Regression tests for /api/health/details raw HTTP response body.

These tests prove that the route-level response is exactly one JSON object
with no trailing data. This catches:
- Concatenated JSON objects (e.g., {}{})
- Extra data after JSON document
- HTML or text corruption in response body

Tests use a module-scoped HTTP server to reduce repeated setup overhead.
"""

from __future__ import annotations

import json

import pytest

pytest_plugins = ("tests.security.conftest_http_shared",)


class TestHealthDetailsRawBodyContract:
    """Regression tests proving /api/health/details returns exactly one JSON object."""

    def test_health_details_returns_single_json_object_no_trailing_data(
        self, http_harness_no_auth_module: list
    ) -> None:
        """Raw HTTP response must be exactly one JSON object, no trailing data.

        This is a regression test for the case where a handler might append
        extra data after the JSON document (e.g., concatenated objects).
        Python's json.loads treats extra data after a valid JSON document as
        an error (json.JSONDecodeError: Extra data).

        Note: The health endpoint may return 200 (healthy) or 503 (unhealthy)
        depending on provider availability in the test harness. We accept both.
        """
        harness, port, _ = http_harness_no_auth_module

        # Make actual HTTP request
        status, body, _ = harness.request("GET", "/api/health/details")

        # Should return 200 (healthy) or 503 (unhealthy - provider may not be available in test harness)
        assert status in (200, 503), f"Expected 200 or 503, got {status}"

        # Body must be non-empty bytes
        assert body, "Response body must not be empty"
        assert isinstance(body, bytes), f"Expected bytes, got {type(body)}"

        # Decode to string
        body_str = body.decode("utf-8").strip()

        # Must be valid JSON
        parsed = json.loads(body_str)
        assert isinstance(parsed, dict), f"Expected JSON object, got {type(parsed)}"

        # Must be exactly one JSON document - json.loads must consume entire string
        # This catches concatenated JSON (e.g., "{}{}") which causes "Extra data" error
        try:
            json.loads(body_str)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"Response body is not exactly one JSON object. "
                f"JSONDecodeError: {e}. "
                f"Body preview (first 200 chars): {body_str[:200]!r}"
            )

    def test_health_details_json_has_required_fields(
        self, http_harness_no_auth_module: list
    ) -> None:
        """Raw HTTP response must contain all required fields for provider preflight.

        Note: Accept both 200 and 503 status codes as the test harness may not
        have a fully configured provider.
        """
        harness, port, _ = http_harness_no_auth_module

        status, body, headers = harness.request("GET", "/api/health/details")

        assert status in (200, 503), f"Expected 200 or 503, got {status}"
        assert body, "Response body must not be empty"

        body_str = body.decode("utf-8").strip()
        parsed = json.loads(body_str)

        # Required fields for provider preflight
        assert "healthy" in parsed, "Response must have 'healthy' field"
        assert "primary_failure_class" in parsed, "Response must have 'primary_failure_class' field"
        assert "dependencies" in parsed, "Response must have 'dependencies' field"
        assert isinstance(parsed["dependencies"], list), "'dependencies' must be a list"

    def test_health_details_content_type_is_json(
        self, http_harness_no_auth_module: list
    ) -> None:
        """Response Content-Type must be application/json."""
        harness, port, _ = http_harness_no_auth_module

        _, body, headers = harness.request("GET", "/api/health/details")

        # Content-Type header should indicate JSON
        content_type = headers.get("Content-Type", "")
        assert "application/json" in content_type.lower(), (
            f"Expected Content-Type: application/json, got {content_type!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
