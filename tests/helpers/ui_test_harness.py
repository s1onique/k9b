"""Test harness helpers for UI server route tests.

This module provides explicit auth modes for UI server tests:
- start_ui_test_server_without_auth(): For legacy route-behavior tests
- start_ui_test_server_with_auth_disabled(): Same as above, explicit name
- server_context_without_auth(): Context manager variant

Use these helpers instead of directly creating HealthUIRequestHandler to ensure
auth behavior is explicit and intentional in tests.

Auth is disabled via mocking of get_auth_config(), not environment variables,
to avoid thread-safety issues with global state.
"""

from __future__ import annotations

import functools
import tempfile
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

if TYPE_CHECKING:
    pass


def _make_disabled_auth_config() -> object:
    """Create a mock AuthConfig with authentication disabled."""
    mock_config = mock.MagicMock()
    mock_config.enabled = False
    mock_config.is_development_mode = True
    mock_config.admin_username = "test"
    mock_config.admin_password_hash = None
    return mock_config


def start_ui_test_server_without_auth(
    *,
    runs_dir: Path,
    static_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, object]:
    """Start a UI test server with authentication disabled.
    
    Use this for legacy route-behavior tests that are not about authentication.
    This ensures these tests continue asserting route-specific behavior (200 for
    valid reads, 400 for malformed requests, etc.) without being blocked by auth.
    
    Args:
        runs_dir: Directory containing run health data
        static_dir: Directory containing static assets
        
    Returns:
        Tuple of (server, thread, patcher) where:
        - server: The ThreadingHTTPServer instance
        - thread: The daemon thread running the server
        - patcher: The mock.patch.object to stop on cleanup
        
    Example:
        server, thread, patcher = start_ui_test_server_without_auth(
            runs_dir=self.runs_dir,
            static_dir=self.static_dir,
        )
        try:
            # Test protected endpoint without auth
            response = self._fetch_run_payload(server)
            self.assertEqual(response["status"], "ok")
        finally:
            patcher.stop()
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
    """
    from k8s_diag_agent.ui import auth_config as auth_config_module
    from k8s_diag_agent.ui.server import HealthUIRequestHandler
    
    # Create handler with functools.partial
    handler = functools.partial(
        HealthUIRequestHandler,
        runs_dir=runs_dir,
        static_dir=static_dir or (Path(tempfile.mkdtemp()) / "static"),
    )
    
    # Start server first
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    # Now patch get_auth_config to return disabled auth
    # This must happen after server starts but before any requests
    patcher = mock.patch.object(
        auth_config_module,
        'get_auth_config',
        return_value=_make_disabled_auth_config()
    )
    patcher.start()
    
    return server, thread, patcher


def start_ui_test_server_with_auth_disabled(
    *,
    runs_dir: Path,
    static_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, object]:
    """Alias for start_ui_test_server_without_auth() with more explicit naming.
    
    Use this variant when you want to be explicit that auth is being disabled.
    """
    return start_ui_test_server_without_auth(runs_dir=runs_dir, static_dir=static_dir)


@contextmanager
def server_context_without_auth(
    *,
    runs_dir: Path,
    static_dir: Path | None = None,
) -> Generator[tuple[ThreadingHTTPServer, threading.Thread], None, None]:
    """Context manager that provides a test server with auth disabled.
    
    Automatically handles server startup, patching, shutdown, and cleanup.
    
    Args:
        runs_dir: Directory containing run health data
        static_dir: Directory containing static assets
        
    Yields:
        Tuple of (server, thread)
        
    Example:
        with server_context_without_auth(runs_dir=self.runs_dir) as (server, thread):
            # Make requests without auth
            response = self._fetch_run_payload(server)
            self.assertEqual(response["status"], "ok")
    """
    server, thread, patcher = start_ui_test_server_without_auth(
        runs_dir=runs_dir,
        static_dir=static_dir,
    )
    try:
        yield server, thread
    finally:
        patcher.stop()
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def shutdown_test_server(
    server: ThreadingHTTPServer,
    thread: threading.Thread,
    patcher: object | None = None,
) -> None:
    """Shutdown a test server and clean up resources.
    
    Args:
        server: The server to shutdown
        thread: The server thread to join
        patcher: Optional mock patcher to stop first
    """
    if patcher is not None:
        patcher.stop()
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
