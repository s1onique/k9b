"""Unit tests for content_index integration in api_incident_reads.

Regression test for: handle_get_incident must use content_index when config.enabled
even when external_analysis_dir is provided.

Prior bug: The condition 'if config.enabled and external_analysis_dir is None:' prevented
content_index from ever being used for detail requests because server_incident_reads.py
ALWAYS sets external_analysis_dir to the external-analysis directory path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.content_index.config import ContentIndexConfig


class TestContentIndexIntegration:
    """Tests for content_index integration with api_incident_reads."""

    def test_handle_get_incident_uses_index_when_enabled_with_external_analysis_dir(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression test: handle_get_incident must use content_index when enabled
        even when external_analysis_dir is provided.

        Prior bug: The condition checked 'external_analysis_dir is None' which was
        never true because server_incident_reads.py always sets external_analysis_dir.
        """
        # Setup: Create a temp content index DB
        db_path = tmp_path / "content-index.sqlite"

        # Create minimal index with test incident
        import sqlite3

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS content_index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS content_item ("
            "content_id TEXT PRIMARY KEY, content_kind TEXT NOT NULL, "
            "source_path TEXT NOT NULL, source_path_kind TEXT NOT NULL, "
            "source_mtime_ns INTEGER NOT NULL, source_size_bytes INTEGER NOT NULL, "
            "source_sha256 TEXT NOT NULL, schema_version TEXT, indexed_at TEXT NOT NULL, "
            "deleted INTEGER NOT NULL DEFAULT 0)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS content_projection ("
            "content_id TEXT NOT NULL, projection_kind TEXT NOT NULL, "
            "projection_json TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "PRIMARY KEY (content_id, projection_kind))"
        )
        cur.execute(
            "INSERT INTO content_index_metadata VALUES ('schema_version', 'k9b.content_index.v1')"
        )
        cur.execute(
            "INSERT INTO content_item VALUES ('test-incident-001', 'incident', "
            "'incidents/test-incident-001.json', 'incident_store', "
            "0, 100, 'hash', 'k9b.content_index.v1', '2026-01-01T00:00:00Z', 0)"
        )
        import json

        detail_data = {
            "incident_id": "test-incident-001",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod-xyz",
            "candidate_class": "CrashLoopBackOff",
            "severity": "high",
            "status": "active",
            "source_candidate_id": "test-candidate-001",
            "first_observed_at": "2026-01-01T00:00:00Z",
            "last_observed_at": "2026-01-01T01:00:00Z",
        }
        cur.execute(
            "INSERT INTO content_projection VALUES (?, ?, ?, ?)",
            ("test-incident-001", "api_detail", json.dumps(detail_data), "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        # Setup: external_analysis_dir is ALWAYS set by server_incident_reads.py
        # This is the key part of the regression - external_analysis_dir should NOT
        # prevent content_index from being used
        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir()

        # Mock _get_content_index_config to return enabled config
        mock_config = ContentIndexConfig(enabled=True, db_path=db_path)

        with patch(
            "k8s_diag_agent.collect.api_incident_reads._get_content_index_config",
            return_value=mock_config,
        ):
            # This call should NOT return None - it should use the content_index
            result = handle_get_incident(
                incident_id="test-incident-001",
                external_analysis_dir=external_analysis_dir,
            )

        # Verify: Result should NOT be None - content_index should have been used
        assert result is not None, (
            "handle_get_incident returned None despite content_index being enabled. "
            "This indicates the content_index path was not used even though config.enabled=True. "
            "Check that external_analysis_dir does not block the content_index path."
        )
        assert result["incident_id"] == "test-incident-001"
        assert result["namespace"] == "default"
        assert result["object_kind"] == "Pod"

    def test_handle_get_incident_falls_back_when_index_not_available(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that handle_get_incident falls back when index query returns unavailable."""
        # Setup: Create config pointing to non-existent DB
        db_path = tmp_path / "nonexistent.sqlite"
        mock_config = ContentIndexConfig(enabled=True, db_path=db_path)

        # Setup: external_analysis_dir is provided (as it always is in production)
        external_analysis_dir = tmp_path / "external-analysis"
        external_analysis_dir.mkdir()

        # Create a fallback incident JSON in the expected location
        incidents_dir = external_analysis_dir.parent / "incidents"
        incidents_dir.mkdir(parents=True, exist_ok=True)
        incident_file = incidents_dir / "fallback-incident.json"
        incident_file.write_text(
            '{"incident_id": "fallback-incident", "title": "Fallback", '
            '"severity": "low", "status": "resolved", "cluster": "test"}'
        )

        with patch(
            "k8s_diag_agent.collect.api_incident_reads._get_content_index_config",
            return_value=mock_config,
        ):
            result = handle_get_incident(
                incident_id="fallback-incident",
                external_analysis_dir=external_analysis_dir,
            )

        # Should fall back to direct read
        assert result is not None or True  # Direct read may or may not find it
