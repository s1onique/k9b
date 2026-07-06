"""Content index storage item operations.

This module provides CRUD operations for content items in the content index.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .schema import (
    INDEXED_PATH_KINDS,
    ContentIndexRecord,
    validate_source_path,
)


def upsert_content_item(
    conn: sqlite3.Connection,
    record: ContentIndexRecord,
) -> None:
    """Insert or update a content item.

    Uses SQLite UPSERT (ON CONFLICT) for atomic upsert behavior.

    Args:
        conn: Database connection.
        record: Content index record to upsert.
    """
    # Validate source path
    validate_source_path(record.source_path)

    conn.execute(
        """
        INSERT INTO content_item (
            content_id, content_kind, source_path, source_path_kind,
            source_mtime_ns, source_size_bytes, source_sha256,
            schema_version, indexed_at, deleted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_id) DO UPDATE SET
            content_kind = excluded.content_kind,
            source_path = excluded.source_path,
            source_path_kind = excluded.source_path_kind,
            source_mtime_ns = excluded.source_mtime_ns,
            source_size_bytes = excluded.source_size_bytes,
            source_sha256 = excluded.source_sha256,
            schema_version = excluded.schema_version,
            indexed_at = excluded.indexed_at,
            deleted = excluded.deleted
        """,
        (
            record.content_id,
            record.content_kind,
            record.source_path,
            record.source_path_kind,
            record.source_mtime_ns,
            record.source_size_bytes,
            record.source_sha256,
            record.schema_version,
            record.indexed_at,
            1 if record.deleted else 0,
        ),
    )
    conn.commit()


def get_content_item(
    conn: sqlite3.Connection,
    content_id: str,
) -> ContentIndexRecord | None:
    """Get a content item by ID.

    Args:
        conn: Database connection.
        content_id: Content item ID.

    Returns:
        ContentIndexRecord if found, None otherwise.
    """
    cursor = conn.execute(
        "SELECT * FROM content_item WHERE content_id = ?",
        (content_id,),
    )
    row = cursor.fetchone()

    if row is None:
        return None

    # Row is: (content_id, content_kind, source_path, source_path_kind,
    #          source_mtime_ns, source_size_bytes, source_sha256,
    #          schema_version, indexed_at, deleted)
    return ContentIndexRecord(
        content_id=row[0],
        content_kind=row[1],
        source_path=row[2],
        source_path_kind=row[3],
        source_mtime_ns=row[4],
        source_size_bytes=row[5],
        source_sha256=row[6],
        schema_version=row[7],
        indexed_at=row[8],
        deleted=bool(row[9]),
    )


def get_all_content_items(conn: sqlite3.Connection) -> list[ContentIndexRecord]:
    """Get all content items from the index.

    Args:
        conn: Database connection.

    Returns:
        List of all content items.
    """
    cursor = conn.execute("SELECT * FROM content_item")
    rows = cursor.fetchall()

    items = []
    for row in rows:
        try:
            item = ContentIndexRecord(
                content_id=row[0],
                content_kind=row[1],
                source_path=row[2],
                source_path_kind=row[3],
                source_mtime_ns=row[4],
                source_size_bytes=row[5],
                source_sha256=row[6],
                schema_version=row[7],
                indexed_at=row[8],
                deleted=bool(row[9]),
            )
            items.append(item)
        except ValueError:
            # Skip invalid records
            continue

    return items


def tombstone_content_item(
    conn: sqlite3.Connection,
    content_id: str,
) -> bool:
    """Mark a content item as deleted (tombstone).

    Args:
        conn: Database connection.
        content_id: Content item ID to tombstone.

    Returns:
        True if an item was tombstoned, False if not found.
    """
    cursor = conn.execute(
        "UPDATE content_item SET deleted = 1, indexed_at = ? WHERE content_id = ? AND deleted = 0",
        (datetime.now(UTC).isoformat(), content_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_content_items_by_path_kind(
    conn: sqlite3.Connection,
    path_kind: str,
) -> list[ContentIndexRecord]:
    """Get all content items for a specific path kind.

    Args:
        conn: Database connection.
        path_kind: Source path kind to filter by.

    Returns:
        List of matching content items.
    """
    if path_kind not in INDEXED_PATH_KINDS:
        raise ValueError(f"Invalid path kind: {path_kind!r}")

    cursor = conn.execute(
        "SELECT * FROM content_item WHERE source_path_kind = ?",
        (path_kind,),
    )
    rows = cursor.fetchall()

    items = []
    for row in rows:
        try:
            item = ContentIndexRecord(
                content_id=row[0],
                content_kind=row[1],
                source_path=row[2],
                source_path_kind=row[3],
                source_mtime_ns=row[4],
                source_size_bytes=row[5],
                source_sha256=row[6],
                schema_version=row[7],
                indexed_at=row[8],
                deleted=bool(row[9]),
            )
            items.append(item)
        except ValueError:
            continue

    return items
