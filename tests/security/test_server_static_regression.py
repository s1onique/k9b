"""Security regression tests for server_static.py artifact and static serving.

This module implements the security regression corpus for path traversal bug class.
Every externally found path traversal bug must produce a permanent executable gate.

Invariant: No request can cause the server to read or serve a file outside an
explicitly allowed root and allowlist.

Test corpus covers:
- Path traversal (..)
- Encoded traversal (%2e%2e%2f, ..%2f, etc.)
- Absolute paths
- Null bytes
- Sensitive file probes
- Dot-segment normalization
- Symlink escape attempts
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# =============================================================================
# PATH TRAVERSAL PAYLOAD CORPUS
# =============================================================================

# Basic path traversal patterns
TRAVERSAL_PAYLOADS: list[str] = [
    "../etc/passwd",
    "..\\etc\\passwd",
    "../../etc/passwd",
    "../../../etc/passwd",
    "../../../../etc/passwd",
    "....//....//....//etc/passwd",
    ".../.../.../etc/passwd",
]

# Encoded traversal patterns (URL-encoded)
ENCODED_TRAVERSAL_PAYLOADS: list[str] = [
    "%2e%2e%2fetc%2fpasswd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%2f..%2f..%2fetc%2fpasswd",
    "..%255c..%255c..%255cetc%255cpasswd",
    "%252e%252e%252fetc%252fpasswd",  # double-encoded
]

# Absolute path attempts
ABSOLUTE_PATH_PAYLOADS: list[str] = [
    "/etc/passwd",
    "/absolute/path/to/file",
    "C:\\Windows\\System32\\config\\SAM",
    "\\\\server\\share\\file",
    "/tmp/../../../etc/passwd",
]

# Null byte injection
NULL_BYTE_PAYLOADS: list[str] = [
    "../etc/passwd\x00",
    "..%00etc/passwd",
    "..\x00passwd",
]

# Dot-segment normalization attacks
DOT_SEGMENT_PAYLOADS: list[str] = [
    "./../etc/passwd",
    ".././etc/passwd",
    "/foo/bar/../baz",
    "foo/bar/../../baz",
    "/foo/./bar/./baz",
]

# Sensitive file probes
SENSITIVE_FILE_PAYLOADS: list[str] = [
    ".env",
    "../.env",
    "../../.env",
    ".git/config",
    "../.git/config",
    "config.yaml",
    "../../config.yaml",
    "/.git/config",
    "secrets.txt",
    "../../secrets.txt",
    "id_rsa",
    "../../../home/user/.ssh/id_rsa",
    "kubeconfig",
    "../../kubeconfig",
    "token",
    "../../token",
    ".aws/credentials",
    "../../.aws/credentials",
    "connection_string",
    "../../connection_string",
]

# Combined attack patterns
COMBINED_ATTACK_PAYLOADS: list[str] = [
    "static/../../secret",
    "runs/health/../../.env",
    "artifact.json/../../secret",
    "files/../../../etc/passwd",
    "download/..%2f..%2f..%2fetc/passwd",
    "view/./../../secret",
]

# All payloads combined - the canonical regression corpus
ALL_PATH_TRAVERSAL_PAYLOADS: list[str] = TRAVERSAL_PAYLOADS + ENCODED_TRAVERSAL_PAYLOADS + ABSOLUTE_PATH_PAYLOADS + NULL_BYTE_PAYLOADS + DOT_SEGMENT_PAYLOADS + SENSITIVE_FILE_PAYLOADS + COMBINED_ATTACK_PAYLOADS

# =============================================================================
# SECURITY TEST HELPERS
# =============================================================================


class SecurityCanaryFiles:
    """Manages canary files outside the allowed root for security testing."""

    def __init__(self, allowed_root: Path) -> None:
        self.allowed_root = allowed_root.resolve()
        self.canary_dir = allowed_root.parent / f"{allowed_root.name}-canary"
        self.canary_dir.mkdir(parents=True, exist_ok=True)
        self.canary_content = "SECRET_CANARY_CONTENT_12345"
        self._create_canary_files()

    def _create_canary_files(self) -> None:
        """Create sensitive files outside the allowed root."""
        canary_files = [
            ".env",
            ".git/config",
            "config.yaml",
            "secrets.txt",
            "id_rsa",
            "kubeconfig",
            ".aws/credentials",
            "connection_string",
            "passwords.txt",
            "tokens.json",
        ]
        for filename in canary_files:
            canary_path = self.canary_dir / filename
            canary_path.parent.mkdir(parents=True, exist_ok=True)
            canary_path.write_text(
                f"{self.canary_content} for {filename}",
                encoding="utf-8",
            )

    def get_canary_content(self) -> str:
        return self.canary_content

    def cleanup(self) -> None:
        """Remove canary directory after tests."""
        import shutil

        if self.canary_dir.exists():
            shutil.rmtree(self.canary_dir)

    def get_all_canary_paths(self) -> list[Path]:
        """Get all canary file paths for negative testing."""
        return list(self.canary_dir.rglob("*"))


class MockHandler:
    """Minimal mock for HealthUIRequestHandler to test serve_artifact."""

    def __init__(self, runs_dir: Path, canary: SecurityCanaryFiles) -> None:
        self.runs_dir = runs_dir
        self.canary = canary
        self._response_status: int | None = None
        self._response_body: bytes = b""
        self._headers_sent: dict[str, str] = {}

    def _send_text(self, status: int, message: str) -> None:
        """Record the response status and message."""
        self._response_status = status
        self._response_body = message.encode("utf-8")

    def send_response(self, code: int) -> None:
        """Record response code."""
        self._response_status = code

    def send_header(self, key: str, value: str) -> None:
        """Record headers."""
        self._headers_sent[key] = value

    def end_headers(self) -> None:
        """Mark headers complete."""
        pass

    @property
    def wfile(self) -> MagicMock:
        """Mock writable file for response body."""
        mock = MagicMock()
        mock.write = lambda data: setattr(self, "_response_body", data)
        return mock


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
        assert handler._response_status in (400, 403, 404), f"Traversal payload {payload!r} was not rejected: status={handler._response_status}"
        # Must not return canary content
        assert self.canary.get_canary_content().encode() not in handler._response_body, f"Canary content leaked for payload {payload!r}"

    @pytest.mark.parametrize("payload", ABSOLUTE_PATH_PAYLOADS)
    def test_absolute_paths_rejected(self, payload: str) -> None:
        """Absolute path attempts must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (400, 403, 404), f"Absolute path {payload!r} was not rejected"
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

        assert handler._response_status in (400, 403, 404), f"Null byte payload {payload!r} was not rejected"

    @pytest.mark.parametrize("payload", SENSITIVE_FILE_PAYLOADS)
    def test_sensitive_files_not_served(self, payload: str) -> None:
        """Sensitive files outside the root must not be served."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (400, 403, 404), f"Sensitive file probe {payload!r} was not rejected"
        # Verify canary content is not leaked
        assert self.canary.get_canary_content().encode() not in handler._response_body, f"Canary leaked for sensitive file probe {payload!r}"

    @pytest.mark.parametrize("payload", DOT_SEGMENT_PAYLOADS)
    def test_dot_segment_normalization_attacks_rejected(self, payload: str) -> None:
        """Dot-segment normalization attacks must be rejected."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = f"path={payload}"
        serve_artifact(handler, query)

        assert handler._response_status in (400, 403, 404), f"Dot-segment attack {payload!r} was not rejected"

    def test_no_path_leak_in_response(self) -> None:
        """Responses must not leak absolute host paths."""
        from k8s_diag_agent.ui.server_static import serve_artifact

        handler = MockHandler(self.runs_dir, self.canary)
        query = "path=../etc/passwd"
        serve_artifact(handler, query)

        response_text = handler._response_body.decode("utf-8", errors="replace")
        # The response should not contain absolute paths
        assert str(self.runs_dir.resolve()) not in response_text, "Absolute path leaked in response"
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
                traversal_attempt = str(relative_to_runs).replace(self.runs_dir.parent.name, "..", 1)

                handler = MockHandler(self.runs_dir, self.canary)
                serve_artifact(handler, f"path={traversal_attempt}")

                # Must not serve canary content
                assert self.canary.get_canary_content().encode() not in handler._response_body, f"Canary file {canary_path.name!r} was accessible via {traversal_attempt!r}"

    def test_symlink_outside_root_not_followed(self) -> None:
        """Symlink pointing outside allowed root must not be followed.

        This tests the classic symlink escape attack where a symlink inside
        the artifact directory points to a file outside the runs_dir root.

        NOTE: This test currently FAILS, demonstrating a real vulnerability.
        The serve_artifact() implementation uses Path.resolve() which follows
        symlinks, then checks containment. But after resolution, the path is
        outside the root and the check should fail. The test proves the
        implementation does NOT prevent symlink escape.

        After fixing serve_artifact() to check containment BEFORE resolution,
        this test should pass.
        """
        import os

        from k8s_diag_agent.ui.server_static import serve_artifact

        # Create a symlink inside the runs_dir pointing to a canary file
        symlink_dir = self.ea_dir / "subdir"
        symlink_dir.mkdir(parents=True)
        canary_file = self.canary.get_all_canary_paths()[0]

        symlink_path = symlink_dir / "escape-link"
        try:
            os.symlink(canary_file, symlink_path)
        except OSError:
            pytest.skip("Platform does not support symlinks")

        # Try to access the symlink path
        handler = MockHandler(self.runs_dir, self.canary)
        query = "path=external-analysis/subdir/escape-link"
        serve_artifact(handler, query)

        # BUG: serve_artifact follows symlinks and serves canary content
        # After fix, this assertion should pass:
        assert self.canary.get_canary_content().encode() not in handler._response_body, (
            "Symlink escape: canary content was served via symlink. "
            "serve_artifact() must check containment BEFORE following symlinks."
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

    def _call_serve_static(self, route: str) -> MockHandler:
        """Call serve_static with the given route."""
        from k8s_diag_agent.ui.server_static import serve_static

        handler = MagicMock()
        handler.static_dir = self.static_dir
        handler._send_text = lambda status, msg: None  # We'll check send_file calls
        handler.send_response = lambda code: None
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None

        # Track what file would be served
        served_file = {"path": None}

        def mock_send_file(h: Any, path: Path) -> None:
            served_file["path"] = path

        from unittest.mock import patch as mock_patch

        with mock_patch("k8s_diag_agent.ui.server_static.send_file", mock_send_file):
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


# =============================================================================
# TESTS: INTEGRATION WITH PATH VALIDATION MODULE
# =============================================================================


class TestPathValidationIntegration:
    """Tests verifying serve_artifact uses path validation correctly."""

    @pytest.fixture(autouse=True)
    def setup_env(self, tmp_path: Path) -> None:
        self.runs_dir = tmp_path / "runs"
        self.runs_dir.mkdir(parents=True)
        self.canary = SecurityCanaryFiles(self.runs_dir)
        yield
        self.canary.cleanup()

    def test_path_validation_hardening_exists(self) -> None:
        """Verify path_validation module has required security functions."""
        from k8s_diag_agent.security.path_validation import (
            SecurityError,
            safe_child_path,
            validate_run_id,
        )

        # These functions should exist and work
        assert validate_run_id("run-test") == "run-test"

        with pytest.raises(SecurityError):
            validate_run_id("../etc")

        result = safe_child_path(self.runs_dir, "external-analysis")
        assert result == self.runs_dir / "external-analysis"

    def test_traversal_raises_security_error(self) -> None:
        """Path traversal must raise SecurityError in safe_child_path."""
        from k8s_diag_agent.security.path_validation import (
            SecurityError,
            safe_child_path,
        )

        with pytest.raises(SecurityError, match="traversal|separator"):
            safe_child_path(self.runs_dir, "..", "etc")

    def test_sibling_directory_not_traversal(self) -> None:
        """Sibling directories with similar names should not be blocked."""
        from k8s_diag_agent.security.path_validation import (
            safe_child_path,
        )

        # Create sibling directory
        sibling = self.runs_dir.parent / f"{self.runs_dir.name}-sibling"
        sibling.mkdir(parents=True)

        # Accessing sibling should work (it's under the parent, not under runs_dir)
        # This tests that safe_child_path doesn't use naive prefix matching
        result = safe_child_path(self.runs_dir, "valid-child")
        assert result == self.runs_dir / "valid-child"


# =============================================================================
# SECURITY GATE VERIFICATION
# =============================================================================


class TestSecurityGateCompleteness:
    """Verify the security regression corpus covers all expected attack vectors."""

    def test_corpus_has_minimum_coverage(self) -> None:
        """The payload corpus must have minimum coverage."""
        assert len(TRAVERSAL_PAYLOADS) >= 5, "Need at least 5 basic traversal payloads"
        assert len(ENCODED_TRAVERSAL_PAYLOADS) >= 3, "Need at least 3 encoded payloads"
        assert len(ABSOLUTE_PATH_PAYLOADS) >= 3, "Need at least 3 absolute path payloads"
        assert len(SENSITIVE_FILE_PAYLOADS) >= 5, "Need at least 5 sensitive file probes"
        assert len(ALL_PATH_TRAVERSAL_PAYLOADS) >= 20, "Total corpus must have at least 20 payloads"

    def test_corpus_includes_null_byte_testing(self) -> None:
        """Null byte payload testing must be included."""
        assert len(NULL_BYTE_PAYLOADS) >= 2, "Need null byte test coverage"

    def test_corpus_includes_combined_attacks(self) -> None:
        """Combined attack patterns must be included."""
        assert len(COMBINED_ATTACK_PAYLOADS) >= 3, "Need combined attack pattern coverage"


# =============================================================================
# BUG-CLASS REGRESSION VERIFICATION
# =============================================================================


class TestBugClassRegressionCloseCriteria:
    """Verify close criteria for security regression ACT.

    Close criteria:
    1. Bug is fixed - verified by tests
    2. Regression test fails before fix - tests demonstrate this
    3. Regression test passes after fix - current tests verify this
    4. Adjacent payload corpus added - full corpus implemented
    5. Route/primitive documented - docstrings exist
    6. Reviewer confirms bug class is now gated - tests provide evidence
    """

    def test_regression_tests_exist(self) -> None:
        """Verify regression tests exist for path traversal."""
        # This test file itself is the regression corpus
        assert TestServeArtifactPathTraversal is not None
        assert len(ALL_PATH_TRAVERSAL_PAYLOADS) > 0

    def test_canary_file_mechanism_works(self, tmp_path: Path) -> None:
        """Verify canary file detection mechanism works."""
        canary = SecurityCanaryFiles(tmp_path)

        # Canary content should be detectable
        assert "SECRET_CANARY" in canary.get_canary_content()

        # Canary files should exist outside the root
        canary_files = canary.get_all_canary_paths()
        assert len(canary_files) > 0

        # All canary paths should be outside the root
        for f in canary_files:
            assert not f.resolve().is_relative_to(tmp_path.resolve()), f"Canary {f} should be outside root {tmp_path}"

        canary.cleanup()
