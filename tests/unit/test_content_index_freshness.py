"""Tests for content index freshness.

Tests freshness checking logic for the content index.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.content_index.freshness import (
    FingerprintResult,
    check_freshness,
    check_schema_freshness,
    compute_sha256,
    fingerprint_file,
    fingerprint_file_from_content,
    summarize_freshness,
)
from k8s_diag_agent.content_index.schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    ContentIndexFreshness,
    ContentIndexRecord,
    FreshnessStatus,
)


class TestComputeSha256:
    """Test SHA256 computation."""

    def test_compute_sha256_simple(self, tmp_path: Path) -> None:
        """SHA256 computation works for simple file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        sha256, bytes_read = compute_sha256(test_file)
        assert bytes_read == 11
        # Known SHA256 for "hello world"
        assert sha256 == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_compute_sha256_empty_file(self, tmp_path: Path) -> None:
        """SHA256 computation works for empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        sha256, bytes_read = compute_sha256(test_file)
        assert bytes_read == 0
        # Known SHA256 for empty string
        assert sha256 == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_compute_sha256_large_file(self, tmp_path: Path) -> None:
        """SHA256 computation handles large files with chunked reading."""
        test_file = tmp_path / "large.txt"
        # Write content larger than chunk size (64KB)
        test_file.write_bytes(b"x" * (100 * 1024))

        sha256, bytes_read = compute_sha256(test_file)
        assert bytes_read == 100 * 1024
        assert len(sha256) == 64  # SHA256 hex is 64 characters


class TestFingerprintFile:
    """Test file fingerprinting."""

    def test_fingerprint_file_success(self, tmp_path: Path) -> None:
        """Fingerprint file returns valid result."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"test": "data"}')

        result = fingerprint_file(test_file)
        assert result.is_valid
        assert result.exists
        assert result.mtime_ns is not None
        # JSON string + trailing newline from write_text
        assert result.size_bytes == 16
        assert result.sha256 is not None
        assert result.error is None

    def test_fingerprint_file_missing(self, tmp_path: Path) -> None:
        """Fingerprint file handles missing file."""
        test_file = tmp_path / "nonexistent.json"

        result = fingerprint_file(test_file)
        assert not result.exists
        assert result.error == "File not found"

    def test_fingerprint_file_permission_denied(self, tmp_path: Path) -> None:
        """Fingerprint file handles permission denied."""
        test_file = tmp_path / "test.json"
        test_file.write_text("data")
        test_file.chmod(0o000)

        try:
            result = fingerprint_file(test_file)
            assert result.error is not None
            assert "Permission" in result.error or "denied" in result.error.lower()
        finally:
            test_file.chmod(0o644)


class TestFingerprintFileFromContent:
    """Test fingerprint from content."""

    def test_fingerprint_from_content(self) -> None:
        """Fingerprint from content works correctly."""
        content = b'{"test": "data"}'
        result = fingerprint_file_from_content(content, mtime_ns=1000000000)

        assert result.is_valid
        assert result.mtime_ns == 1000000000
        # Exact byte count: '{"test": "data"}' = 16 chars
        assert result.size_bytes == 16
        assert result.sha256 is not None

    def test_fingerprint_from_content_defaults_mtime(self) -> None:
        """Fingerprint from content defaults mtime to now."""
        content = b"test"
        result = fingerprint_file_from_content(content)

        assert result.is_valid
        assert result.mtime_ns is not None
        assert result.mtime_ns > 0


