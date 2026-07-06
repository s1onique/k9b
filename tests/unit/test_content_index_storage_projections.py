"""Tests for content index storage projections.

Tests projection CRUD operations.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.content_index.schema import (
    ContentIndexRecord,
    ContentProjectionRecord,
)
from k8s_diag_agent.content_index.storage import (
    delete_projection,
    get_projection,
    get_projections_for_item,
    initialize_database,
    upsert_content_item,
    upsert_projection,
)


class TestProjectionOperations:
    """Test projection CRUD operations."""

    def test_upsert_projection_inserts(self, tmp_path: Path) -> None:
        """Upsert inserts a new projection."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # First create the content item (required for FK constraint)
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

        projection = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123", "status": "open"}),
            updated_at=datetime.now(UTC).isoformat(),
        )

        upsert_projection(conn, projection)

        retrieved = get_projection(conn, "test-123", "api_summary")
        assert retrieved is not None
        assert retrieved.content_id == "test-123"
        assert retrieved.projection_kind == "api_summary"

        # Verify JSON is valid
        data = json.loads(retrieved.projection_json)
        assert data["id"] == "123"
        conn.close()

    def test_upsert_projection_updates(self, tmp_path: Path) -> None:
        """Upsert updates an existing projection."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # First create the content item (required for FK constraint)
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

        projection1 = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123", "status": "open"}),
            updated_at=datetime.now(UTC).isoformat(),
        )
        upsert_projection(conn, projection1)

        projection2 = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123", "status": "closed"}),
            updated_at=datetime.now(UTC).isoformat(),
        )
        upsert_projection(conn, projection2)

        retrieved = get_projection(conn, "test-123", "api_summary")
        assert retrieved is not None

        data = json.loads(retrieved.projection_json)
        assert data["status"] == "closed"
        conn.close()

    def test_delete_projection(self, tmp_path: Path) -> None:
        """Delete removes a projection."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # First create the content item (required for FK constraint)
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

        projection = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123"}),
            updated_at=datetime.now(UTC).isoformat(),
        )
        upsert_projection(conn, projection)

        result = delete_projection(conn, "test-123", "api_summary")
        assert result is True

        retrieved = get_projection(conn, "test-123", "api_summary")
        assert retrieved is None
        conn.close()

    def test_get_projections_for_item(self, tmp_path: Path) -> None:
        """Get projections for item returns all projections."""
        db_path = tmp_path / "test.sqlite"
        conn = initialize_database(db_path)

        # First create the content item (required for FK constraint)
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

        proj1 = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123"}),
            updated_at=datetime.now(UTC).isoformat(),
        )
        proj2 = ContentProjectionRecord(
            content_id="test-123",
            projection_kind="api_detail",
            projection_json=json.dumps({"id": "123", "detail": True}),
            updated_at=datetime.now(UTC).isoformat(),
        )
        upsert_projection(conn, proj1)
        upsert_projection(conn, proj2)

        projections = get_projections_for_item(conn, "test-123")
        assert len(projections) == 2
        conn.close()
