"""Tests for content index storage connection.

Tests database initialization.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from k8s_diag_agent.content_index.schema import CONTENT_INDEX_SCHEMA_VERSION
from k8s_diag_agent.content_index.storage import (
    get_metadata,
    get_schema_version,
    initialize_database,
)


class TestDatabaseInitialization:
    """Test database initialization."""

    def test_initialize_database_creates_tables(self, tmp_path: Path) -> None:
        """Database initialization creates all required tables."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

            assert "content_index_metadata" in tables
            assert "content_item" in tables
            assert "content_projection" in tables
        finally:
            conn.close()

    def test_initialize_database_writes_schema_version(self, tmp_path: Path) -> None:
        """Database initialization writes schema version."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        try:
            version = get_schema_version(conn)
            assert version == CONTENT_INDEX_SCHEMA_VERSION
        finally:
            conn.close()

    def test_initialize_database_writes_created_at(self, tmp_path: Path) -> None:
        """Database initialization writes created_at."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        try:
            created_at = get_metadata(conn, "created_at")
            assert created_at is not None
            # Should be a valid ISO timestamp
            datetime.fromisoformat(created_at)
        finally:
            conn.close()

    def test_initialize_database_writes_indexed_at(self, tmp_path: Path) -> None:
        """Database initialization writes indexed_at."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        try:
            indexed_at = get_metadata(conn, "indexed_at")
            assert indexed_at is not None
            datetime.fromisoformat(indexed_at)
        finally:
            conn.close()

    def test_initialize_database_enables_foreign_keys(self, tmp_path: Path) -> None:
        """Database connection enables foreign keys."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        try:
            cursor = conn.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()
            assert result[0] == 1
        finally:
            conn.close()

    def test_initialize_creates_parent_directory(self, tmp_path: Path) -> None:
        """Database initialization creates parent directory if needed."""
        db_path = tmp_path / "subdir" / "nested" / "test.sqlite"
        assert not db_path.parent.exists()

        conn = initialize_database(db_path)
        conn.close()

        assert db_path.exists()
