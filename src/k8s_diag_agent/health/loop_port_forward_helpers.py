"""Port-forward infrastructure helpers for the health loop.

Extracts TCP port selection and connectivity helpers from loop.py into a focused module.
Preserves behavior exactly - no subprocess, logging, or cleanup semantic changes.

This module provides pure infrastructure helpers:
1. Choose a free local TCP port
2. Wait for a TCP port to become ready

These are reusable across port-forward lifecycle operations.
"""

from __future__ import annotations

import socket
import time


def _choose_free_local_port() -> int:
    """Choose a free local TCP port for port-forward.
    
    Returns:
        A free port number on localhost.
        
    Raises:
        RuntimeError: If no free port can be found after 10 attempts.
    """
    for attempt in range(10):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                port: int = sock.getsockname()[1]
                return port
        except OSError:
            continue
    raise RuntimeError("Could not find a free local port for port-forward")


def _wait_for_port_ready(
    host: str,
    port: int,
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.1,
) -> bool:
    """Wait for a TCP port to become accepting connections.
    
    Args:
        host: The host to check (typically "127.0.0.1").
        port: The port to check.
        timeout_seconds: Maximum time to wait.
        poll_interval: Time between connection attempts.
        
    Returns:
        True if the port became ready within the timeout, False otherwise.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(poll_interval)
    return False