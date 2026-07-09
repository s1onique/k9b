"""Content index schema definitions and contracts.

This module defines the schema, constants, and dataclasses for the k9b
on-disk content index. The index accelerates UI/backend read paths by
precomputing projections from source artifacts.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# =============================================================================
# Schema Version
# =============================================================================

CONTENT_INDEX_SCHEMA_VERSION = "k9b.content_index.v1"


# =============================================================================
# Indexed Content Kinds
# =============================================================================

INDEXED_CONTENT_KINDS = frozenset({
    "incident",
    "evidence_link",
    "snapshot_bundle",
    "review_packet",
    "automatic_diagnosis_review",
    "automatic_diagnosis_hypothesis_burst",
    "automatic_diagnosis_pass",
    "automatic_diagnosis_final_hypotheses",
    "automatic_diagnosis_summary",
    "diagnosis_loop_run",
    "diagnosis_loop_pass",
    "lab_result",
    "trace_capture_summary",
    "perf_baseline_summary",
})


# =============================================================================
# Source Path Kinds
# =============================================================================

INDEXED_PATH_KINDS = frozenset({
    "incident_store",
    "artifact",
    "lab",
    "trace_capture",
    "perf_baseline",
})


# =============================================================================
# Feature Flags
# =============================================================================

# Default is disabled - reserved for ACT-K9B-CONTENT-INDEXER01
K9B_CONTENT_INDEX_ENABLED = False


# =============================================================================
# Freshness Status
# =============================================================================

class FreshnessStatus(StrEnum):
    """Status of content index freshness."""

    FRESH = "fresh"
    STALE = "stale"
    TOMBSTONE = "tombstone"
    UNKNOWN = "unknown"
    REBUILD_REQUIRED = "rebuild_required"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class ContentIndexRecord:
    """Represents a content item in the index.

    Attributes:
        content_id: Unique identifier for the content item.
        content_kind: Type of content (e.g., 'incident', 'review_packet').
        source_path: Source file path (relative, never absolute).
        source_path_kind: Category of the source path.
        source_mtime_ns: Source file modification time in nanoseconds.
        source_size_bytes: Source file size in bytes.
        source_sha256: SHA256 hash of source file content.
        schema_version: Schema version of the source content.
        indexed_at: ISO timestamp when indexed.
        deleted: Whether the source has been deleted (tombstone).
    """

    content_id: str
    content_kind: str
    source_path: str
    source_path_kind: str
    source_mtime_ns: int
    source_size_bytes: int
    source_sha256: str
    schema_version: str | None = None
    indexed_at: str = ""
    deleted: bool = False

    def __post_init__(self) -> None:
        """Validate content kind and path kind after initialization."""
        if self.content_kind not in INDEXED_CONTENT_KINDS:
            raise ValueError(
                f"Invalid content_kind: {self.content_kind!r}. "
                f"Must be one of: {sorted(INDEXED_CONTENT_KINDS)}"
            )
        if self.source_path_kind not in INDEXED_PATH_KINDS:
            raise ValueError(
                f"Invalid source_path_kind: {self.source_path_kind!r}. "
                f"Must be one of: {sorted(INDEXED_PATH_KINDS)}"
            )
        # Never allow absolute paths
        if self.source_path.startswith("/") or self.source_path.startswith("~"):
            raise ValueError(
                f"source_path must be relative, not absolute: {self.source_path!r}"
            )


@dataclass(frozen=True)
class ContentProjectionRecord:
    """Represents a precomputed projection for a content item.

    Attributes:
        content_id: ID of the parent content item.
        projection_kind: Type of projection (e.g., 'api_summary', 'api_detail').
        projection_json: JSON string of the projection data.
        updated_at: ISO timestamp when projection was updated.
    """

    content_id: str
    projection_kind: str
    projection_json: str
    updated_at: str

    def __post_init__(self) -> None:
        """Validate projection JSON after initialization."""
        import json

        try:
            json.loads(self.projection_json)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"projection_json must be valid JSON: {e}"
            ) from e


@dataclass
class ContentIndexFreshness:
    """Result of a freshness check for a content item.

    Attributes:
        content_id: ID of the content item.
        status: Freshness status.
        source_mtime_ns: Current source mtime (if checked).
        source_size_bytes: Current source size (if checked).
        source_sha256: Current source hash (if checked).
        reason: Human-readable reason for the status.
    """

    content_id: str
    status: FreshnessStatus
    source_mtime_ns: int | None = None
    source_size_bytes: int | None = None
    source_sha256: str | None = None
    reason: str = ""

    @property
    def is_fresh(self) -> bool:
        """Return True if content is fresh."""
        return self.status == FreshnessStatus.FRESH

    @property
    def needs_rebuild(self) -> bool:
        """Return True if content needs rebuilding."""
        return self.status in (
            FreshnessStatus.STALE,
            FreshnessStatus.TOMBSTONE,
            FreshnessStatus.REBUILD_REQUIRED,
        )


@dataclass
class ContentIndexValidationResult:
    """Result of validating the content index schema.

    Attributes:
        is_valid: Whether the schema is valid.
        schema_version: Schema version found in index.
        required_tables_present: Set of required tables that exist.
        required_columns_present: Dict mapping table to required columns present.
        missing_tables: Set of required tables that are missing.
        missing_columns: Dict mapping table to required columns that are missing.
        errors: List of validation errors.
    """

    is_valid: bool = True
    schema_version: str | None = None
    required_tables_present: frozenset[str] = field(default_factory=frozenset)
    required_columns_present: dict[str, frozenset[str]] = field(default_factory=dict)
    missing_tables: frozenset[str] = field(default_factory=frozenset)
    missing_columns: dict[str, frozenset[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Add a validation error and mark as invalid."""
        self.errors.append(message)
        self.is_valid = False


