"""Module-scoped HTTP fixtures for security tests.

These fixtures create the HTTP server and test harness once per session,
reducing repeated setup overhead across security route tests.
"""
from __future__ import annotations

import socket
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)
from tests.security.server_static_test_support import SecurityCanaryFiles


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

    def _create_handler(self) -> Any:
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

    @property
    def port(self) -> int:
        """Return the bound port."""
        return self._port

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes, dict[str, str]]:
        """Make an HTTP request. Returns (status_code, body, headers_dict)."""
        from http.client import HTTPConnection

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


class AuthDisabledHarness:
    """Harness wrapper for auth-disabled server."""

    def __init__(self, server_instance: Any) -> None:
        self._server = server_instance

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, bytes, dict[str, str]]:
        """Make an HTTP request. Returns (status_code, body, headers_dict)."""
        from http.client import HTTPConnection

        port = self._server.server_address[1]
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
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


@pytest.fixture(scope="module")
def http_harness_module(tmp_path_factory: pytest.TempPathFactory) -> Generator[list, None, None]:
    """Module-scoped HTTP test harness with runs_dir, static_dir, and canary files.

    Creates server/directories once per module instead of per test.
    WARNING: Do not modify state in tests as it's shared.
    """
    tmp_path = tmp_path_factory.mktemp("http_harness")
    
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


@pytest.fixture(scope="module")
def http_harness_no_auth_module(tmp_path_factory: pytest.TempPathFactory) -> Generator[list, None, None]:
    """Module-scoped HTTP test harness with auth disabled for route-behavior testing.

    WARNING: Do not modify state in tests as it's shared.
    """
    tmp_path = tmp_path_factory.mktemp("http_harness_no_auth")
    
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

    # Start server with auth disabled
    server, thread, patcher = start_ui_test_server_without_auth(
        runs_dir=runs_dir,
        static_dir=static_dir,
    )

    harness = AuthDisabledHarness(server)

    try:
        yield [harness, harness.port, canary]
    finally:
        shutdown_test_server(server, thread, patcher)
        canary.cleanup()
