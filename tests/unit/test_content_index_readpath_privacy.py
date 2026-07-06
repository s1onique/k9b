"""Tests for content index privacy and safety.

Tests that projections don't leak sensitive data.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from k8s_diag_agent.content_index import (
    ContentIndexConfig,
)
from k8s_diag_agent.content_index.readpath import (
    get_incident_from_index,
    list_incidents_from_index,
)
from k8s_diag_agent.content_index.schema import FORBIDDEN_FIELD_PATTERNS


class TestPrivacySafety:
    """Test that projections don't leak sensitive data."""

    def test_projection_has_no_absolute_paths(self, valid_db_path: Path) -> None:
        """Test that projections don't contain absolute paths."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)

        # List incidents
        list_result = list_incidents_from_index(config)
        if list_result.data:
            for incident in list_result.data.get("incidents", []):
                incident_str = json.dumps(incident)
                # Should not contain absolute paths
                assert "/root/" not in incident_str
                assert "/home/" not in incident_str

        # Get detail
        detail_result = get_incident_from_index(config, "incident-test-001")
        if detail_result.data:
            detail_str = json.dumps(detail_result.data)
            assert "/root/" not in detail_str
            assert "/home/" not in detail_str

    def test_projection_has_no_forbidden_fields(
        self, valid_db_path: Path
    ) -> None:
        """Test that projections don't contain forbidden field patterns."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)
        result = get_incident_from_index(config, "incident-test-001")

        if result.data:
            # Check that none of the forbidden field patterns appear as keys
            for pattern in FORBIDDEN_FIELD_PATTERNS:
                assert pattern.lower() not in json.dumps(result.data).lower()

    def test_no_secrets_in_response(self, valid_db_path: Path) -> None:
        """Test that response doesn't contain secret-like values."""
        config = ContentIndexConfig(enabled=True, db_path=valid_db_path)

        # List
        list_result = list_incidents_from_index(config)
        if list_result.data:
            response_str = json.dumps(list_result.data)
            # Secret patterns should not appear
            assert "secret" not in response_str.lower()
            assert "token" not in response_str.lower()
            assert "password" not in response_str.lower()

        # Detail
        detail_result = get_incident_from_index(config, "incident-test-001")
        if detail_result.data:
            response_str = json.dumps(detail_result.data)
            assert "secret" not in response_str.lower()
            assert "token" not in response_str.lower()
            assert "password" not in response_str.lower()

    @pytest.fixture
    def valid_db_path(self) -> Path:
        """Create a valid content index database with incidents."""
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

            # Insert metadata
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("schema_version", "k9b.content_index.v1"),
            )
            conn.execute(
                "INSERT INTO content_index_metadata (key, value) VALUES (?, ?)",
                ("created_at", "2024-01-01T00:00:00+00:00"),
            )

            # Insert test incident with safe data only
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

            # Safe projection data
            projection_data = {
                "incident_id": "incident-test-001",
                "status": "open",
                "severity": "high",
                "safe_title": "Test Incident",
                "safe_summary": "A test incident",
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

            detail_data = {
                **projection_data,
                "created_at": "2024-01-01T00:00:00+00:00",
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
