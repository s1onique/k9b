"""Content index storage validation.

This module provides database validation operations.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    REQUIRED_COLUMNS,
    REQUIRED_TABLES,
    check_forbidden_fields,
)
from .storage_metadata import get_schema_version


def validate_database(conn: sqlite3.Connection) -> dict[str, Any]:
    """Validate the content index database.

    Checks:
    - Schema version matches
    - Required tables exist
    - Required columns exist
    - Projections contain valid JSON
    - No forbidden fields in projections
    - No absolute paths in source_path
    - Deleted marker is 0 or 1

    Args:
        conn: Database connection.

    Returns:
        Dictionary with validation results.
    """
    result: dict[str, Any] = {
        "valid": True,
        "schema_version": get_schema_version(conn),
        "errors": [],
        "warnings": [],
    }

    # Check schema version
    if result["schema_version"] != CONTENT_INDEX_SCHEMA_VERSION:
        result["valid"] = False
        result["errors"].append(
            f"Schema version mismatch: expected {CONTENT_INDEX_SCHEMA_VERSION}, "
            f"got {result['schema_version']}"
        )

    # Check required tables
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}

    for table in REQUIRED_TABLES:
        if table not in existing_tables:
            result["valid"] = False
            result["errors"].append(f"Missing required table: {table}")

    # Check required columns for each table
    if "content_item" in existing_tables:
        cursor = conn.execute("PRAGMA table_info(content_item)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col in REQUIRED_COLUMNS.get("content_item", set()):
            if col not in existing_cols:
                result["valid"] = False
                result["errors"].append(f"Missing required column in content_item: {col}")

    # Validate projections JSON and check for forbidden fields
    if "content_projection" in existing_tables:
        cursor = conn.execute("SELECT projection_json FROM content_projection")
        for row in cursor.fetchall():
            try:
                data = json.loads(row[0])
                forbidden = check_forbidden_fields(data)
                if forbidden:
                    result["warnings"].append(
                        f"Projection contains forbidden fields: {forbidden}"
                    )
            except json.JSONDecodeError:
                result["valid"] = False
                result["errors"].append("Projection contains invalid JSON")

    # Check for absolute paths in source_path
    if "content_item" in existing_tables:
        cursor = conn.execute(
            "SELECT content_id, source_path FROM content_item WHERE source_path LIKE '/%'"
        )
        bad_paths = cursor.fetchall()
        if bad_paths:
            result["valid"] = False
            result["errors"].append(
                f"Found {len(bad_paths)} items with absolute paths: "
                f"{[p[1] for p in bad_paths[:5]]}"
            )

    # Check deleted marker values
    if "content_item" in existing_tables:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM content_item WHERE deleted NOT IN (0, 1)"
        )
        bad_count = cursor.fetchone()[0]
        if bad_count > 0:
            result["valid"] = False
            result["errors"].append(
                f"Found {bad_count} items with invalid deleted marker"
            )

    return result


def count_items(conn: sqlite3.Connection) -> dict[str, int]:
    """Count items in the index.

    Args:
        conn: Database connection.

    Returns:
        Dictionary with item counts.
    """
    cursor = conn.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(deleted) as deleted,
            SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END) as active
        FROM content_item
        """
    )
    row = cursor.fetchone()

    cursor2 = conn.execute(
        "SELECT COUNT(*) FROM content_projection"
    )
    proj_count = cursor2.fetchone()[0]

    return {
        "total_items": row[0] if row[0] else 0,
        "deleted_items": row[1] if row[1] else 0,
        "active_items": row[2] if row[2] else 0,
        "projections": proj_count,
    }


def count_by_kind(conn: sqlite3.Connection) -> dict[str, int]:
    """Count items by content kind.

    Args:
        conn: Database connection.

    Returns:
        Dictionary mapping content kind to count.
    """
    cursor = conn.execute(
        """
        SELECT content_kind, COUNT(*) as count
        FROM content_item
        GROUP BY content_kind
        """
    )
    return {row[0]: row[1] for row in cursor.fetchall()}
