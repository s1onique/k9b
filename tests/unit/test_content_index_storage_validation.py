"""Tests for content index storage validation and counts.

Tests validation and count operations.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.content_index.schema import (
    ContentIndexRecord,
)
from k8s_diag_agent.content_index.storage import (
    count_by_kind,
    count_items,
    initialize_database,
    tombstone_content_item,
    upsert_content_item,
    validate_database,
)


class TestValidation:
    """Test validation operations."""

    def test_validate_database_success(self, tmp_path: Path) -> None:
        """Validation succeeds for a valid database."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # Add a valid content item
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

        result = validate_database(conn)
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        conn.close()

    def test_validate_database_missing_tables(self, tmp_path: Path) -> None:
        """Validation fails when tables are missing."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE content_index_metadata (key TEXT, value TEXT)")
        conn.commit()

        result = validate_database(conn)
        assert result["valid"] is False
        assert any("content_item" in e for e in result["errors"])
        conn.close()

    def test_validate_database_invalid_projection_json(self, tmp_path: Path) -> None:
        """Validation fails for invalid projection JSON."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # First insert a content item so FK constraint passes
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

        # Then insert invalid JSON directly (bypassing ContentProjectionRecord validation)
        conn.execute(
            "INSERT INTO content_projection (content_id, projection_kind, projection_json, updated_at) VALUES (?, ?, ?, ?)",
            ("test-123", "api_summary", "not valid json {", datetime.now(UTC).isoformat()),
        )
        conn.commit()

        result = validate_database(conn)
        assert result["valid"] is False
        assert any("invalid JSON" in e for e in result["errors"])
        conn.close()

    def test_validate_database_absolute_path(self, tmp_path: Path) -> None:
        """Validation fails for absolute paths in source_path.

        Note: The CHECK constraint in the schema prevents absolute paths,
        so we verify this by checking the constraint behavior.
        """
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # Try to insert absolute path directly - should fail due to CHECK constraint
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            conn.execute(
                """INSERT INTO content_item
                   (content_id, content_kind, source_path, source_path_kind,
                    source_mtime_ns, source_size_bytes, source_sha256, indexed_at, deleted)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "test-123",
                    "incident",
                    "/absolute/path.json",
                    "incident_store",
                    1000000000,
                    1024,
                    "abc123",
                    datetime.now(UTC).isoformat(),
                    0,
                ),
            )
        conn.close()


class TestCountOperations:
    """Test count operations."""

    def test_count_items(self, tmp_path: Path) -> None:
        """Count items returns correct counts."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # Add some items
        for i in range(5):
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

        # Tombstone one
        tombstone_content_item(conn, "test-0")

        counts = count_items(conn)
        assert counts["total_items"] == 5
        assert counts["deleted_items"] == 1
        assert counts["active_items"] == 4
        conn.close()

    def test_count_by_kind(self, tmp_path: Path) -> None:
        """Count by kind groups correctly."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # Add items of different kinds
        for i in range(3):
            record = ContentIndexRecord(
                content_id=f"incident-{i}",
                content_kind="incident",
                source_path=f"incidents/{i}.json",
                source_path_kind="incident_store",
                source_mtime_ns=1000000000,
                source_size_bytes=1024,
                source_sha256=f"hash{i}",
                indexed_at=datetime.now(UTC).isoformat(),
            )
            upsert_content_item(conn, record)

        for i in range(2):
            record = ContentIndexRecord(
                content_id=f"lab-{i}",
                content_kind="lab_result",
                source_path=f"lab/{i}/lab-result.json",
                source_path_kind="lab",
                source_mtime_ns=1000000000,
                source_size_bytes=1024,
                source_sha256=f"labhash{i}",
                indexed_at=datetime.now(UTC).isoformat(),
            )
            upsert_content_item(conn, record)

        counts = count_by_kind(conn)
        assert counts["incident"] == 3
        assert counts["lab_result"] == 2
        conn.close()
