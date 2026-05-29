"""Path traversal regression tests for server_static.py.

This module tests the security regression corpus for path traversal bug class
in the artifact and static file serving endpoints.

Invariant: No request can cause the server to read or serve a file outside an
explicitly allowed root and allowlist.

Test corpus covers:
- Path traversal (..)
- Encoded traversal (%2e%2e%2f, ..%2f, etc.)
- Absolute paths
- Null bytes
- Sensitive file probes
- Dot-segment normalization
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.security.server_static_test_support import (
    ABSOLUTE_PATH_PAYLOADS,
    DOT_SEGMENT_PAYLOADS,
    NULL_BYTE_PAYLOADS,
    SENSITIVE_FILE_PAYLOADS,
    TRAVERSAL_PAYLOADS,
    MockHandler,
    SecurityCanaryFiles,
)

# =============================================================================
# TESTS: serve_artifact() PATH TRAVERSAL REJECTION
# =============================================================================


class TestServeArtifactPathTraversal:
    """Tests for serve_artifact() rejecting path traversal attempts.

    The serve_artifact function must:
    1. Reject any path that escapes the runs_dir root
    2. Return 400 for malformed paths
    3. Return 404 for valid but non-existent paths within root
    4. Never serve content from outside the allowed root
    5. Never leak absolute paths in responses
    """

    @pytest.fixture(autouse=True)
    def setup_test_env(self, tmp_path: Path) -> None:
        """Set up test environment with runs_dir and canary files."""
        self.runs_dir = tmp_path / "runs"
        self.runs_dir.mkdir(parents=True)
        self.health_dir = self.runs_dir / "health"
        self.health_dir.mkdir(parents=True)
        self.ea_dir = self.runs_dir / "external-analysis"
        self.ea_dir.mkdir(parents=True)

        # Create a valid artifact inside the root
        self.valid_artifact = self.ea_dir / "run-test-assessment-001.json"
        self.valid_artifact.write_text(
            '{"findings": [], "summary": "valid artifact"}',
            encoding="utf-8",
        )

        # Set up canary files outside the root
        self.canary = SecurityCanaryFiles(self.runs_dir)

        yield

        self.canary.cleanup()

    def _call_serve_artifact(self, path: str) -> MockHandler:
        """Call serve_artifact with the given path."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        serve_artifact(handler, f"path={path}")
        return handler

    def test_valid_artifact_is_served(self) -> None:
        """Valid artifact path within runs_dir should be served successfully."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = "path=external-analysis/run-test-assessment-001.json"
        serve_artifact(handler, query)

        assert handler._response_status == 200
        assert b"valid artifact" in handler._response_body

    def test_missing_path_returns_400(self) -> None:
        """Missing path parameter should return 400."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        serve_artifact(handler, "")  # Empty query

        assert handler._response_status == 400
        assert "path required" in handler._response_body.decode("utf-8").lower()

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_traversal_payloads_rejected(self, payload: str) -> None:
        """Basic path traversal patterns must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        # Must be rejected (400) or not found (404), not success (200)
        assert handler._response_status in (
            400,
            403,
            404,
        ), f"Traversal payload {payload!r} was not rejected: status={handler._response_status}"
        # Must not return canary content
        assert self.canary.get_canary_content().encode() not in handler._response_body, (
            f"Canary content leaked for payload {payload!r}"
        )

    @pytest.mark.parametrize("payload", ABSOLUTE_PATH_PAYLOADS)
    def test_absolute_paths_rejected(self, payload: str) -> None:
        """Absolute path attempts must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (
            400,
            403,
            404,
        ), f"Absolute path {payload!r} was not rejected"
        assert self.canary.get_canary_content().encode() not in handler._response_body

    @pytest.mark.parametrize("payload", NULL_BYTE_PAYLOADS)
    def test_null_byte_payloads_rejected(self, payload: str) -> None:
        """Null byte injection attempts must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        # Null bytes in query strings are URL-encoded
        safe_payload = payload.replace("\x00", "%00")
        query = f"path={safe_payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (
            400,
            403,
            404,
        ), f"Null byte payload {payload!r} was not rejected"

    @pytest.mark.parametrize("payload", SENSITIVE_FILE_PAYLOADS)
    def test_sensitive_files_not_served(self, payload: str) -> None:
        """Sensitive files outside the root must not be served."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (
            400,
            403,
            404,
        ), f"Sensitive file probe {payload!r} was not rejected"
        # Verify canary content is not leaked
        assert self.canary.get_canary_content().encode() not in handler._response_body, (
            f"Canary leaked for sensitive file probe {payload!r}"
        )

    @pytest.mark.parametrize("payload", DOT_SEGMENT_PAYLOADS)
    def test_dot_segment_normalization_attacks_rejected(self, payload: str) -> None:
        """Dot-segment normalization attacks must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (
            400,
            403,
            404,
        ), f"Dot-segment attack {payload!r} was not rejected"

    def test_no_path_leak_in_response(self) -> None:
        """Responses must not leak absolute host paths."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = "path=../etc/passwd"
        serve_artifact(handler, query)

        response_text = handler._response_body.decode("utf-8", errors="replace")
        # The response should not contain absolute paths
        assert str(
            self.runs_dir.resolve()
        ) not in response_text, "Absolute path leaked in response"
        # Should not contain /etc/passwd style paths
        assert "/etc/" not in response_text, "Path leaked in response"
        assert "/home/" not in response_text, "Path leaked in response"

    def test_canary_files_not_accessible(self) -> None:
        """Canary files outside the root must not be accessible."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        # Try to access each canary file
        for canary_path in self.canary.get_all_canary_paths():
            if canary_path.is_file():
                # Construct path relative to runs_dir using traversal
                relative_to_runs = canary_path.relative_to(self.runs_dir.parent)
                traversal_attempt = str(relative_to_runs).replace(
                    self.runs_dir.parent.name, "..", 1
                )

                handler = MockHandler(self.runs_dir, self.canary)
                serve_artifact(handler, f"path={traversal_attempt}")

                # Must not serve canary content
                assert self.canary.get_canary_content().encode() not in handler._response_body, (
                    f"Canary file {canary_path.name!r} was accessible via {traversal_attempt!r}"
                )


# =============================================================================
# TESTS: serve_static() PATH TRAVERSAL REJECTION
# =============================================================================


class TestServeStaticPathTraversal:
    """Tests for serve_static() path traversal security.

    serve_static() serves files from a static_dir. It must prevent
    traversal out of the static directory.
    """

    @pytest.fixture(autouse=True)
    def setup_static_env(self, tmp_path: Path) -> None:
        """Set up test environment with static_dir and canary files."""
        self.static_dir = tmp_path / "static"
        self.static_dir.mkdir(parents=True)

        # Create valid static content
        (self.static_dir / "index.html").write_text("<h1>Welcome</h1>", encoding="utf-8")
        (self.static_dir / "assets").mkdir()
        (self.static_dir / "assets" / "app.js").write_text("// app", encoding="utf-8")

        # Set up canary files outside static_dir
        self.canary = SecurityCanaryFiles(self.static_dir)

        yield

        self.canary.cleanup()

    def _call_serve_static(self, route: str) -> Path | None:
        """Call serve_static with the given route."""
        from unittest.mock import MagicMock, patch

        from k8s_diag_agent.ui.server_static import serve_static

        handler = MagicMock()
        handler.static_dir = self.static_dir
        handler._send_text = lambda status, msg: None
        handler.send_response = lambda code: None
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        # Track what file would be served
        served_file = {"path": None}

        def mock_send_file(h: Any, path: Path) -> None:
            served_file["path"] = path

        with patch("k8s_diag_agent.ui.server_static.send_file", mock_send_file):
            serve_static(handler, route)

        return served_file["path"]

    def test_valid_static_route_served(self) -> None:
        """Valid static routes should serve the correct file."""
        served = self._call_serve_static("index.html")
        assert served == self.static_dir / "index.html"

    def test_traversal_returns_index_fallback(self) -> None:
        """Path traversal in static route should return index.html fallback."""
        served = self._call_serve_static("../etc/passwd")
        # Should fall back to index.html, not serve the traversal target
        assert served == self.static_dir / "index.html"

    def test_absolute_path_returns_index_fallback(self) -> None:
        """Absolute paths should return index.html fallback."""
        served = self._call_serve_static("/etc/passwd")
        assert served == self.static_dir / "index.html"

    def test_sibling_directory_not_accessible(self) -> None:
        """Sibling directories must not be accessible via static route.

        This tests the sibling-prefix vulnerability case where:
        - static_dir = /tmp/static
        - sibling = /tmp/static-evil

        A naive string-prefix check would incorrectly serve files from /tmp/static-evil
        because '/tmp/static-evil/file.txt' starts with '/tmp/static'.

        Using Path.relative_to() correctly rejects this by validating that the resolved
        path is actually contained within static_root.

        Note: The request uses '../' traversal to actually resolve to the sibling directory.
        Without traversal, serve_static() would just look for a nested 'static-evil' directory
        under static_root, which doesn't exercise the sibling-prefix escape.
        """
        import shutil

        # Create a sibling directory at the same level as static_dir
        sibling_dir = self.static_dir.parent / f"{self.static_dir.name}-evil"
        sibling_dir.mkdir(parents=True, exist_ok=True)

        # Create a file in the sibling directory that could be mistaken by string-prefix check
        evil_file = sibling_dir / "secret.txt"
        evil_file.write_text("SIBLING_CANARY_CONTENT", encoding="utf-8")

        try:
            # Use '../' traversal to resolve to the sibling directory.
            # This is the critical path that the old string-prefix check would have missed:
            #   candidate = static_root / "../static-evil/secret.txt" -> resolves to /tmp/static-evil/secret.txt
            #   Old check: '/tmp/static-evil/secret.txt'.startswith('/tmp/static') = True (WRONG!)
            #   New check: Path.relative_to() raises ValueError correctly (CORRECT!)
            served = self._call_serve_static(f"../{self.static_dir.name}-evil/secret.txt")

            # Must fall back to index.html, not serve the sibling file
            assert served == self.static_dir / "index.html", (
                f"Sibling directory was accessible: {served}"
            )
        finally:
            # Cleanup
            if sibling_dir.exists():
                shutil.rmtree(sibling_dir)