# =============================================================================
# Required Tables and Columns
# =============================================================================

REQUIRED_TABLES = frozenset({
    "content_index_metadata",
    "content_item",
    "content_projection",
})

REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "content_index_metadata": frozenset({"key", "value"}),
    "content_item": frozenset({
        "content_id",
        "content_kind",
        "source_path",
        "source_path_kind",
        "source_mtime_ns",
        "source_size_bytes",
        "source_sha256",
        "schema_version",
        "indexed_at",
        "deleted",
    }),
    "content_projection": frozenset({
        "content_id",
        "projection_kind",
        "projection_json",
        "updated_at",
    }),
}


# =============================================================================
# Forbidden Field Names
# =============================================================================

# These field names MUST NOT appear in projections or schema columns.
# They represent sensitive data that should never be indexed.
FORBIDDEN_FIELD_PATTERNS = frozenset({
    "secret",
    "token",
    "bearer",
    "cookie",
    "auth_header",
    "authorization",
    "kubeconfig",
    "password",
    "credential",
    "private_key",
    "access_key",
})


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_content_kind(kind: str) -> bool:
    """Validate that a content kind is in the indexed set.

    Args:
        kind: Content kind to validate.

    Returns:
        True if valid, False otherwise.
    """
    return kind in INDEXED_CONTENT_KINDS


def get_content_kind_validator() -> Callable[[str], bool]:
    """Get a validator function for content kinds.

    Returns:
        A callable that returns True if the content kind is valid.
    """
    return validate_content_kind


def check_forbidden_fields(data: dict[str, Any]) -> list[str]:
    """Check a dict for forbidden field names.

    Args:
        data: Dictionary to check.

    Returns:
        List of forbidden field names found.
    """
    found: list[str] = []
    for key in data.keys():
        key_lower = key.lower()
        for pattern in FORBIDDEN_FIELD_PATTERNS:
            if pattern in key_lower:
                found.append(key)
                break
    return found


def validate_source_path(path: str) -> None:
    """Validate that a source path is safe.

    Args:
        path: Path to validate.

    Raises:
        ValueError: If path is absolute or contains home directory reference.
    """
    if path.startswith("/"):
        raise ValueError(f"Absolute paths are forbidden: {path!r}")
    if path.startswith("~"):
        raise ValueError(f"Home directory references are forbidden: {path!r}")
    if ".." in path:
        raise ValueError(f"Parent directory references are forbidden: {path!r}")
