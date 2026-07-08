"""Unit tests for SQLite incident store schema and migrations.

These tests verify:
- Schema creation (tables, triggers, indexes)
- Migration management
- Immutability constraints via triggers
- WAL mode warnings
"""

import os
import sqlite3
import tempfile

import pytest

from k8s_diag_agent.collect.incident_store_sqlite_migrations import (
    get_current_version,
    run_migrations,
    verify_schema,
)
from k8s_diag_agent.collect.incident_store_sqlite_schema import (
    SCHEMA_VERSION,
    get_schema_sql,
    is_network_path,
    verify_append_only_constraint,
)


class TestGetSchemaSql:
    """Tests for get_schema_sql() function."""

    def test_returns_list_of_sql_statements(self) -> None:
        """Schema SQL should be returned as a list."""
        sql_list = get_schema_sql()
        assert isinstance(sql_list, list)
        assert len(sql_list) > 0

    def test_schema_version_is_set(self) -> None:
        """SCHEMA_VERSION should be a positive integer."""
        assert isinstance(SCHEMA_VERSION, int)
        assert SCHEMA_VERSION > 0


class TestRunMigrations:
    """Tests for run_migrations() function."""

    def test_fresh_database_initializes_schema(self) -> None:
        """A fresh database should get the full schema applied."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                version = run_migrations(conn)
                assert version == SCHEMA_VERSION

                # Verify tables exist
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = {row[0] for row in cursor.fetchall()}
                assert "incident_events" in tables
                assert "incident_current" in tables
                assert "schema_migrations" in tables

                # Verify migration was recorded
                cursor = conn.execute("SELECT version FROM schema_migrations")
                versions = [row[0] for row in cursor.fetchall()]
                assert SCHEMA_VERSION in versions
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_idempotent_migrations(self) -> None:
        """Running migrations twice should be safe (idempotent)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                # First run
                version1 = run_migrations(conn)
                assert version1 == SCHEMA_VERSION

                # Second run (should be no-op)
                version2 = run_migrations(conn)
                assert version2 == SCHEMA_VERSION

                # Only one migration record per version
                cursor = conn.execute("SELECT version, COUNT(*) FROM schema_migrations GROUP BY version")
                for row in cursor.fetchall():
                    assert row[1] == 1
            finally:
                conn.close()
        finally:
            os.unlink(db_path)


class TestGetCurrentVersion:
    """Tests for get_current_version() function."""

    def test_no_schema_returns_zero(self) -> None:
        """Database with no schema should return version 0."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                version = get_current_version(conn)
                assert version == 0
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_with_schema_returns_version(self) -> None:
        """Database with schema should return the version."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                version = get_current_version(conn)
                assert version == SCHEMA_VERSION
            finally:
                conn.close()
        finally:
            os.unlink(db_path)