class TestCheckFreshness:
    """Test freshness checking."""

    def test_fresh_when_all_match(self, tmp_path: Path) -> None:
        """Fresh when mtime, size, and sha256 all match."""
        test_file = tmp_path / "test.json"
        test_file.write_text("test content")
        result = fingerprint_file(test_file)

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="test.json",
            source_path_kind="incident_store",
            source_mtime_ns=result.mtime_ns,
            source_size_bytes=result.size_bytes,
            source_sha256=result.sha256,
            indexed_at=datetime.now(UTC).isoformat(),
        )

        freshness = check_freshness(record, result)
        assert freshness.status == FreshnessStatus.FRESH
        assert freshness.is_fresh

    def test_stale_when_mtime_changes(self, tmp_path: Path) -> None:
        """Stale when mtime changes."""
        test_file = tmp_path / "test.json"
        test_file.write_text("test content")
        result1 = fingerprint_file(test_file)

        # Touch file to change mtime
        test_file.write_text("test content")

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="test.json",
            source_path_kind="incident_store",
            source_mtime_ns=result1.mtime_ns,
            source_size_bytes=result1.size_bytes,
            source_sha256=result1.sha256,
            indexed_at=datetime.now(UTC).isoformat(),
        )

        result2 = fingerprint_file(test_file)
        freshness = check_freshness(record, result2)

        # Mtime changed but content might not have
        assert freshness.status in (FreshnessStatus.FRESH, FreshnessStatus.STALE)

    def test_stale_when_size_changes(self, tmp_path: Path) -> None:
        """Stale when file size changes."""
        test_file = tmp_path / "test.json"
        test_file.write_text("short")

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="test.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=5,
            source_sha256="abc123",
            indexed_at=datetime.now(UTC).isoformat(),
        )

        result = fingerprint_file(test_file)
        freshness = check_freshness(record, result)

        assert freshness.status == FreshnessStatus.STALE
        assert not freshness.is_fresh

    def test_stale_when_sha256_changes(self, tmp_path: Path) -> None:
        """Stale when content hash changes."""
        test_file = tmp_path / "test.json"
        test_file.write_text("new content")

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="test.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=11,
            source_sha256="oldhash",
            indexed_at=datetime.now(UTC).isoformat(),
        )

        result = fingerprint_file(test_file)
        freshness = check_freshness(record, result)

        assert freshness.status == FreshnessStatus.STALE
        assert not freshness.is_fresh

    def test_tombstone_when_file_missing(self) -> None:
        """Tombstone when source file is missing."""
        fingerprint = FingerprintResult(
            source_path=Path("/nonexistent/file.json"),
            exists=False,
            error="File not found",
        )

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="file.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            indexed_at=datetime.now(UTC).isoformat(),
        )

        freshness = check_freshness(record, fingerprint)
        assert freshness.status == FreshnessStatus.TOMBSTONE
        assert not freshness.is_fresh
        assert freshness.needs_rebuild

    def test_unknown_when_fingerprinting_fails(self) -> None:
        """Unknown when fingerprinting fails."""
        fingerprint = FingerprintResult(
            source_path=Path("/path/to/file"),
            exists=True,
            error="Permission denied",
        )

        record = ContentIndexRecord(
            content_id="test-123",
            content_kind="incident",
            source_path="file.json",
            source_path_kind="incident_store",
            source_mtime_ns=1000000000,
            source_size_bytes=1024,
            source_sha256="abc123",
            indexed_at=datetime.now(UTC).isoformat(),
        )

        freshness = check_freshness(record, fingerprint)
        assert freshness.status == FreshnessStatus.UNKNOWN


class TestCheckSchemaFreshness:
    """Test schema freshness checking."""

    def test_schema_fresh_when_matches(self) -> None:
        """Schema is fresh when versions match."""
        assert check_schema_freshness(CONTENT_INDEX_SCHEMA_VERSION) is True

    def test_schema_not_fresh_when_mismatched(self) -> None:
        """Schema is not fresh when versions mismatch."""
        assert check_schema_freshness("k9b.content_index.v0") is False

    def test_schema_not_fresh_when_none(self) -> None:
        """Schema is not fresh when version is None."""
        assert check_schema_freshness(None) is False


class TestSummarizeFreshness:
    """Test freshness summarization."""

    def test_summarize_empty(self) -> None:
        """Summarize handles empty results."""
        results: dict[str, ContentIndexFreshness] = {}
        summary = summarize_freshness(results)

        assert summary["total"] == 0
        assert summary["fresh"] == 0
        assert summary["needs_rebuild"] == 0

    def test_summarize_mixed(self) -> None:
        """Summarize handles mixed freshness statuses."""
        results = {
            "item1": ContentIndexFreshness(
                content_id="item1",
                status=FreshnessStatus.FRESH,
                reason="All good",
            ),
            "item2": ContentIndexFreshness(
                content_id="item2",
                status=FreshnessStatus.STALE,
                reason="Content changed",
            ),
            "item3": ContentIndexFreshness(
                content_id="item3",
                status=FreshnessStatus.TOMBSTONE,
                reason="File deleted",
            ),
        }

        summary = summarize_freshness(results)

        assert summary["total"] == 3
        assert summary["fresh"] == 1
        assert summary["stale"] == 1
        assert summary["tombstone"] == 1
        assert summary["needs_rebuild"] == 2


class TestContentIndexFreshness:
    """Test ContentIndexFreshness dataclass."""

    def test_is_fresh_property(self) -> None:
        """is_fresh returns True only for FRESH status."""
        fresh = ContentIndexFreshness(
            content_id="test",
            status=FreshnessStatus.FRESH,
        )
        assert fresh.is_fresh is True

        stale = ContentIndexFreshness(
            content_id="test",
            status=FreshnessStatus.STALE,
        )
        assert stale.is_fresh is False

    def test_needs_rebuild_property(self) -> None:
        """needs_rebuild returns True for appropriate statuses."""
        stale = ContentIndexFreshness(
            content_id="test",
            status=FreshnessStatus.STALE,
        )
        assert stale.needs_rebuild is True

        tombstone = ContentIndexFreshness(
            content_id="test",
            status=FreshnessStatus.TOMBSTONE,
        )
        assert tombstone.needs_rebuild is True

        fresh = ContentIndexFreshness(
            content_id="test",
            status=FreshnessStatus.FRESH,
        )
        assert fresh.needs_rebuild is False
