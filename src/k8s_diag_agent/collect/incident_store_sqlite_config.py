"""SQLite connection configuration for incident store.

This module provides connection management utilities for the SQLite backend:
- Connection configuration dataclass
- Connection factory with proper pragmas
- Journal mode safety checks

Hard constraints:
- NO WAL mode by default (unsafe on network filesystems)
- DELETE journal mode for Kubernetes shared/RWX volumes
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

# =============================================================================
# Environment / Configuration
# =============================================================================

ENV_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_SQLITE_PATH = "K9B_INCIDENT_STORE_SQLITE_PATH"
ENV_FILE_PATH = "K9B_INCIDENT_STORE_PATH"
ENV_JOURNAL_MODE = "K9B_INCIDENT_SQLITE_JOURNAL_MODE"

# Default values
DEFAULT_SQLITE_PATH = "/app/runs/incidents/k9b-incidents.sqlite3"
DEFAULT_JOURNAL_MODE = "DELETE"  # Safe for network filesystems

# Valid journal modes
VALID_JOURNAL_MODES = frozenset({"DELETE", "TRUNCATE", "PERSIST", "WAL"})


# =============================================================================
# SQLite Connection Management
# =============================================================================


@dataclass
class SQLiteConnectionConfig:
    """Configuration for SQLite connection."""

    path: Path
    journal_mode: str = DEFAULT_JOURNAL_MODE
    busy_timeout: int = 5000
    foreign_keys: bool = True


def create_connection(config: SQLiteConnectionConfig) -> sqlite3.Connection:
    """Create a configured SQLite connection.

    Args:
        config: Connection configuration

    Returns:
        Configured SQLite connection
    """
    conn = sqlite3.connect(
        str(config.path),
        isolation_level="DEFERRED",  # Explicit transaction management
        timeout=config.busy_timeout / 1000,  # Convert to seconds
    )
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    if config.foreign_keys:
        conn.execute("PRAGMA foreign_keys=ON")

    # Set busy timeout
    conn.execute(f"PRAGMA busy_timeout={config.busy_timeout}")

    # Set journal mode
    _set_journal_mode(conn, config.journal_mode, config.path)

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
            "WAL journal mode requested for %s. "
            "WAL mode is UNSAFE on network filesystems (NFS, RWX volumes). "
            "Consider using DELETE mode for Kubernetes shared storage.",
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
    "SQLiteConnectionConfig",
    "create_connection",
    "ENV_BACKEND",
    "ENV_SQLITE_PATH",
    "ENV_FILE_PATH",
    "ENV_JOURNAL_MODE",
    "DEFAULT_SQLITE_PATH",
    "DEFAULT_JOURNAL_MODE",
    "VALID_JOURNAL_MODES",
]
