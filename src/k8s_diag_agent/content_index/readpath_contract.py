"""Content index read path contracts.

This module defines the contracts for the disabled-by-default content index
read path for k9b UI APIs.

Schema Version: k9b.content_index.v1

Ownership:
    - FallbackReason: Bounded reason codes for OTel span attributes
    - IndexOpenResult: Result of opening the content index database
    - IndexValidationResult: Result of validating the content index schema
    - IndexReadResult: Result of an index read operation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# =============================================================================
# Fallback Reason Codes
# =============================================================================


class FallbackReason:
    """Bounded fallback reason codes for OTel span attributes.

    These are safe, low-cardinality values that indicate why the index
    read path fell back to the direct read path.

    Expected mapping:
        disabled config -> index_not_enabled
        FileNotFoundError -> index_not_found
        sqlite3.DatabaseError during open -> index_corrupt
        generic open exception -> index_open_error
        schema version mismatch -> index_schema_mismatch
        validate_database invalid -> index_validation_failed
        query/projection exception -> projection_error
    """

    # Index not enabled
    INDEX_NOT_ENABLED = "index_not_enabled"
    # Generic not available (fallback)
    INDEX_NOT_AVAILABLE = "index_not_available"
    # Index file not found
    INDEX_NOT_FOUND = "index_not_found"
    # Index file is corrupt or invalid
    INDEX_CORRUPT = "index_corrupt"
    # Schema version mismatch
    INDEX_SCHEMA_MISMATCH = "index_schema_mismatch"
    # Index validation failed
    INDEX_VALIDATION_FAILED = "index_validation_failed"
    # Generic open error
    INDEX_OPEN_ERROR = "index_open_error"
    # Query or projection error
    PROJECTION_ERROR = "projection_error"

    @classmethod
    def from_open_error(cls, exc: Exception) -> str:
        """Map an open exception to the appropriate fallback reason.

        Args:
            exc: The exception that occurred during open.

        Returns:
            The appropriate fallback reason code.
        """
        # Import here to avoid circular imports

        # File not found
        if isinstance(exc, FileNotFoundError):
            return cls.INDEX_NOT_FOUND

        # Database error (corrupt/invalid)
        import sqlite3

        if isinstance(exc, sqlite3.DatabaseError):
            return cls.INDEX_CORRUPT

        # Generic open error
        return cls.INDEX_OPEN_ERROR

    @classmethod
    def from_validation_failure(cls, reason: str | None) -> str:
        """Map a validation failure reason to the appropriate fallback reason.

        Args:
            reason: The validation failure reason, or None for unknown.

        Returns:
            The appropriate fallback reason code.
        """
        if reason == "schema_mismatch":
            return cls.INDEX_SCHEMA_MISMATCH
        if reason == "validation_failed":
            return cls.INDEX_VALIDATION_FAILED
        return cls.INDEX_VALIDATION_FAILED


# =============================================================================
# Index Open Result
# =============================================================================


@dataclass(frozen=True)
class IndexOpenResult:
    """Result of opening the content index database.

    Attributes:
        ok: Whether the index was opened successfully.
        reason: Bounded fallback reason code if open failed, or None.
    """

    ok: bool
    reason: str | None

    @classmethod
    def success(cls) -> IndexOpenResult:
        """Create a successful open result."""
        return cls(ok=True, reason=None)

    @classmethod
    def not_found(cls) -> IndexOpenResult:
        """Create a not-found result."""
        return cls(ok=False, reason=FallbackReason.INDEX_NOT_FOUND)

    @classmethod
    def corrupt(cls) -> IndexOpenResult:
        """Create a corrupt database result."""
        return cls(ok=False, reason=FallbackReason.INDEX_CORRUPT)

    @classmethod
    def error(cls) -> IndexOpenResult:
        """Create a generic open error result."""
        return cls(ok=False, reason=FallbackReason.INDEX_OPEN_ERROR)


# =============================================================================
# Index Validation Result
# =============================================================================


@dataclass(frozen=True)
class IndexValidationResult:
    """Result of validating the content index database.

    Attributes:
        ok: Whether the index is valid.
        reason: Bounded fallback reason code if validation failed, or None.
        schema_version: Schema version from the index if available.
    """

    ok: bool
    reason: str | None
    schema_version: str | None = None

    @classmethod
    def success(cls, schema_version: str) -> IndexValidationResult:
        """Create a successful validation result."""
        return cls(ok=True, reason=None, schema_version=schema_version)

    @classmethod
    def schema_mismatch(cls) -> IndexValidationResult:
        """Create a schema mismatch result."""
        return cls(
            ok=False,
            reason=FallbackReason.INDEX_SCHEMA_MISMATCH,
            schema_version=None,
        )

    @classmethod
    def validation_failed(cls) -> IndexValidationResult:
        """Create a validation failed result."""
        return cls(
            ok=False,
            reason=FallbackReason.INDEX_VALIDATION_FAILED,
            schema_version=None,
        )


# =============================================================================
# Index Read Result
# =============================================================================


@dataclass(frozen=True)
class IndexReadResult:
    """Result of an index read operation.

    Attributes:
        data: The projected data from the index, or None if index unavailable.
        fallback_reason: Bounded reason code for why fallback occurred, or None.
        schema_version: Schema version from the index, or None.
        count: Number of items returned from the index.
        index_available: Whether the index was available and valid.
    """

    data: dict[str, Any] | None
    fallback_reason: str | None
    schema_version: str | None
    count: int
    index_available: bool

    @classmethod
    def fallback(
        cls,
        reason: str,
        count: int = 0,
    ) -> IndexReadResult:
        """Create a fallback result when index is unavailable."""
        return cls(
            data=None,
            fallback_reason=reason,
            schema_version=None,
            count=count,
            index_available=False,
        )

    @classmethod
    def from_index(
        cls,
        data: dict[str, Any],
        schema_version: str,
        count: int,
    ) -> IndexReadResult:
        """Create a successful index result."""
        return cls(
            data=data,
            fallback_reason=None,
            schema_version=schema_version,
            count=count,
            index_available=True,
        )

    @classmethod
    def not_found(
        cls,
        schema_version: str | None,
    ) -> IndexReadResult:
        """Create a not-found result when incident doesn't exist in valid index.

        This is not a fallback - the index is valid, but the item doesn't exist.
        """
        return cls(
            data=None,
            fallback_reason=None,
            schema_version=schema_version,
            count=0,
            index_available=True,
        )