class TestVerifySchema:
    """Tests for verify_schema() function."""

    def test_verifies_all_tables_present(self) -> None:
        """verify_schema should report all expected tables."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                result = verify_schema(conn)

                assert "incident_events" in result["tables"]
                assert "incident_current" in result["tables"]
                assert "schema_migrations" in result["tables"]
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_verifies_triggers_present(self) -> None:
        """verify_schema should report triggers."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                result = verify_schema(conn)

                assert len(result["triggers"]) > 0
                # Should have the immutability triggers
                trigger_names = list(result["triggers"].keys())
                assert any("incident_events_no_delete" in name for name in trigger_names)
                assert any("incident_events_no_update" in name for name in trigger_names)
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_verifies_indexes_present(self) -> None:
        """verify_schema should report indexes."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                result = verify_schema(conn)

                assert len(result["indexes"]) > 0
                # Should have indexes with idx_ prefix
                assert all(idx.startswith("idx_") for idx in result["indexes"])
            finally:
                conn.close()
        finally:
            os.unlink(db_path)


class TestImmutabilityConstraint:
    """Tests for append-only immutability via triggers."""

    def test_delete_is_blocked(self) -> None:
        """DELETE on incident_events should be blocked by trigger."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)

                # Insert a test event
                conn.execute(
                    """INSERT INTO incident_events 
                       (event_id, incident_id, aggregate_version, event_type, 
                        occurred_at, actor, payload_json, payload_sha256, 
                        event_sha256, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "test-event-1",
                        "incident-1",
                        1,
                        "incident.opened",
                        "2024-01-01T00:00:00+00:00",
                        "system",
                        "{}",
                        "abc123",
                        "def456",
                        "2024-01-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

                # Attempt to delete should raise
                with pytest.raises(sqlite3.IntegrityError) as exc_info:
                    conn.execute("DELETE FROM incident_events")
                # SQLite raises "incident_events is append-only"
                assert "append-only" in str(exc_info.value).lower()
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_update_is_blocked(self) -> None:
        """UPDATE on incident_events should be blocked by trigger."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)

                # Insert a test event
                conn.execute(
                    """INSERT INTO incident_events 
                       (event_id, incident_id, aggregate_version, event_type, 
                        occurred_at, actor, payload_json, payload_sha256, 
                        event_sha256, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "test-event-1",
                        "incident-1",
                        1,
                        "incident.opened",
                        "2024-01-01T00:00:00+00:00",
                        "system",
                        "{}",
                        "abc123",
                        "def456",
                        "2024-01-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

                # Attempt to update should raise
                with pytest.raises(sqlite3.IntegrityError) as exc_info:
                    conn.execute("UPDATE incident_events SET event_type = ? WHERE event_id = ?", 
                                ("incident.updated", "test-event-1"))
                # SQLite raises "incident_events is append-only"
                assert "append-only" in str(exc_info.value).lower()
            finally:
                conn.close()
        finally:
            os.unlink(db_path)


class TestVerifyAppendOnlyConstraint:
    """Tests for verify_append_only_constraint() helper."""

    def test_verify_returns_correct_tables(self) -> None:
        """Should return correct structure for table checking."""
        result = verify_append_only_constraint()
        assert isinstance(result, dict)
        assert "immutable_tables" in result
        assert "blocked_operations" in result
        assert "incident_events" in result["immutable_tables"]
        assert "DELETE" in result["blocked_operations"]
        assert "UPDATE" in result["blocked_operations"]


class TestPragmaSettings:
    """Tests for SQLite pragma settings."""

    def test_foreign_keys_can_be_enabled(self) -> None:
        """Foreign keys should be able to be enabled for data integrity."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                # Enable foreign keys explicitly
                conn.execute("PRAGMA foreign_keys = ON")
                cursor = conn.execute("PRAGMA foreign_keys")
                (fk_enabled,) = cursor.fetchone()
                assert fk_enabled == 1
            finally:
                conn.close()
        finally:
            os.unlink(db_path)

    def test_journal_mode_is_delete(self) -> None:
        """Journal mode should be DELETE by default (not WAL)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            try:
                run_migrations(conn)
                cursor = conn.execute("PRAGMA journal_mode")
                (mode,) = cursor.fetchone()
                # Default should be DELETE, not WAL
                assert mode.upper() == "DELETE"
            finally:
                conn.close()
        finally:
            os.unlink(db_path)


class TestIsNetworkPath:
    """Tests for is_network_path() function."""

    def test_network_paths(self) -> None:
        """Should detect network mount paths."""
        network_paths = [
            "/mnt/nfs/data/incidents.db",
            "/volumes/shared/incidents.db",
            "/network/slow-storage/incidents.db",
            "//server/share/incidents.db",
        ]
        for path in network_paths:
            assert is_network_path(path) is True, f"Should detect: {path}"

    def test_local_paths(self) -> None:
        """Should not flag local paths as network."""
        local_paths = [
            "/tmp/incidents.db",
            "/var/data/incidents.db",
            "/home/user/incidents.db",
            "incidents.db",
            "./incidents.db",
        ]
        for path in local_paths:
            assert is_network_path(path) is False, f"Should not detect: {path}"
