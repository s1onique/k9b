"""Loopback HTTP test server for promotion transport matrix.

ACT-K9B-HULK-PROMOTION-AMBIGUOUS-RESPONSE-TRANSPORT-TRUTH01-LOCAL-CONTRACT01.

The support module exposes a deterministic ``BaseHTTPRequestHandler``
subclass that the test matrix can drive to exercise every HTTP
shape against the real scheduler promotion client. The server binds
only to ``127.0.0.1`` on an ephemeral port (selected by the kernel).

The handler is intentionally minimal:

* it does not parse the request body shape; the matrix only cares
  about status code, content type, and body cardinality;
* it never logs the response body;
* it never reads a token or authorization header (the production
  client does, the server simply ignores those headers).

Tests register a "scenario" via :func:`set_scenario` and then call
the real scheduler client. Scenarios are bounded so the support file
is small.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer


@dataclass(frozen=True, slots=True)
class HttpScenario:
    """Bounded HTTP scenario consumed by the test server.

    ``body`` MUST NOT contain request-specific identifiers. The
    scheduler correlation uses ``request_id`` separately.
    """

    status_code: int
    content_type: str | None
    body: bytes | None
    declared_content_length: int | None = None
    close_after_send: bool = False
    truncate_at_bytes: int | None = None


_SCENARIO_GETTER: Callable[[], HttpScenario] | None = None
_SCENARIO_LOCK = threading.Lock()


def set_scenario(scenario_factory: Callable[[], HttpScenario]) -> None:
    """Register the scenario factory used by the next request handler.

    The factory MUST be deterministic for the test invocation scope
    so concurrent tests do not race on a mutable global.
    """
    global _SCENARIO_GETTER
    with _SCENARIO_LOCK:
        _SCENARIO_GETTER = scenario_factory


def clear_scenario() -> None:
    """Clear the registered scenario factory."""
    global _SCENARIO_GETTER
    with _SCENARIO_LOCK:
        _SCENARIO_GETTER = None


def _consume_scenario() -> HttpScenario:
    with _SCENARIO_LOCK:
        getter = _SCENARIO_GETTER
    if getter is None:
        raise RuntimeError(
            "promotion_http_test_server: no scenario registered; call "
            "set_scenario(...) before exercising the client."
        )
    return getter()


class _Handler(BaseHTTPRequestHandler):
    """HTTP handler driven by the registered scenario factory.

    The handler closes the connection when the scenario opts in via
    ``close_after_send=True``. Truncation is implemented by sending
    only the first ``truncate_at_bytes`` bytes of the configured
    body and then closing the connection without sending
    ``Content-Length``.
    """

    # Class-level throttling: BaseHTTPRequestHandler logs every request
    # to stderr by default. We override ``log_message`` to a no-op so
    # the test output stays clean.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        scenario = _consume_scenario()
        # Read (and discard) the request body so the kernel does not
        # hold the socket open.
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > 0:
            try:
                _ = self.rfile.read(content_length)
            except OSError:
                return

        body = scenario.body or b""
        if scenario.truncate_at_bytes is not None:
            body = body[: scenario.truncate_at_bytes]
            # Intentionally do NOT send Content-Length so the client
            # observes a missing / truncated Content-Length header.
            self.send_response(scenario.status_code)
            if scenario.content_type:
                self.send_header("Content-Type", scenario.content_type)
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass
            if scenario.close_after_send:
                try:
                    self.connection.shutdown(2)
                except OSError:
                    pass
            return

        self.send_response(scenario.status_code)
        if scenario.content_type:
            self.send_header("Content-Type", scenario.content_type)
        if scenario.declared_content_length is not None:
            self.send_header(
                "Content-Length", str(scenario.declared_content_length)
            )
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except OSError:
                pass
        if scenario.close_after_send:
            try:
                self.connection.shutdown(2)
            except OSError:
                pass

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        # GET is supported only to satisfy BaseHTTPRequestHandler's
        # method-routing check; production promotion uses POST.
        scenario = _consume_scenario()
        self.send_response(scenario.status_code)
        if scenario.content_type:
            self.send_header("Content-Type", scenario.content_type)
        self.end_headers()


@dataclass(frozen=True, slots=True)
class LoopbackServer:
    """Bounded reference to the loopback HTTP test server."""

    host: str
    port: int
    base_url: str

    @property
    def promote_alert_signals_url(self) -> str:
        """Canonical promotion endpoint used by the production client."""
        return f"{self.base_url}/api/internal/incidents/promote-alert-signals"


_SERVER_LOCK = threading.Lock()
_SERVER_SINGLETON: LoopbackServer | None = None
_SERVER_THREAD: threading.Thread | None = None


def start_loopback_server() -> LoopbackServer:
    """Start a single loopback HTTP test server for the current process.

    The server binds to ``127.0.0.1`` on an ephemeral port. Multiple
    calls return the same singleton within one process so test
    matrices share a stable URL.
    """
    global _SERVER_SINGLETON, _SERVER_THREAD
    with _SERVER_LOCK:
        if _SERVER_SINGLETON is not None:
            return _SERVER_SINGLETON
        # ``server_bind`` raises ``OSError`` if the port is taken; the
        # kernel-selected port (port=0) avoids that failure mode.
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        host, port = server.server_address
        thread = threading.Thread(
            target=server.serve_forever,
            name="promotion-http-test-server",
            daemon=True,
        )
        thread.start()
        _SERVER_SINGLETON = LoopbackServer(
            host=host,
            port=port,
            base_url=f"http://{host}:{port}",
        )
        _SERVER_THREAD = thread
        return _SERVER_SINGLETON
