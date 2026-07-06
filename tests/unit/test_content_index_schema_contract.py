"""Tests for content index schema contract.

This module tests the schema definitions and contracts for the k9b on-disk
content index.

Coverage:
1. Schema version constant exists
2. Required content kinds are present
3. SQL contains required tables
4. SQL contains required freshness columns
5. Forbidden field names are not present in SQL/projection contract
6. Schema metadata table exists
7. Tombstone/deleted marker exists
8. Feature flag default is documented as disabled
9. Unknown content kind is rejected by helper
10. Source path kind is required
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from k8s_diag_agent.content_index.schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    FORBIDDEN_FIELD_PATTERNS,
    INDEXED_CONTENT_KINDS,
    INDEXED_PATH_KINDS,
    REQUIRED_COLUMNS,
    REQUIRED_TABLES,
    ContentIndexFreshness,
    ContentIndexRecord,
    ContentIndexValidationResult,
    ContentProjectionRecord,
    FreshnessStatus,
    check_forbidden_fields,
    get_content_kind_validator,
    validate_content_kind,
    validate_source_path,
)


class TestSchemaVersion:
    """Test schema version constant."""

    def test_schema_version_constant_exists(self) -> None:
        """Schema version constant must exist."""
        assert CONTENT_INDEX_SCHEMA_VERSION == "k9b.content_index.v1"

    def test_schema_version_format(self) -> None:
        """Schema version must follow expected format."""
        assert CONTENT_INDEX_SCHEMA_VERSION.startswith("k9b.")
        assert ".v" in CONTENT_INDEX_SCHEMA_VERSION


class TestIndexedContentKinds:
    """Test indexed content kinds."""

    def test_required_content_kinds_present(self) -> None:
        """All required content kinds must be present."""
        required_kinds = {
            "incident",
            "evidence_link",
            "snapshot_bundle",
            "review_packet",
            "automatic_diagnosis_review",
            "diagnosis_loop_run",
            "diagnosis_loop_pass",
            "lab_result",
            "trace_capture_summary",
            "perf_baseline_summary",
        }
        assert required_kinds.issubset(INDEXED_CONTENT_KINDS)

    def test_content_kinds_is_frozenset(self) -> None:
        """Content kinds must be immutable (frozenset)."""
        assert isinstance(INDEXED_CONTENT_KINDS, frozenset)

    def test_content_kinds_count(self) -> None:
        """Must have exactly 10 content kinds."""
        assert len(INDEXED_CONTENT_KINDS) == 10


class TestIndexedPathKinds:
    """Test indexed path kinds."""

    def test_required_path_kinds_present(self) -> None:
        """All required path kinds must be present."""
        required_kinds = {
            "incident_store",
            "artifact",
            "lab",
            "trace_capture",
            "perf_baseline",
        }
        assert required_kinds.issubset(INDEXED_PATH_KINDS)

    def test_path_kinds_is_frozenset(self) -> None:
        """Path kinds must be immutable (frozenset)."""
        assert isinstance(INDEXED_PATH_KINDS, frozenset)


class TestSqlSchema:
    """Test SQL schema structure."""

    def test_required_tables_in_sql(self) -> None:
        """SQL schema must contain required tables."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        assert schema_path.exists(), f"Schema file not found at {schema_path}"

        schema_content = schema_path.read_text()

        for table in REQUIRED_TABLES:
            assert "CREATE TABLE" in schema_content
            # Check table name appears (case-insensitive)
            assert table.lower() in schema_content.lower(), f"Table {table} not found in schema"

    def test_required_columns_in_sql(self) -> None:
        """SQL schema must contain required columns."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text().lower()

        for table, columns in REQUIRED_COLUMNS.items():
            for column in columns:
                assert column.lower() in schema_content, f"Column {column} not found in schema"

    def test_freshness_columns_present(self) -> None:
        """SQL must have freshness tracking columns."""
        freshness_columns = {"source_mtime_ns", "source_size_bytes", "source_sha256"}
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text()

        for col in freshness_columns:
            assert col in schema_content, f"Freshness column {col} not found"

    def test_tombstone_deleted_marker_exists(self) -> None:
        """SQL must have deleted/tombstone marker."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text().lower()

        assert "deleted" in schema_content, "Deleted marker column not found"
        assert "tombstone" in schema_content.lower() or "deleted" in schema_content.lower()

    def test_sql_executes_without_error(self) -> None:
        """SQL schema must execute without error in SQLite."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text()

        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(schema_content)
            conn.commit()
        finally:
            conn.close()

    def test_sql_creates_required_tables(self) -> None:
        """SQL must actually create the required tables."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text()

        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(schema_content)
            conn.commit()

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

            for table in REQUIRED_TABLES:
                assert table in tables, f"Table {table} not created"
        finally:
            conn.close()


