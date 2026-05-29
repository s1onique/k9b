"""HTTP-level route security tests for static and artifact serving.

This module exercises the actual HTTP routes that operators/clients would use,
proving that security behavior is preserved through real request parsing,
URL decoding, and routing.

Routes tested:
- GET /artifact?path=... - artifact serving
- GET /... (other paths) - static asset serving / SPA fallback

Invariant: No request can cause the server to read or serve a file outside an
explicitly allowed root and allowlist.

Test corpus reuses the canonical payload corpus from server_static_test_support.py.
HTTP test harness is provided by server_http_test_support.py (via pytest_plugins).
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from tests.security.server_static_test_support import (
    ABSOLUTE_PATH_PAYLOADS,
    ENCODED_TRAVERSAL_PAYLOADS,
    NULL_BYTE_PAYLOADS,
    TRAVERSAL_PAYLOADS,
)

pytest_plugins = ("tests.security.server_http_test_support",)

# =============================================================================
# TESTS: ARTIFACT ROUTE - /artifact?path=...
# =============================================================================


class TestArtifactHTTPRoute:
    """HTTP-level tests for the /artifact route.

    These tests exercise the artifact serving endpoint through real HTTP requests,
    proving security behavior is preserved through URL parsing and routing.
    """

    def test_valid_artifact_served_via_http(self, http_harness: list) -> None:
        """Valid artifact path within runs_dir should be served successfully via HTTP."""
        harness, port, canary = http_harness
        status, body, _ = harness.request("GET", "/artifact?path=external-analysis/run-test-assessment-001.json")

        assert status == 200, f"Expected 200 for valid artifact, got {status}"
        assert b"valid artifact" in body

    def test_missing_path_returns_400(self, http_harness: list) -> None:
        """Missing path parameter should return 400 via HTTP."""
        harness, port, canary = http_harness
        status, body, _ = harness.request("GET", "/artifact")

        assert status == 400, f"Expected 400 for missing path, got {status}"

    def test_basic_traversal_rejected_via_http(self, http_harness: list) -> None:
        """Basic path traversal must be rejected via HTTP."""
        harness, port, canary = http_harness

        for payload in TRAVERSAL_PAYLOADS[:3]:  # Test subset for HTTP layer
            status, body, _ = harness.request("GET", f"/artifact?path={quote(payload)}")

            # Must be rejected, not 200
            assert status != 200, (
                f"Traversal payload {payload!r} was not rejected via HTTP: status={status}"
            )
            # Must not return canary content
            assert canary.get_canary_content().encode() not in body, (
                f"Canary content leaked via HTTP for payload {payload!r}"
            )

    def test_encoded_traversal_rejected_via_http(self, http_harness: list) -> None:
        """URL-encoded traversal patterns must be rejected via HTTP.

        This tests the real-world case where clients send %2e%2e%2f directly
        in the URL, exercising the same code path as browsers and API clients.
        """
        harness, port, canary = http_harness

        for payload in ENCODED_TRAVERSAL_PAYLOADS[:4]:  # Test key encoded patterns
            status, body, _ = harness.request("GET", f"/artifact?path={payload}")

            # Must be rejected
            assert status in (400, 403, 404), (
                f"Encoded traversal {payload!r} was not rejected via HTTP: status={status}"
            )
            # Must not return canary content
            assert canary.get_canary_content().encode() not in body, (
                f"Canary leaked via HTTP for encoded payload {payload!r}"
            )

    def test_double_encoded_traversal_rejected_via_http(self, http_harness: list) -> None:
        """Double-encoded traversal (%252e%252e%252f) must be rejected via HTTP.

        This tests defense in depth: the server should reject double-encoded
        traversal even though single-encoding should catch it first.
        """
        harness, port, canary = http_harness

        # %252e = encoded %2e = encoded .
        # This tests that URL decoding is handled correctly
        status, body, _ = harness.request("GET", "/artifact?path=%252e%252e%252fetc%252fpasswd")

        # Should be rejected (400 for hostile component, or 404 for not found)
        assert status in (400, 403, 404), (
            f"Double-encoded traversal was not rejected via HTTP: status={status}"
        )
        # Must not contain canary or sensitive paths
        canary_content = canary.get_canary_content().encode()
        assert canary_content not in body
        assert b"/etc/passwd" not in body

    def test_absolute_paths_rejected_via_http(self, http_harness: list) -> None:
        """Absolute path attempts must be rejected via HTTP."""
        harness, port, canary = http_harness

        for payload in ABSOLUTE_PATH_PAYLOADS[:3]:  # Test subset
            status, body, _ = harness.request("GET", f"/artifact?path={quote(payload)}")

            assert status in (400, 403, 404), (
                f"Absolute path {payload!r} was not rejected via HTTP: status={status}"
            )
            assert canary.get_canary_content().encode() not in body

    def test_null_bytes_rejected_via_http(self, http_harness: list) -> None:
        """Null byte injection must be rejected via HTTP."""
        harness, port, canary = http_harness

        for payload in NULL_BYTE_PAYLOADS[:2]:  # Test subset
            # Null bytes are URL-encoded in query strings
            safe_payload = payload.replace("\x00", "%00")
            status, body, _ = harness.request("GET", f"/artifact?path={safe_payload}")

            assert status in (400, 403, 404), (
                f"Null byte payload {payload!r} was not rejected via HTTP: status={status}"
            )

    def test_canary_not_accessible_via_http_traversal(self, http_harness: list) -> None:
        """Canary files outside root must not be accessible via HTTP traversal."""
        harness, port, canary = http_harness

        canary_paths = canary.get_all_canary_paths()
        if not canary_paths:
            pytest.skip("No canary files created")

        # Try to access each canary file via traversal
        for canary_path in canary_paths[:3]:  # Test subset
            if not canary_path.is_file():
                continue

            # Construct traversal path: ../<canary-dir-name>/<filename>
            runs_parent = canary_path.resolve().parents[1]
            relative_to_runs = canary_path.relative_to(runs_parent)
            traversal = str(relative_to_runs).replace(
                runs_parent.name, "..", 1
            )

            status, body, _ = harness.request("GET", f"/artifact?path={quote(traversal)}")

            # Must not serve canary content
            assert canary.get_canary_content().encode() not in body, (
                f"Canary file {canary_path.name!r} was accessible via HTTP traversal {traversal!r}"
            )

    def test_no_host_path_leak_in_artifact_response(self, http_harness: list) -> None:
        """Artifact error responses must not leak absolute host paths."""
        harness, port, canary = http_harness

        status, body, _ = harness.request("GET", "/artifact?path=../etc/passwd")
        response_text = body.decode("utf-8", errors="replace")

        # Must not contain absolute paths
        assert str(canary.allowed_root.resolve()) not in response_text, (
            "Absolute host path leaked in artifact response"
        )
        # Must not contain sensitive path patterns
        assert "/etc/" not in response_text
        assert "/home/" not in response_text
        assert "/tmp/" not in response_text

    def test_dot_segment_encoded_variants(self, http_harness: list) -> None:
        """Dot-segment normalization variants must be rejected via HTTP.

        Tests: %2e%2e%2f, %2e%2e/, %2e.
        """
        harness, port, canary = http_harness

        variants = [
            "%2e%2e%2fetc%2fpasswd",  # Encoded ../
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # Triple encoded
            "..%2f..%2f..%2fetc%2fpasswd",  # Partial encoding
        ]

        for payload in variants:
            status, body, _ = harness.request("GET", f"/artifact?path={payload}")

            assert status in (400, 403, 404), (
                f"Dot-segment variant {payload!r} was not rejected via HTTP: status={status}"
            )
            assert canary.get_canary_content().encode() not in body


# =============================================================================
# TESTS: STATIC ROUTE - GET /* (non-API paths)
# =============================================================================


class TestStaticHTTPRoute:
    """HTTP-level tests for static asset serving routes.

    These tests exercise the static file serving endpoint through real HTTP requests,
    proving that:
    1. Valid static files are served correctly
    2. Traversal attempts fall back to index.html (SPA behavior)
    3. Canary content is never served even through static fallback
    4. No absolute host paths leak in responses
    """

    def test_valid_static_file_served_via_http(self, http_harness: list) -> None:
        """Valid static file should be served via HTTP."""
        harness, port, canary = http_harness
        status, body, _ = harness.request("GET", "/assets/app.js")

        assert status == 200, f"Expected 200 for valid static file, got {status}"
        assert b"// app" in body

    def test_root_path_serves_index(self, http_harness: list) -> None:
        """Root path should serve index.html via HTTP."""
        harness, port, canary = http_harness
        status, body, _ = harness.request("GET", "/")

        assert status == 200
        assert b"<h1>Welcome</h1>" in body

    def test_traversal_returns_index_fallback(self, http_harness: list) -> None:
        """Path traversal in static route should return index.html via HTTP.

        This is the expected SPA fallback behavior: malicious paths should
        not serve attacker-targeted files, but may return index.html.
        """
        harness, port, canary = http_harness

        for payload in TRAVERSAL_PAYLOADS[:3]:
            status, body, _ = harness.request("GET", f"/{quote(payload)}")

            # Either 200 with index.html content OR rejected (not serving traversal target)
            if status == 200:
                assert b"<h1>Welcome</h1>" in body, (
                    f"Static route returned 200 but not index.html for {payload!r}"
                )
            # Must not serve canary content
            assert canary.get_canary_content().encode() not in body, (
                f"Canary content leaked via static route for payload {payload!r}"
            )

    def test_encoded_traversal_static_behavior(self, http_harness: list) -> None:
        """Encoded traversal in static route must not serve attacker-targeted files."""
        harness, port, canary = http_harness

        for payload in ENCODED_TRAVERSAL_PAYLOADS[:3]:
            status, body, _ = harness.request("GET", f"/{payload}")

            # If 200, must be index.html content (SPA fallback)
            # Must never serve canary or sensitive files
            assert canary.get_canary_content().encode() not in body, (
                f"Canary leaked via static route for encoded payload {payload!r}"
            )
            assert b"/etc/passwd" not in body
            assert b"password" not in body.lower()

    def test_absolute_path_static_behavior(self, http_harness: list) -> None:
        """Absolute paths in static route must not serve attacker-targeted files."""
        harness, port, canary = http_harness

        status, body, _ = harness.request("GET", "/etc/passwd")

        # Must not serve /etc/passwd content
        assert b"root:" not in body  # /etc/passwd starts with root:
        assert canary.get_canary_content().encode() not in body

    def test_no_host_path_leak_in_static_response(self, http_harness: list) -> None:
        """Static error/fallback responses must not leak absolute host paths."""
        harness, port, canary = http_harness

        status, body, _ = harness.request("GET", "/../etc/passwd")
        response_text = body.decode("utf-8", errors="replace")

        # Must not contain absolute paths
        assert str(canary.allowed_root.resolve()) not in response_text, (
            "Absolute host path leaked in static response"
        )
        assert "/tmp/" not in response_text
        assert "/etc/" not in response_text
