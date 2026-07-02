"""Typed test handler for API contract testing.

This module provides a mock handler that implements the protocols used by
route handlers, enabling mypy to pass without blanket type ignores.
"""

from __future__ import annotations

import json
from email.message import Message
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JsonResponseSender(Protocol):
    """Protocol for HTTP handlers that can send JSON responses."""

    def _send_json(self, body: dict[str, object], code: int) -> None:
        ...


class _CapturingBytesIO(BytesIO):
    """BytesIO that captures written content and stores it in a handler."""

    def __init__(self, handler: MockApiHandler) -> None:
        super().__init__()
        self._handler = handler

    def write(self, s: bytes) -> int:  # type: ignore[override]
        result = super().write(s)
        # After writing, parse as JSON if Content-Type is application/json
        content_type = self._handler._sent_headers.get("Content-Type", "")
        if "application/json" in content_type:
            self._handler.wfile.seek(0)
            content = self._handler.wfile.read()
            try:
                self._handler._sent_body = json.loads(content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return result


class MockApiHandler(BaseHTTPRequestHandler, JsonResponseSender):
    """Mock HTTP request handler for testing JSON response contracts.

    This mock inherits from BaseHTTPRequestHandler to be compatible with
    HealthUIRequestHandler type expectations and implements JsonResponseSender.
    """

    protocol_version = "HTTP/1.1"

    def __init__(self) -> None:
        # Don't call BaseHTTPRequestHandler.__init__ - we're using this as a data class
        self._sent_code: int | None = None
        self._sent_body: dict[str, Any] | None = None
        self._sent_headers: dict[str, str] = {}
        self._sent_text: str | None = None
        self.path: str = "/"
        self.command: str = "GET"
        self.headers: Message[str, str] = Message()
        self.runs_dir: Path = Path("/tmp/test/runs")
        self.static_dir: Path = Path("/tmp/test/static")
        self._health_root: Path = Path("/tmp/test/health")
        self._response_bytes: int = 0
        self._send_count: int = 0  # Track response calls to detect double-send
        self.wfile: _CapturingBytesIO = _CapturingBytesIO(self)
        # Request body attribute for handlers that read request body (e.g., _parse_request_config)
        self.body: bytes = b""

    def send_response(self, code: int, message: str | None = None) -> None:
        """Mock send_response for BaseHTTPRequestHandler compatibility."""
        self._sent_code = code
        self._send_count += 1

    def send_header(self, name: str, value: str) -> None:
        """Mock send_header for BaseHTTPRequestHandler compatibility."""
        self._sent_headers[name] = value

    def end_headers(self) -> None:
        """Mock end_headers for BaseHTTPRequestHandler compatibility."""
        pass

    def _send_json(self, body: dict[str, object], code: int = 200) -> None:
        """Direct JSON send via handler method (used by health endpoints)."""
        self._sent_code = code
        self._sent_body = body
        self._send_count += 1

    def _send_text(self, code: int, message: str) -> None:
        """Direct text send via handler method."""
        self._sent_code = code
        self._sent_text = message
        self._send_count += 1

    def _log_access_completion(self) -> None:
        """Mock access logging method for server_routes.py compatibility."""
        pass

    def _load_context(self) -> dict[str, Any] | None:
        """Mock context loading method for server_reads.py compatibility."""
        return None

    # Required by BaseHTTPRequestHandler
    def flush_headers(self) -> None:
        pass

    def log_message(self, format: str, *args: Any) -> None:
        pass


# =============================================================================
# Assertion helpers
# =============================================================================


def assert_json_response(
    handler: MockApiHandler,
    expected_code: int | None = None,
    expected_body_keys: list[str] | None = None,
) -> None:
    """Assert handler has a valid JSON response.

    Args:
        handler: The mock handler to check
        expected_code: Optional expected status code
        expected_body_keys: Optional list of expected body keys
    """
    assert handler._sent_body is not None, "Response body is None (response may not have been sent)"

    if expected_code is not None:
        assert handler._sent_code == expected_code, (
            f"Expected status {expected_code}, got {handler._sent_code}"
        )

    assert isinstance(handler._sent_body, dict), (
        f"Response body is not a dict: {type(handler._sent_body)}"
    )

    if expected_body_keys:
        for key in expected_body_keys:
            assert key in handler._sent_body, (
                f"Expected key '{key}' in response body"
            )


def assert_no_html_in_response(handler: MockApiHandler) -> None:
    """Assert response does not contain HTML markers.

    Args:
        handler: The mock handler to check
    """
    body = handler._sent_body or handler._sent_text
    body_str = json.dumps(body) if isinstance(body, dict) else str(body)
    body_lower = body_str.lower()

    html_markers = [
        "<html",
        "<body",
        "<head",
        "<!doctype",
        "<div",
        "<script",
        "index.html",
        "<a ",
        "<form",
    ]

    for marker in html_markers:
        assert marker not in body_lower, (
            f"HTML marker '{marker}' found in response"
        )


def assert_valid_json(handler: MockApiHandler) -> None:
    """Assert response body is valid JSON.

    Args:
        handler: The mock handler to check
    """
    assert handler._sent_body is not None, "Response body is None"

    # Must be serializable
    json_str = json.dumps(handler._sent_body)
    parsed = json.loads(json_str)
    assert parsed == handler._sent_body


def assert_single_response(handler: MockApiHandler) -> None:
    """Assert exactly one response was sent (no double-send).

    Args:
        handler: The mock handler to check
    """
    assert handler._send_count == 1, (
        f"Expected exactly 1 response sent, got {handler._send_count}"
    )