class TestForbiddenFields:
    """Test forbidden field patterns."""

    def test_forbidden_patterns_defined(self) -> None:
        """Forbidden patterns must be defined."""
        assert len(FORBIDDEN_FIELD_PATTERNS) > 0
        assert "secret" in FORBIDDEN_FIELD_PATTERNS
        assert "token" in FORBIDDEN_FIELD_PATTERNS
        assert "password" in FORBIDDEN_FIELD_PATTERNS

    def test_forbidden_fields_not_in_sql(self) -> None:
        """Forbidden field names should not appear as column names in SQL."""
        schema_path = Path(__file__).parent.parent.parent / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
        schema_content = schema_path.read_text().lower()

        # Check that forbidden patterns don't appear as column definitions
        # (they can appear in comments or CHECK constraints)
        lines = schema_content.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("--") or stripped.startswith("/*"):
                continue  # Skip comments
            for pattern in FORBIDDEN_FIELD_PATTERNS:
                # Column definitions typically have format: column_name TYPE
                if f" {pattern} " in f" {line} " or f",{pattern} " in f",{line}":
                    # Allow in constraints like CHECK (content_kind IN (...))
                    if "check" not in stripped.lower():
                        pytest.fail(f"Forbidden pattern {pattern!r} found in non-constraint SQL: {line!r}")

    def test_check_forbidden_fields_helper(self) -> None:
        """check_forbidden_fields helper must detect forbidden fields."""
        data = {
            "api_secret": "secret-value",
            "normal_field": "safe",
            "bearer_token": "token-value",
        }
        found = check_forbidden_fields(data)
        assert "api_secret" in found
        assert "bearer_token" in found
        assert "normal_field" not in found


class TestContentIndexRecord:
    """Test ContentIndexRecord dataclass."""

    def test_valid_record_creation(self) -> None:
        """Valid record must be created successfully."""
        record = ContentIndexRecord(
            content_id="incident-123",
            content_kind="incident",
            source_path="incidents/123.json",
            source_path_kind="incident_store",
            source_mtime_ns=1234567890000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            schema_version="v1",
            indexed_at="2026-06-07T00:00:00Z",
            deleted=False,
        )
        assert record.content_id == "incident-123"
        assert record.content_kind == "incident"
        assert record.deleted is False

    def test_invalid_content_kind_rejected(self) -> None:
        """Invalid content kind must be rejected."""
        with pytest.raises(ValueError, match="Invalid content_kind"):
            ContentIndexRecord(
                content_id="test-123",
                content_kind="invalid_kind",
                source_path="test.json",
                source_path_kind="incident_store",
                source_mtime_ns=0,
                source_size_bytes=0,
                source_sha256="abc",
            )

    def test_invalid_path_kind_rejected(self) -> None:
        """Invalid path kind must be rejected."""
        with pytest.raises(ValueError, match="Invalid source_path_kind"):
            ContentIndexRecord(
                content_id="test-123",
                content_kind="incident",
                source_path="test.json",
                source_path_kind="invalid_path_kind",
                source_mtime_ns=0,
                source_size_bytes=0,
                source_sha256="abc",
            )

    def test_absolute_path_rejected(self) -> None:
        """Absolute paths must be rejected."""
        with pytest.raises(ValueError, match="must be relative, not absolute"):
            ContentIndexRecord(
                content_id="test-123",
                content_kind="incident",
                source_path="/absolute/path.json",
                source_path_kind="incident_store",
                source_mtime_ns=0,
                source_size_bytes=0,
                source_sha256="abc",
            )

    def test_home_directory_path_rejected(self) -> None:
        """Home directory paths must be rejected."""
        with pytest.raises(ValueError, match="must be relative, not absolute"):
            ContentIndexRecord(
                content_id="test-123",
                content_kind="incident",
                source_path="~/path.json",
                source_path_kind="incident_store",
                source_mtime_ns=0,
                source_size_bytes=0,
                source_sha256="abc",
            )


