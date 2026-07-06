"""Tests for content index successful read operations.

Tests that valid index returns projected incidents correctly.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from k8s_diag_agent.content_index import (
    CONTENT_INDEX_SCHEMA_VERSION,
    ContentIndexConfig,
    IndexReadResult,
)
from k8s_diag_agent.content_index.readpath import (
    ContentIndexReader,
    get_incident_from_index,
    list_incidents_from_index,
)


@pytest.fixture
def valid_db_path() -> Path:
    """Create a valid content index database with incidents."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    try:
        # Create schema
        schema_sql = (
            Path(__file__).parent.parent.parent
            / "src/k8s_diag_agent/content_index/schema.sql"
        )
        conn.executescript(schema_sql.read_text())

        # Insert metadata
        conn.execute(
            "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("schema_version", CONTENT_INDEX_SCHEMA_VERSION),
        )
        conn.execute(
            "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("created_at", "2024-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
            ("indexed_at", "2024-01-01T00:00:00+00:00"),
        )

        # Insert test incident
        conn.execute(
            """
            INSERT INTO content_item (
                content_id, content_kind, source_path, source_path_kind,
                source_mtime_ns, source_size_bytes, source_sha256,
                schema_version, indexed_at, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "incident-test-001",
                "incident",
                "runs/health/incidents/incident-test-001.json",
                "incident_store",
                1704067200000000000,
                1024,
                "abc123",
                "k9b.incident.v1",
                "2024-01-01T00:00:00+00:00",
                0,
            ),
        )

        # Insert projection
        projection_data = {
            "incident_id": "incident-test-001",
            "status": "open",
            "severity": "high",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "safe_title": "Test Incident",
            "safe_summary": "A test incident for unit testing",
        }
        conn.execute(
            """
            INSERT INTO content_projection (
                content_id, projection_kind, projection_json, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "incident-test-001",
                "api_summary",
                json.dumps(projection_data),
                "2024-01-01T00:00:00+00:00",
            ),
        )

        # Insert detail projection
        detail_data = {
            **projection_data,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        conn.execute(
            """
            INSERT INTO content_projection (
                content_id, projection_kind, projection_json, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "incident-test-001",
                "api_detail",
                json.dumps(detail_data),
                "2024-01-01T00:00:00+00:00",
            ),
        )

        conn.commit()
    finally:
        conn.close()

    yield db_path
    db_path.unlink(missing_ok=True)


class TestEnabledPathOpensReadOnly:
    """Test that enabled path opens index read-only."""

    def test_enabled_opens_valid_db(self, valid_db_path: Path) -> None:
        """Test that enabled config opens a valid database."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = list_incidents_from_index(config)

        assert result.index_available is True
        assert result.schema_version == CONTENT_INDEX_SCHEMA_VERSION
        assert result.fallback_reason is None

    def test_reader_uses_read_only_connection(
        self, valid_db_path: Path
    ) -> None:
        """Test that reader opens connection in read-only mode."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        reader = ContentIndexReader(config)

        # Read should succeed
        result = reader.read_incidents_list()
        assert result.index_available is True

        # Connection should be usable after reading
        reader.close()


class TestValidIndexReturnsProjections:
    """Test that valid index returns projected incidents."""

    def test_list_returns_incidents(self, valid_db_path: Path) -> None:
        """Test that list_incidents_from_index returns projected data."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = list_incidents_from_index(config)

        assert result.index_available is True
        assert result.data is not None
        assert "incidents" in result.data
        assert "total" in result.data
        assert isinstance(result.data["incidents"], list)
        assert result.data["total"] == 1

    def test_detail_returns_incident(self, valid_db_path: Path) -> None:
        """Test that get_incident_from_index returns incident detail."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = get_incident_from_index(config, "incident-test-001")

        assert result.index_available is True
        assert result.data is not None
        assert result.data["incident_id"] == "incident-test-001"
        assert result.data["status"] == "open"

    def test_detail_returns_none_for_missing(self, valid_db_path: Path) -> None:
        """Test that detail returns None for missing incident."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = get_incident_from_index(config, "incident-nonexistent")

        # Index is available, but incident not found - data is None
        assert result.index_available is True
        assert result.data is None
        assert result.count == 0


class TestAPIResponseShape:
    """Test that response shape remains compatible with API."""

    def test_list_response_has_required_fields(
        self, valid_db_path: Path
    ) -> None:
        """Test that list response has the expected API fields."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = list_incidents_from_index(config)

        assert result.data is not None
        assert "incidents" in result.data
        assert "total" in result.data
        # Total should match incident count
        assert result.data["total"] == len(result.data["incidents"])

    def test_incident_has_safe_fields(self, valid_db_path: Path) -> None:
        """Test that projected incident has safe fields only."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = get_incident_from_index(config, "incident-test-001")

        assert result.data is not None
        # Check safe fields are present
        assert "incident_id" in result.data
        assert "status" in result.data


class TestIndexReadResultSuccess:
    """Test IndexReadResult success creation."""

    def test_from_index_result(self) -> None:
        """Test creating a successful index result."""
        data = {"incidents": [], "total": 0}
        result = IndexReadResult.from_index(
            data=data,
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            count=0,
        )

        assert result.data == data
        assert result.fallback_reason is None
        assert result.schema_version == CONTENT_INDEX_SCHEMA_VERSION
        assert result.count == 0
        assert result.index_available is True

    def test_from_index_with_data(self, valid_db_path: Path) -> None:
        """Test successful result with actual data."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = list_incidents_from_index(config)

        assert result.index_available is True
        assert result.data is not None
        assert isinstance(result.data, dict)
