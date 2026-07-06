"""Content index storage projection operations.

This module provides CRUD operations for content projections.
"""

from __future__ import annotations

import sqlite3

from .schema import ContentProjectionRecord


def upsert_projection(
    conn: sqlite3.Connection,
    projection: ContentProjectionRecord,
) -> None:
    """Insert or update a content projection.

    Args:
        conn: Database connection.
        projection: Projection record to upsert.
    """
    conn.execute(
        """
        INSERT INTO content_projection (
            content_id, projection_kind, projection_json, updated_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(content_id, projection_kind) DO UPDATE SET
            projection_json = excluded.projection_json,
            updated_at = excluded.updated_at
        """,
        (
            projection.content_id,
            projection.projection_kind,
            projection.projection_json,
            projection.updated_at,
        ),
    )
    conn.commit()


def get_projection(
    conn: sqlite3.Connection,
    content_id: str,
    projection_kind: str,
) -> ContentProjectionRecord | None:
    """Get a specific projection for a content item.

    Args:
        conn: Database connection.
        content_id: Content item ID.
        projection_kind: Type of projection.

    Returns:
        ProjectionRecord if found, None otherwise.
    """
    cursor = conn.execute(
        """
        SELECT content_id, projection_kind, projection_json, updated_at
        FROM content_projection
        WHERE content_id = ? AND projection_kind = ?
        """,
        (content_id, projection_kind),
    )
    row = cursor.fetchone()

    if row is None:
        return None

    return ContentProjectionRecord(
        content_id=row[0],
        projection_kind=row[1],
        projection_json=row[2],
        updated_at=row[3],
    )


def get_projections_for_item(
    conn: sqlite3.Connection,
    content_id: str,
) -> list[ContentProjectionRecord]:
    """Get all projections for a content item.

    Args:
        conn: Database connection.
        content_id: Content item ID.

    Returns:
        List of all projections for the item.
    """
    cursor = conn.execute(
        """
        SELECT content_id, projection_kind, projection_json, updated_at
        FROM content_projection
        WHERE content_id = ?
        """,
        (content_id,),
    )
    rows = cursor.fetchall()

    projections = []
    for row in rows:
        try:
            proj = ContentProjectionRecord(
                content_id=row[0],
                projection_kind=row[1],
                projection_json=row[2],
                updated_at=row[3],
            )
            projections.append(proj)
        except ValueError:
            continue

    return projections


def delete_projection(
    conn: sqlite3.Connection,
    content_id: str,
    projection_kind: str,
) -> bool:
    """Delete a specific projection.

    Args:
        conn: Database connection.
        content_id: Content item ID.
        projection_kind: Type of projection to delete.

    Returns:
        True if deleted, False if not found.
    """
    cursor = conn.execute(
        "DELETE FROM content_projection WHERE content_id = ? AND projection_kind = ?",
        (content_id, projection_kind),
    )
    conn.commit()
    return cursor.rowcount > 0
