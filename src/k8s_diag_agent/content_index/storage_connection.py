"""Content index storage connection management.

This module provides database connection, initialization, and schema loading.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

# =============================================================================
# Schema SQL
# =============================================================================

# Load schema from file at module load time
_SCHEMA_SQL: str | None = None


def _get_schema_sql() -> str:
    """Load schema SQL from file."""
    global _SCHEMA_SQL
    if _SCHEMA_SQL is None:
        schema_path = Path(__file__).parent / "schema.sql"
        _SCHEMA_SQL = schema_path.read_text()
    return _SCHEMA_SQL


# =============================================================================
# Connection Management
# =============================================================================


def get_connection(db_path: Path, read_only: bool = False) -> sqlite3.Connection:
    """Get a database connection with proper settings.

    Args:
        db_path: Path to the SQLite database file.
        read_only: If True, open in read-only mode.

    Returns:
        A configured SQLite connection.

    Raises:
        FileNotFoundError: If database doesn't exist and read_only=True.
    """
    if read_only:
        if not db_path.exists():
            raise FileNotFoundError(f"Database does not exist: {db_path}")
        # Use URI mode for read-only access
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            timeout=30.0,
        )
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30.0,
        )
        conn.execute("PRAGMA journal_mode = WAL")

    # Enable foreign keys for all connections
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def initialize_database(db_path: Path) -> sqlite3.Connection:
    """Initialize a new content index database.

    Creates all tables, indexes, and writes metadata.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A configured SQLite connection to the new database.

    Raises:
        sqlite3.Error: If schema execution fails.
    """
    from datetime import UTC, datetime

    from .schema import CONTENT_INDEX_SCHEMA_VERSION

    schema_sql = _get_schema_sql()
    now = datetime.now(UTC).isoformat()

    conn = get_connection(db_path, read_only=False)

    try:
        # Execute schema creation
        conn.executescript(schema_sql)
        conn.commit()

        # Write metadata
        conn.execute(
            "INSERT OR REPLACE INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("schema_version", CONTENT_INDEX_SCHEMA_VERSION),
        )
        conn.execute(
            "INSERT OR REPLACE INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("created_at", now),
        )
        conn.execute(
            "INSERT OR REPLACE INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("indexed_at", now),
        )
        conn.commit()

    except sqlite3.Error:
        conn.close()
        raise

    return conn


def create_temp_database() -> tuple[Path, sqlite3.Connection]:
    """Create a temporary database for rebuild operations.

    Returns:
        Tuple of (temp path, connection).
    """
    import tempfile

    temp_dir = Path(tempfile.gettempdir())
    temp_path = temp_dir / f"k9b_content_index_{os.getpid()}_{time.time()}.sqlite"
    conn = initialize_database(temp_path)
    return temp_path, conn