class TestContentProjectionRecord:
    """Test ContentProjectionRecord dataclass."""

    def test_valid_projection_creation(self) -> None:
        """Valid projection must be created successfully."""
        record = ContentProjectionRecord(
            content_id="incident-123",
            projection_kind="api_summary",
            projection_json=json.dumps({"id": "123", "status": "open"}),
            updated_at="2026-06-07T00:00:00Z",
        )
        assert record.content_id == "incident-123"
        assert record.projection_kind == "api_summary"

    def test_invalid_json_rejected(self) -> None:
        """Invalid JSON must be rejected."""
        with pytest.raises(ValueError, match="projection_json must be valid JSON"):
            ContentProjectionRecord(
                content_id="incident-123",
                projection_kind="api_summary",
                projection_json="not valid json {",
                updated_at="2026-06-07T00:00:00Z",
            )


class TestContentIndexFreshness:
    """Test ContentIndexFreshness dataclass."""

    def test_fresh_status(self) -> None:
        """Fresh status must be detected correctly."""
        freshness = ContentIndexFreshness(
            content_id="test-123",
            status=FreshnessStatus.FRESH,
            reason="All checks passed",
        )
        assert freshness.is_fresh is True
        assert freshness.needs_rebuild is False

    def test_stale_status(self) -> None:
        """Stale status must be detected correctly."""
        freshness = ContentIndexFreshness(
            content_id="test-123",
            status=FreshnessStatus.STALE,
            reason="Content changed",
        )
        assert freshness.is_fresh is False
        assert freshness.needs_rebuild is True

    def test_tombstone_status(self) -> None:
        """Tombstone status must be detected correctly."""
        freshness = ContentIndexFreshness(
            content_id="test-123",
            status=FreshnessStatus.TOMBSTONE,
            reason="Source file deleted",
        )
        assert freshness.is_fresh is False
        assert freshness.needs_rebuild is True


class TestContentIndexValidationResult:
    """Test ContentIndexValidationResult dataclass."""

    def test_valid_result(self) -> None:
        """Valid result must be created successfully."""
        result = ContentIndexValidationResult(
            is_valid=True,
            schema_version=CONTENT_INDEX_SCHEMA_VERSION,
            required_tables_present=frozenset(REQUIRED_TABLES),
        )
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_result(self) -> None:
        """Invalid result must track errors."""
        result = ContentIndexValidationResult(is_valid=True)
        result.add_error("Table missing")
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "Table missing" in result.errors


class TestValidationHelpers:
    """Test validation helper functions."""

    def test_validate_content_kind_valid(self) -> None:
        """Valid content kind must return True."""
        assert validate_content_kind("incident") is True
        assert validate_content_kind("review_packet") is True

    def test_validate_content_kind_invalid(self) -> None:
        """Invalid content kind must return False."""
        assert validate_content_kind("invalid") is False
        assert validate_content_kind("") is False

    def test_get_content_kind_validator(self) -> None:
        """Validator function must work correctly."""
        validator = get_content_kind_validator()
        assert validator("incident") is True
        assert validator("invalid") is False

    def test_validate_source_path_valid(self) -> None:
        """Valid source paths must pass validation."""
        validate_source_path("incidents/123.json")
        validate_source_path("artifacts/test.json")
        validate_source_path("data/file.json")

    def test_validate_source_path_absolute_rejected(self) -> None:
        """Absolute paths must be rejected."""
        with pytest.raises(ValueError, match="Absolute paths are forbidden"):
            validate_source_path("/absolute/path.json")

    def test_validate_source_path_home_rejected(self) -> None:
        """Home directory paths must be rejected."""
        with pytest.raises(ValueError, match="Home directory references are forbidden"):
            validate_source_path("~/path.json")

    def test_validate_source_path_parent_rejected(self) -> None:
        """Parent directory references must be rejected."""
        with pytest.raises(ValueError, match="Parent directory references are forbidden"):
            validate_source_path("../parent.json")


class TestFeatureFlag:
    """Test feature flag defaults."""

    def test_feature_flag_documented(self) -> None:
        """Feature flag must be documented as disabled by default."""
        # Import the flag value
        from k8s_diag_agent.content_index.schema import K9B_CONTENT_INDEX_ENABLED

        # Default should be False (disabled)
        assert K9B_CONTENT_INDEX_ENABLED is False
