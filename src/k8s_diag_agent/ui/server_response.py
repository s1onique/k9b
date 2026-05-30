"""HTTP response serialization helpers for the UI server.

This module contains response serialization functions extracted from server.py
to keep the main server module below size thresholds. These helpers handle:
- JSON response encoding and sending
- Text response helpers
- File/binary response helpers
- Structured timing and logging

All functions are designed to work with BaseHTTPRequestHandler instances.
"""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..structured_logging import emit_structured_log

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def send_json_response(
    handler: BaseHTTPRequestHandler,
    body: object,
    code: int = 200,
    request_path: str = "",
) -> None:
    """Send a JSON response with structured timing instrumentation.

    This function handles the full JSON response lifecycle:
    1. Serialize body to JSON
    2. Encode to UTF-8 bytes
    3. Set HTTP response line and headers
    4. Write and flush response body
    5. Force connection close to prevent keep-alive issues
    6. Emit structured timing log for debugging

    Args:
        handler: The HTTP request handler instance
        body: The Python object to serialize as JSON
        code: HTTP status code (default 200)
        request_path: The request path for logging (optional, for compatibility)
    """
    send_start = time.perf_counter()
    payload = json.dumps(body, ensure_ascii=False)
    encode_done = time.perf_counter()
    encoded = payload.encode("utf-8")
    body_write_done = time.perf_counter()

    # Set response bytes for access logging BEFORE sending
    handler._response_bytes = len(encoded)

    handler.send_response(code)
    send_headers_done = time.perf_counter()
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    # INTENTIONAL: Always force Connection: close for development and single-threaded
    # server instances. This prevents proxy/Vite/podman keep-alive socket reuse delays
    # where the browser waits for a fresh socket after backend completion.
    # For production multi-process servers behind a reverse proxy, this header can be
    # removed if the proxy handles connection management correctly.
    handler.send_header("Connection", "close")
    handler.end_headers()
    flush_done = time.perf_counter()
    handler.wfile.write(encoded)
    handler.wfile.flush()
    write_done = time.perf_counter()

    # Tell BaseHTTPRequestHandler to close connection after this response
    # This is the definitive way to prevent keep-alive with HTTP/1.1
    handler.close_connection = True

    # Log detailed send timing for debugging
    emit_structured_log(
        component="ui-send",
        message="HTTP response sent",
        run_id="",
        run_label="",
        severity="DEBUG",
        metadata={
            "path": request_path,
            "payload_bytes": len(encoded),
            "json_dumps_ms": round((encode_done - send_start) * 1000, 3),
            "encode_ms": round((body_write_done - encode_done) * 1000, 3),
            "send_response_ms": round((send_headers_done - body_write_done) * 1000, 3),
            "send_headers_ms": round((flush_done - send_headers_done) * 1000, 3),
            "wfile_write_ms": round((write_done - flush_done) * 1000, 3),
            "total_send_ms": round((write_done - send_start) * 1000, 3),
        },
    )


def send_error_response(
    handler: BaseHTTPRequestHandler,
    error: str,
    code: int = 500,
) -> None:
    """Send a JSON error response.

    Convenience function for consistent error response format.

    Args:
        handler: The HTTP request handler instance
        error: Error message to include in response
        code: HTTP status code (default 500)
    """
    send_json_response(handler, {"error": error}, code)


def send_text_response(
    handler: BaseHTTPRequestHandler,
    code: int,
    message: str,
) -> None:
    """Send a plain text response.

    Args:
        handler: The HTTP request handler instance
        code: HTTP status code
        message: Text message to send
    """
    handler.send_response(code)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(message.encode("utf-8"))


def send_file_response(
    handler: BaseHTTPRequestHandler,
    path: Path,
) -> bool:
    """Send a file response with appropriate content type.

    Args:
        handler: The HTTP request handler instance
        path: Path to the file to serve

    Returns:
        True if file was sent successfully, False if there was an error
    """
    try:
        data = path.read_bytes()
    except OSError as exc:
        send_text_response(handler, 500, f"Unable to read asset: {exc}")
        return False
    content_type, _ = mimetypes.guess_type(path.name)
    handler.send_response(200)
    handler.send_header("Content-Type", content_type or "application/octet-stream")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
    return True


def send_bytes_response(
    handler: BaseHTTPRequestHandler,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    filename: str | None = None,
) -> None:
    """Send raw bytes response with optional Content-Disposition header.

    Args:
        handler: The HTTP request handler instance
        data: Raw bytes to send
        content_type: Content-Type header value
        filename: Optional filename for Content-Disposition header
    """
    handler._response_bytes = len(data)

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if filename:
        # Use quoted filename for ASCII, encoded for non-ASCII
        handler.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
    # INTENTIONAL: Always force Connection: close for development
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(data)
    handler.wfile.flush()

    # Tell BaseHTTPRequestHandler to close connection after this response
    handler.close_connection = True


def set_response_status(handler: BaseHTTPRequestHandler, code: int) -> None:
    """Set the response status code.

    Args:
        handler: The HTTP request handler instance
        code: HTTP status code
    """
    handler._status_code = code
    handler.send_response(code)
