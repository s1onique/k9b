"""Protocol definitions for UI route handlers.

This module contains Protocol classes that define the minimal interface
required by route handlers, enabling structural subtyping (duck typing)
without requiring concrete class inheritance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class JsonResponseSender(Protocol):
    """Minimal protocol for HTTP handlers that can send JSON responses.

    This protocol defines the minimal interface that route handlers need.
    Both the real HealthUIRequestHandler and test MockHandler satisfy this protocol.
    """

    def _send_json(self, body: dict[str, object], code: int) -> None:
        ...
