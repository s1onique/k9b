"""Content index storage metadata operations.

This module provides metadata read/write operations for the content index.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    """Get a metadata value from the index.

    Args:
        conn: Database connection.
        key: Metadata key to retrieve.

    Returns:
        The metadata value, or None if not found.
    """
    cursor = conn.execute(
        "SELECT value FROM content_index_metadata WHERE key = ?",
        (key,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def update_indexed_at(conn: sqlite3.Connection) -> None:
    """Update the indexed_at timestamp.

    Args:
        conn: Database connection.
    """
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO content_index_metadata (key, value) VALUES (?, ?)",
        ("indexed_at", now),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> str | None:
    """Get the schema version from the index metadata.

    Args:
        conn: Database connection.

    Returns:
        The schema version, or None if not set.
    """
    return get_metadata(conn, "schema_version")
