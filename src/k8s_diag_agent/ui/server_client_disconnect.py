"""Client disconnect classification for UI HTTP transport edge.

This module provides canonical classification of expected client disconnects
at the HTTP transport boundary. These are not domain failures - they occur
when the client closes the connection before or during response delivery.

The goal is a precise transport-disconnect predicate, not a broad exception handler.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# Canonical client disconnect exceptions that escape through Python's socketserver/http.server
# boundary. These indicate the client closed the connection unexpectedly.
CLIENT_DISCONNECT_EXCEPTIONS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)


def is_client_disconnect_error(exc: BaseException | None) -> bool:
    """Classify whether an exception represents an expected client disconnect.

    This predicate is used to distinguish expected transport failures (client
    closed connection, proxy timeout, etc.) from unexpected application errors.

    Args:
        exc: The exception to classify, or None if no exception.

    Returns:
        True if this is an expected client disconnect, False otherwise.
    """
    if exc is None:
        return False
    return isinstance(exc, CLIENT_DISCONNECT_EXCEPTIONS)


def get_disconnect_errno(exc: BaseException | None) -> int | None:
    """Extract errno from a disconnect exception if present.

    Args:
        exc: The exception to extract errno from.

    Returns:
        The errno value if available, None otherwise.
    """
    if exc is None:
        return None
    # BrokenPipeError, ConnectionResetError, ConnectionAbortedError may have errno
    if isinstance(exc, socket.error) and hasattr(exc, "errno"):
        return exc.errno
    if isinstance(exc, OSError) and hasattr(exc, "errno"):
        return exc.errno
    return None
