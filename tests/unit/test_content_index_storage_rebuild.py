"""Tests for content index storage rebuild operations.

Tests atomic database replacement.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from k8s_diag_agent.content_index.storage_connection import (
    get_connection,
    initialize_database,
)
from k8s_diag_agent.content_index.storage_rebuild import atomically_replace_database


class TestAtomicDatabaseReplacement:
    """Test atomic database replacement."""

    def test_raises_for_missing_temp_db(self, tmp_path: Path) -> None:
        """Atomically replace raises FileNotFoundError if temp DB doesn't exist."""
        target_path = tmp_path / "target.sqlite"
        temp_path = tmp_path / "nonexistent.sqlite"

        # Create target DB
        with initialize_database(target_path) as conn:
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("test_key", "test_value"),
            )
            conn.commit()

        # Verify target exists
        with get_connection(target_path, read_only=True) as conn:
            cursor = conn.execute(
                "SELECT value FROM content_index_metadata WHERE key = ?",
                ("test_key",),
            )
            assert cursor.fetchone()[0] == "test_value"

        # Should raise FileNotFoundError for missing temp
        try:
            atomically_replace_database(target_path, temp_path)
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError as e:
            assert "Temp database not found" in str(e)

    def test_works_when_target_does_not_exist(self, tmp_path: Path) -> None:
        """Atomically replace works when target DB doesn't exist."""
        target_path = tmp_path / "new_target.sqlite"
        temp_path = tmp_path / "temp.sqlite"

        assert not target_path.exists()

        # Create temp DB
        with initialize_database(temp_path) as conn:
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("test_key", "test_value"),
            )
            conn.commit()

        # Replace should succeed
        atomically_replace_database(target_path, temp_path)

        # Target should now exist
        assert target_path.exists()
        assert not temp_path.exists()

        # Verify contents
        with get_connection(target_path, read_only=True) as conn:
            cursor = conn.execute(
                "SELECT value FROM content_index_metadata WHERE key = ?",
                ("test_key",),
            )
            assert cursor.fetchone()[0] == "test_value"

    def test_works_when_target_already_exists(self, tmp_path: Path) -> None:
        """Atomically replace works when target DB already exists."""
        target_path = tmp_path / "existing_target.sqlite"
        temp_path = tmp_path / "temp.sqlite"

        # Create initial target DB with some data
        with initialize_database(target_path) as conn:
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("original", "old_value"),
            )
            conn.commit()

        # Create temp DB with different data
        with initialize_database(temp_path) as conn:
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("replacement", "new_value"),
            )
            conn.commit()

        # Replace should succeed
        atomically_replace_database(target_path, temp_path)

        # Target should exist and have new content
        assert target_path.exists()
        assert not temp_path.exists()

        # Verify new content
        with get_connection(target_path, read_only=True) as conn:
            # Old key should be gone
            cursor = conn.execute(
                "SELECT value FROM content_index_metadata WHERE key = ?",
                ("original",),
            )
            assert cursor.fetchone() is None

            # New key should exist
            cursor = conn.execute(
                "SELECT value FROM content_index_metadata WHERE key = ?",
                ("replacement",),
            )
            assert cursor.fetchone()[0] == "new_value"

    def test_replaced_db_validates_successfully(self, tmp_path: Path) -> None:
        """Replaced database is a valid SQLite database."""
        target_path = tmp_path / "target.sqlite"
        temp_path = tmp_path / "temp.sqlite"

        # Create temp DB with valid content
        with initialize_database(temp_path) as conn:
            conn.execute(
                "INSERT INTO content_item (content_id, content_kind, source_path, source_path_kind, source_mtime_ns, source_size_bytes, source_sha256, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("item1", "incident", "rel/path.yaml", "incident_store", 0, 100, "abc123", "2024-01-01T00:00:00"),
            )
            conn.commit()

        # Replace
        atomically_replace_database(target_path, temp_path)

        # Verify the DB is valid by opening it and querying
        conn = sqlite3.connect(str(target_path))
        try:
            cursor = conn.execute("PRAGMA integrity_check")
            assert cursor.fetchone()[0] == "ok"
        finally:
            conn.close()

    def test_creates_target_parent_directory(self, tmp_path: Path) -> None:
        """Atomically replace creates target parent directory if needed."""
        target_path = tmp_path / "nested" / "dir" / "target.sqlite"
        temp_path = tmp_path / "temp.sqlite"

        assert not target_path.parent.exists()

        with initialize_database(temp_path):
            pass

        atomically_replace_database(target_path, temp_path)

        assert target_path.exists()
        assert target_path.parent.exists()

    def test_replacement_file_cleaned_up(self, tmp_path: Path) -> None:
        """No leftover replacement file after atomic replace."""
        target_path = tmp_path / "target.sqlite"
        temp_path = tmp_path / "temp.sqlite"
        replacement_path = target_path.with_suffix(target_path.suffix + ".replacement")

        with initialize_database(target_path):
            pass
        with initialize_database(temp_path):
            pass

        assert not replacement_path.exists()

        atomically_replace_database(target_path, temp_path)

        # No replacement file left behind
        assert not replacement_path.exists()
        assert target_path.exists()

    def test_temp_file_not_left_behind(self, tmp_path: Path) -> None:
        """No leftover temp file after atomic replace."""
        target_path = tmp_path / "target.sqlite"
        temp_path = tmp_path / "temp.sqlite"

        with initialize_database(target_path):
            pass
        with initialize_database(temp_path):
            pass

        atomically_replace_database(target_path, temp_path)

        # Temp file should be gone
        assert not temp_path.exists()
        assert target_path.exists()
