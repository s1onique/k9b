"""Shared test support for server_static security tests.

This module contains the payload corpus and helper classes used across
server_static security regression test modules.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

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
ALL_PATH_TRAVERSAL_PAYLOADS: list[str] = (
    TRAVERSAL_PAYLOADS
    + ENCODED_TRAVERSAL_PAYLOADS
    + ABSOLUTE_PATH_PAYLOADS
    + NULL_BYTE_PAYLOADS
    + DOT_SEGMENT_PAYLOADS
    + SENSITIVE_FILE_PAYLOADS
    + COMBINED_ATTACK_PAYLOADS
)


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
