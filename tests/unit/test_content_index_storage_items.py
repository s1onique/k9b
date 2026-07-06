"""Tests for content index storage items.

Tests content item CRUD operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.content_index.schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    ContentIndexRecord,
)
from k8s_diag_agent.content_index.storage import (
    get_all_content_items,
    get_content_item,
    initialize_database,
    tombstone_content_item,
    upsert_content_item,
)


class TestContentItemOperations:
    """Test content item CRUD operations."""

    def test_upsert_content_item_inserts(self, tmp_path: Path) -> None:
        """Upsert inserts a new content item."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="incidents/123.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            indexed_at=datetime.now(UTC).isoformat(),
        )

        upsert_content_item(conn, record)

        retrieved = get_content_item(conn, "test-123")
        assert retrieved is not None
        assert retrieved.content_id == "test-123"
        assert retrieved.content_kind == "incident"
        assert retrieved.source_sha256 == "abc123"
        conn.close()

    def test_upsert_content_item_updates(self, tmp_path: Path) -> None:
        """Upsert updates an existing content item."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        record1 = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="incidents/123.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            indexed_at=datetime.now(UTC).isoformat(),
        )
        upsert_content_item(conn, record1)

        record2 = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="incidents/123.json",
            source_path_kind="incident_store",
            source_mtime_ns=2000000000,
            source_size_bytes=2048,
            source_sha256="def456",
            indexed_at=datetime.now(UTC).isoformat(),
        )
        upsert_content_item(conn, record2)

        retrieved = get_content_item(conn, "test-123")
        assert retrieved is not None
        assert retrieved.source_mtime_ns == 2000000000
        assert retrieved.source_size_bytes == 2048
        assert retrieved.source_sha256 == "def456"
        conn.close()

    def test_upsert_rejects_absolute_path(self, tmp_path: Path) -> None:
        """Upsert rejects absolute paths in source_path."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # ValueError should be raised when creating the record with absolute path
        with pytest.raises(ValueError, match="must be relative"):
            ContentIndexRecord(
                content_id="test-123",
                content_kind="incident",
                source_path="/absolute/path.json",
                source_path_kind="incident_store",
                source_mtime_ns=1000000000,
                source_size_bytes=1024,
                source_sha256="abc123",
                indexed_at=datetime.now(UTC).isoformat(),
            )
        conn.close()

    def test_get_all_content_items(self, tmp_path: Path) -> None:
        """Get all content items returns all items."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        for i in range(3):
            record = ContentIndexRecord(
                content_id=f"test-{i}",
                content_kind="incident",
                source_path=f"incidents/{i}.json",
                source_path_kind="incident_store",
                source_mtime_ns=1000000000,
                source_size_bytes=1024,
                source_sha256=f"hash{i}",
                indexed_at=datetime.now(UTC).isoformat(),
            )
            upsert_content_item(conn, record)

        items = get_all_content_items(conn)
        assert len(items) == 3
        conn.close()


class TestTombstoneOperations:
    """Test tombstone operations."""

    def test_tombstone_content_item(self, tmp_path: Path) -> None:
        """Tombstone marks an item as deleted."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="incidents/123.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            indexed_at=datetime.now(UTC).isoformat(),
        )
        upsert_content_item(conn, record)

        result = tombstone_content_item(conn, "test-123")
        assert result is True

        item = get_content_item(conn, "test-123")
        assert item is not None
        assert item.deleted is True
        conn.close()

    def test_tombstone_nonexistent_returns_false(self, tmp_path: Path) -> None:
        """Tombstone returns False for nonexistent item."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        result = tombstone_content_item(conn, "nonexistent")
        assert result is False
        conn.close()
