"""SQLite connection factory for incident store.

This module provides connection creation utilities:
- Thread-safe connection factory (each operation gets its own connection)
- Journal mode configuration with safety checks

Thread safety design:
- Each store operation opens a fresh connection via _connect() context manager
- Connections are NOT shared across threads to avoid sqlite3.ProgrammingError
- SQLite check_same_thread=True is preserved (default)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .incident_store_sqlite_config import (
    VALID_JOURNAL_MODES,
)

_logger = logging.getLogger(__name__)


def _create_connection(path: Path, journal_mode: str) -> sqlite3.Connection:
    """Create a configured SQLite connection.

    This factory creates connections without sharing state between threads.
    Each operation gets its own connection, and writes are serialized via lock.

    Args:
        path: Path to the SQLite database
        journal_mode: SQLite journal mode (DELETE, TRUNCATE, PERSIST, WAL)

    Returns:
        Configured SQLite connection with row_factory and pragmas
    """
    conn = sqlite3.connect(
        str(path),
        isolation_level="DEFERRED",  # Explicit transaction management
        timeout=5.0,  # 5 second busy timeout
    )
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    # Set busy timeout (ms)
    conn.execute("PRAGMA busy_timeout=5000")

    # Set journal mode
    _set_journal_mode(conn, journal_mode, path)

    return conn


def _set_journal_mode(conn: sqlite3.Connection, mode: str, path: Path) -> None:
    """Set SQLite journal mode with safety checks.

    Args:
        conn: SQLite connection
        mode: Journal mode (DELETE, TRUNCATE, PERSIST, WAL)
        path: Path to database (for logging)
    """
    mode = mode.upper()
    if mode not in VALID_JOURNAL_MODES:
        _logger.warning(
            "Invalid journal mode %s, using DELETE",
            mode,
        )
        mode = "DELETE"

    # WAL warning for network filesystems
    if mode == "WAL":
        _logger.warning(
            "WAL journal mode requested for %s. WAL mode is UNSAFE on network filesystems (NFS, RWX volumes). Consider using DELETE mode for Kubernetes shared storage.",
            path,
            extra={
                "event": "sqlite-wal-warning",
                "path": str(path),
            },
        )

    conn.execute(f"PRAGMA journal_mode={mode}")
    _logger.debug(
        "SQLite journal mode set to %s for %s",
        mode,
        path,
    )


__all__ = [
    "_create_connection",
    "_set_journal_mode",
]
