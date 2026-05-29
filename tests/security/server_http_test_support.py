"""Shared HTTP test support for server route security tests.

This module contains the HTTP test harness and fixtures used across
server HTTP route security test modules.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Generator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from tests.security.server_static_test_support import (
    SecurityCanaryFiles,
)

# =============================================================================
# HTTP TEST HARNESS
# =============================================================================


class HTTPServerTestHarness:
    """Minimal HTTP server harness for security testing.

    Spawns a HealthUIRequestHandler-based server on a random available port.
    Provides clean start/stop and HTTP request methods.
    """

    def __init__(
        self,
        runs_dir: Path,
        static_dir: Path,
        auth_token: str | None = None,
    ) -> None:
        self.runs_dir = runs_dir
        self.static_dir = static_dir
        self.auth_token = auth_token
        self._server: object | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0
        self._ready_event = threading.Event()

    def start(self) -> int:
        """Start the test server. Returns the port it bound to."""
        from http.server import ThreadingHTTPServer

        # Find an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tmp_sock:
            tmp_sock.bind(("127.0.0.1", 0))
            self._port = tmp_sock.getsockname()[1]

        handler = self._create_handler()
        self._server = ThreadingHTTPServer(("127.0.0.1", self._port), handler)

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        self._ready_event.wait(timeout=5.0)
        return self._port

    def _create_handler(self) -> Callable[..., Any]:
        """Create a handler class with the configured runs_dir and static_dir."""
        from functools import partial

        from k8s_diag_agent.ui.server import HealthUIRequestHandler

        return partial(
            HealthUIRequestHandler,
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
            auth_token=self.auth_token,
        )

    def _serve(self) -> None:
        """Server thread target."""
        self._ready_event.set()
        assert self._server is not None
        try:
            self._server.serve_forever()
        except Exception:
            pass  # Server shutdown

    def stop(self) -> None:
        """Stop the test server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes, dict[str, str]]:
        """Make an HTTP request. Returns (status_code, body, headers_dict)."""
        conn = HTTPConnection("127.0.0.1", self._port, timeout=5)
        try:
            if headers:
                conn.request(method, path, headers=headers)
            else:
                conn.request(method, path)
            response = conn.getresponse()
            status = response.status
            body = response.read()
            response_headers = dict(response.getheaders())
            return status, body, response_headers
        finally:
            conn.close()


# =============================================================================
# PYTEST FIXTURES
# =============================================================================


@pytest.fixture
def http_harness(tmp_path: Path) -> Generator[list, None, None]:
    """Create an HTTP test harness with runs_dir, static_dir, and canary files.

    Yields a tuple of (harness, port, canary).
    """
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    health_dir = runs_dir / "health"
    health_dir.mkdir(parents=True)
    ea_dir = runs_dir / "external-analysis"
    ea_dir.mkdir(parents=True)

    # Create a valid artifact inside the root
    valid_artifact = ea_dir / "run-test-assessment-001.json"
    valid_artifact.write_text(
        '{"findings": [], "summary": "valid artifact"}',
        encoding="utf-8",
    )

    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<h1>Welcome</h1>", encoding="utf-8")
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("// app", encoding="utf-8")

    canary = SecurityCanaryFiles(runs_dir)

    harness = HTTPServerTestHarness(runs_dir=runs_dir, static_dir=static_dir)
    port = harness.start()

    try:
        yield [harness, port, canary]
    finally:
        harness.stop()
        canary.cleanup()
