"""Content index freshness checking.

This module provides freshness checking for content items based on
file fingerprints (mtime, size, sha256) and schema version.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    ContentIndexFreshness,
    ContentIndexRecord,
    FreshnessStatus,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Constants
# =============================================================================

# Chunk size for file hashing (64KB)
HASH_CHUNK_SIZE = 65536

# Maximum file size to hash in memory (100MB)
MAX_DIRECT_HASH_SIZE = 100 * 1024 * 1024


# =============================================================================
# Fingerprint Result
# =============================================================================


@dataclass
class FingerprintResult:
    """Result of fingerprinting a file.

    Attributes:
        source_path: Path to the source file.
        mtime_ns: File modification time in nanoseconds.
        size_bytes: File size in bytes.
        sha256: SHA256 hash of file content.
        exists: Whether the file exists.
        error: Error message if fingerprinting failed.
    """

    source_path: Path
    mtime_ns: int | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    exists: bool = True
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        """Return True if fingerprint is valid."""
        return (
            self.exists
            and self.mtime_ns is not None
            and self.size_bytes is not None
            and self.sha256 is not None
        )


# =============================================================================
# Fingerprinting
# =============================================================================


def compute_sha256(file_path: Path) -> tuple[str, int]:
    """Compute SHA256 hash of a file.

    Uses chunked reading to avoid memory issues with large files.

    Args:
        file_path: Path to the file.

    Returns:
        Tuple of (sha256_hex, bytes_read).
    """
    sha256_hash = hashlib.sha256()
    total_bytes = 0

    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            sha256_hash.update(chunk)
            total_bytes += len(chunk)

    return sha256_hash.hexdigest(), total_bytes


def fingerprint_file(file_path: Path, base_path: Path | None = None) -> FingerprintResult:
    """Fingerprint a file.

    Computes mtime, size, and sha256 hash.

    Args:
        file_path: Path to the file to fingerprint.
        base_path: Base path for validation (if path is relative).

    Returns:
        FingerprintResult with file metadata.
    """
    result = FingerprintResult(source_path=file_path)

    try:
        stat = file_path.stat()
        result.mtime_ns = stat.st_mtime_ns
        result.size_bytes = stat.st_size
    except FileNotFoundError:
        result.exists = False
        result.error = "File not found"
        return result
    except PermissionError:
        result.error = "Permission denied"
        return result
    except OSError as e:
        result.error = f"OS error: {e}"
        return result

    # Note: We don't validate source_path here because fingerprint_file
    # operates on any file (absolute or relative). Path validation happens
    # in upsert_content_item when storing records in the database.

    # Compute hash
    try:
        sha256, bytes_read = compute_sha256(file_path)
        result.sha256 = sha256

        # Verify bytes read matches stat size
        if bytes_read != result.size_bytes:
            result.error = f"Size mismatch: stat={result.size_bytes}, read={bytes_read}"

    except PermissionError:
        result.error = "Permission denied for reading"
    except OSError as e:
        result.error = f"Error reading file: {e}"

    return result


def fingerprint_file_from_content(
    content: bytes,
    mtime_ns: int | None = None,
) -> FingerprintResult:
    """Create a fingerprint from file content.

    Useful for testing or when file content is already in memory.

    Args:
        content: File content as bytes.
        mtime_ns: Modification time in nanoseconds (defaults to now).

    Returns:
        FingerprintResult with computed hash.
    """
    sha256_hash = hashlib.sha256(content).hexdigest()

    return FingerprintResult(
        source_path=Path(""),
        mtime_ns=mtime_ns or int(datetime.now(UTC).timestamp() * 1e9),
        size_bytes=len(content),
        sha256=sha256_hash,
        exists=True,
    )


# =============================================================================
# Freshness Checking
# =============================================================================


def check_freshness(
    record: ContentIndexRecord,
    current_fingerprint: FingerprintResult,
) -> ContentIndexFreshness:
    """Check if a content item is fresh.

    Compares the stored fingerprint with the current file fingerprint.

    Args:
        record: The stored content index record.
        current_fingerprint: Current fingerprint of the source file.

    Returns:
        ContentIndexFreshness with status and reason.
    """
    content_id = record.content_id

    # Check if file exists
    if not current_fingerprint.exists:
        return ContentIndexFreshness(
            content_id=content_id,
            status=FreshnessStatus.TOMBSTONE,
            reason="Source file has been deleted",
        )

    # Check if fingerprinting succeeded
    if current_fingerprint.error:
        return ContentIndexFreshness(
            content_id=content_id,
            status=FreshnessStatus.UNKNOWN,
            reason=f"Fingerprinting error: {current_fingerprint.error}",
        )

    # Check mtime
    if current_fingerprint.mtime_ns != record.source_mtime_ns:
        # Mtime changed - need to check content
        if current_fingerprint.sha256 != record.source_sha256:
            return ContentIndexFreshness(
                content_id=content_id,
                status=FreshnessStatus.STALE,
                source_mtime_ns=current_fingerprint.mtime_ns,
                source_size_bytes=current_fingerprint.size_bytes,
                source_sha256=current_fingerprint.sha256,
                reason="File modified (mtime and content changed)",
            )
        else:
            # Mtime changed but content is the same
            return ContentIndexFreshness(
                content_id=content_id,
                status=FreshnessStatus.FRESH,
                source_mtime_ns=current_fingerprint.mtime_ns,
                source_size_bytes=current_fingerprint.size_bytes,
                source_sha256=current_fingerprint.sha256,
                reason="File touched (mtime changed but content unchanged)",
            )

    # Check size
    if current_fingerprint.size_bytes != record.source_size_bytes:
        return ContentIndexFreshness(
            content_id=content_id,
            status=FreshnessStatus.STALE,
            source_mtime_ns=current_fingerprint.mtime_ns,
            source_size_bytes=current_fingerprint.size_bytes,
            source_sha256=current_fingerprint.sha256,
            reason="File size changed",
        )

    # Check content hash
    if current_fingerprint.sha256 != record.source_sha256:
        return ContentIndexFreshness(
            content_id=content_id,
            status=FreshnessStatus.STALE,
            source_mtime_ns=current_fingerprint.mtime_ns,
            source_size_bytes=current_fingerprint.size_bytes,
            source_sha256=current_fingerprint.sha256,
            reason="Content hash changed",
        )

    # All checks pass - fresh
    return ContentIndexFreshness(
        content_id=content_id,
        status=FreshnessStatus.FRESH,
        source_mtime_ns=current_fingerprint.mtime_ns,
        source_size_bytes=current_fingerprint.size_bytes,
        source_sha256=current_fingerprint.sha256,
        reason="All freshness checks passed",
    )


def check_schema_freshness(
    stored_version: str | None,
) -> bool:
    """Check if the schema version is current.

    Args:
        stored_version: The schema version stored in the index.

    Returns:
        True if schema version is current.
    """
    return stored_version == CONTENT_INDEX_SCHEMA_VERSION


# =============================================================================
# Batch Freshness Checking
# =============================================================================


def check_freshness_for_paths(
    records: list[ContentIndexRecord],
    base_path: Path,
) -> dict[str, ContentIndexFreshness]:
    """Check freshness for multiple content items.

    Args:
        records: List of content index records.
        base_path: Base path to resolve relative paths.

    Returns:
        Dictionary mapping content_id to freshness result.
    """
    results: dict[str, ContentIndexFreshness] = {}

    for record in records:
        # Construct absolute path
        file_path = base_path / record.source_path

        # Get fingerprint
        fingerprint = fingerprint_file(file_path, base_path)

        # Check freshness
        freshness = check_freshness(record, fingerprint)
        results[record.content_id] = freshness

    return results


# =============================================================================
# Summary Statistics
# =============================================================================


def summarize_freshness(
    freshness_results: dict[str, ContentIndexFreshness],
) -> dict[str, Any]:
    """Summarize freshness check results.

    Args:
        freshness_results: Dictionary of freshness results.

    Returns:
        Summary dictionary with counts.
    """
    summary: dict[str, Any] = {
        "total": len(freshness_results),
        "fresh": 0,
        "stale": 0,
        "tombstone": 0,
        "unknown": 0,
        "needs_rebuild": 0,
    }

    for result in freshness_results.values():
        status = result.status.value
        if status in summary:
            summary[status] += 1

        if result.needs_rebuild:
            summary["needs_rebuild"] += 1

    return summary


__all__ = [
    "HASH_CHUNK_SIZE",
    "MAX_DIRECT_HASH_SIZE",
    "FingerprintResult",
    "compute_sha256",
    "fingerprint_file",
    "fingerprint_file_from_content",
    "check_freshness",
    "check_schema_freshness",
    "check_freshness_for_paths",
    "summarize_freshness",
]
