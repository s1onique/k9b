"""Custom HTTP server class with structured error handling.

This module provides a ThreadingHTTPServer subclass that overrides handle_error()
to emit structured logs instead of raw tracebacks for client disconnects and
unexpected exceptions.

The default socketserver.BaseServer.handle_error() prints raw tracebacks to stderr.
This is not appropriate for production observability - we want structured logs.
"""

from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer
from typing import Any

from ..structured_logging import emit_structured_log
from .server_client_disconnect import get_disconnect_errno, is_client_disconnect_error


def _format_client_address(client_address: tuple[str, int] | str | None) -> str:
    """Format client address for logging.

    Args:
        client_address: The client address tuple (host, port) or string.

    Returns:
        Formatted address string.
    """
    if client_address is None:
        return "unknown"
    if isinstance(client_address, str):
        return client_address
    if isinstance(client_address, tuple) and len(client_address) >= 2:
        host, port = client_address[:2]
        return f"{host}:{port}"
    return str(client_address)


class StructuredErrorHTTPServer(ThreadingHTTPServer):
    """HTTP server with structured error handling.

    This server class overrides handle_error() to emit structured logs instead
    of raw tracebacks for expected client disconnects and unexpected exceptions.

    Key behaviors:
    - Client disconnects (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
      produce INFO-level structured logs with request_outcome="client_disconnected".
    - Unexpected exceptions produce ERROR-level structured logs with
      request_outcome="exception".
    - No raw tracebacks are printed to stderr.
    """

    def handle_error(self, request: Any, client_address: tuple[str, int] | str | None) -> None:
        """Handle an error during request processing with structured logging.

        This overrides the default socketserver.BaseServer.handle_error() which
        prints raw tracebacks to stderr. Instead, we emit structured logs and
        continue serving requests.

        For expected client disconnects (BrokenPipeError, ConnectionResetError,
        ConnectionAbortedError), we emit INFO-level logs and return.

        For unexpected exceptions, we emit ERROR-level logs with exception details
        and return.

        Args:
            request: The request that caused the error.
            client_address: The client address tuple.
        """
        exc_type, exc, _tb = sys.exc_info()

        if is_client_disconnect_error(exc):
            # Expected client disconnect - log at INFO level and continue
            emit_structured_log(
                component="ui-server",
                severity="INFO",
                message="Client disconnected during request handling",
                request_outcome="client_disconnected",
                client_address=_format_client_address(client_address),
                exception_type=type(exc).__name__ if exc else None,
                errno=get_disconnect_errno(exc),
                run_id="",
                run_label="",
            )
            return

        # Unexpected exception - log at ERROR level
        emit_structured_log(
            component="ui-server",
            severity="ERROR",
            message="Unhandled request handler exception",
            request_outcome="exception",
            client_address=_format_client_address(client_address),
            exception_type=exc_type.__name__ if exc_type else None,
            exception_message=str(exc) if exc else None,
            run_id="",
            run_label="",
        )
        return
