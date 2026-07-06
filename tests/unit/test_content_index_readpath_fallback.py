"""Tests for content index fallback behavior.

Tests that index failures trigger appropriate fallback to direct read path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from k8s_diag_agent.content_index import (
    ContentIndexConfig,
    FallbackReason,
    IndexReadResult,
)
from k8s_diag_agent.content_index.readpath import (
    ContentIndexReader,
    get_incident_from_index,
    list_incidents_from_index,
)


class TestDisabledPath:
    """Test that disabled path never opens the index."""

    def test_disabled_skips_index(self) -> None:
        """Test that disabled config never attempts to open index."""
        config = ContentIndexConfig(enabled=False, db_path=None)
        reader = ContentIndexReader(config)

        # Should return fallback immediately without trying to open
        result = reader.read_incidents_list()

        assert result.fallback_reason == FallbackReason.INDEX_NOT_ENABLED
        assert result.index_available is False
        assert result.data is None

    def test_disabled_with_nonexistent_path(self) -> None:
        """Test that disabled config ignores nonexistent db path."""
        config = ContentIndexConfig(
            enabled=False,
            db_path=Path("/definitely/nonexistent/path.sqlite"),
        )
        result = list_incidents_from_index(config)

        assert result.fallback_reason == FallbackReason.INDEX_NOT_ENABLED
        assert result.index_available is False


class TestMissingDBFallback:
    """Test that missing database triggers fallback."""

    def test_missing_db_falls_back(self) -> None:
        """Test that nonexistent DB path falls back."""
        config = ContentIndexConfig(
            enabled=True,
            db_path=Path("/definitely/nonexistent/content-index.sqlite"),
        )
        result = list_incidents_from_index(config)

        assert result.index_available is False
        assert result.fallback_reason == FallbackReason.INDEX_NOT_FOUND

    def test_missing_db_detail_falls_back(self) -> None:
        """Test that get_incident also falls back on missing DB."""
        config = ContentIndexConfig(
            enabled=True,
            db_path=Path("/definitely/nonexistent/content-index.sqlite"),
        )
        result = get_incident_from_index(config, "incident-test-001")

        assert result.index_available is False
        assert result.fallback_reason == FallbackReason.INDEX_NOT_FOUND


class TestCorruptDBFallback:
    """Test that corrupt database triggers fallback."""

    def test_corrupt_db_falls_back(self, corrupt_db_path: Path) -> None:
        """Test that corrupt DB falls back."""
        config = ContentIndexConfig(enabled=True, db_path=corrupt_db_path)
        result = list_incidents_from_index(config)

        assert result.index_available is False
        # Corrupt DB causes validation to fail
        assert result.fallback_reason in (
            FallbackReason.INDEX_NOT_FOUND,
            FallbackReason.INDEX_SCHEMA_MISMATCH,
            FallbackReason.INDEX_VALIDATION_FAILED,
        )

    @pytest.fixture
    def corrupt_db_path(self) -> Path:
        """Create a corrupt database path (not a valid SQLite file)."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            f.write(b"This is not a valid SQLite database")
            path = Path(f.name)
        yield path
        path.unlink(missing_ok=True)


class TestSchemaMismatchFallback:
    """Test that schema mismatch triggers fallback."""

    def test_wrong_schema_falls_back(self, wrong_schema_db_path: Path) -> None:
        """Test that wrong schema version falls back."""
        config = ContentIndexConfig(enabled=True, db_path=wrong_schema_db_path)
        result = list_incidents_from_index(config)

        assert result.index_available is False
        assert result.fallback_reason == FallbackReason.INDEX_SCHEMA_MISMATCH

    @pytest.fixture
    def wrong_schema_db_path(self) -> Path:
        """Create a database with wrong schema version."""
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            db_path = Path(f.name)

        conn = sqlite3.connect(str(db_path))
        try:
            schema_sql = (
                Path(__file__).parent.parent.parent
                / "src/k8s_diag_agent/content_index/schema.sql"
            )
            conn.executescript(schema_sql.read_text())

            # Insert WRONG metadata
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("schema_version", "k9b.content_index.v99"),
            )
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("created_at", "2024-01-01T00:00:00+00:00"),
            )

            conn.commit()
        finally:
            conn.close()

        yield db_path

        db_path.unlink(missing_ok=True)


class TestFallbackReasonCodes:
    """Test that fallback reasons are bounded and safe."""

    def test_all_fallback_reasons_are_strings(self) -> None:
        """Test that all FallbackReason values are strings."""
        assert isinstance(FallbackReason.INDEX_NOT_ENABLED, str)
        assert isinstance(FallbackReason.INDEX_NOT_AVAILABLE, str)
        assert isinstance(FallbackReason.INDEX_NOT_FOUND, str)
        assert isinstance(FallbackReason.INDEX_CORRUPT, str)
        assert isinstance(FallbackReason.INDEX_SCHEMA_MISMATCH, str)
        assert isinstance(FallbackReason.INDEX_VALIDATION_FAILED, str)
        assert isinstance(FallbackReason.INDEX_OPEN_ERROR, str)
        assert isinstance(FallbackReason.PROJECTION_ERROR, str)

    def test_fallback_reason_is_bounded(self) -> None:
        """Test that fallback reason is a bounded, safe value."""
        config = ContentIndexConfig(
            enabled=True,
            db_path=Path("/definitely/nonexistent/path.sqlite"),
        )
        result = list_incidents_from_index(config)

        # Reason should be one of the defined codes
        valid_reasons = [
            FallbackReason.INDEX_NOT_ENABLED,
            FallbackReason.INDEX_NOT_AVAILABLE,
            FallbackReason.INDEX_NOT_FOUND,
            FallbackReason.INDEX_CORRUPT,
            FallbackReason.INDEX_SCHEMA_MISMATCH,
            FallbackReason.INDEX_VALIDATION_FAILED,
            FallbackReason.INDEX_OPEN_ERROR,
            FallbackReason.PROJECTION_ERROR,
        ]
        assert result.fallback_reason in valid_reasons


class TestIndexReadResultFallback:
    """Test IndexReadResult fallback creation."""

    def test_fallback_result(self) -> None:
        """Test creating a fallback result."""
        result = IndexReadResult.fallback(FallbackReason.INDEX_NOT_FOUND, count=0)

        assert result.data is None
        assert result.fallback_reason == FallbackReason.INDEX_NOT_FOUND
        assert result.schema_version is None
        assert result.count == 0
        assert result.index_available is False

    def test_fallback_with_count(self) -> None:
        """Test fallback result with non-zero count."""
        result = IndexReadResult.fallback(FallbackReason.INDEX_NOT_FOUND, count=5)

        assert result.count == 5
        assert result.index_available is False
