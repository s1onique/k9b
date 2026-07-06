"""Content index read path contracts.

This module defines the contracts for the disabled-by-default content index
read path for k9b UI APIs.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from dataclasses import dataclass


class FallbackReason:
    """Bounded fallback reason codes for OTel span attributes."""

    INDEX_NOT_ENABLED = "index_not_enabled"
    INDEX_NOT_AVAILABLE = "index_not_available"
    INDEX_NOT_FOUND = "index_not_found"
    INDEX_CORRUPT = "index_corrupt"
    INDEX_SCHEMA_MISMATCH = "index_schema_mismatch"
    INDEX_VALIDATION_FAILED = "index_validation_failed"
    INDEX_OPEN_ERROR = "index_open_error"
    PROJECTION_ERROR = "projection_error"


@dataclass(frozen=True)
class IndexOpenResult:
    """Result of opening the content index database."""

    ok: bool
    reason: str | None

    @classmethod
    def success(cls) -> IndexOpenResult:
        return cls(ok=True, reason=None)

    @classmethod
    def failure(cls, reason: str) -> IndexOpenResult:
        return cls(ok=False, reason=reason)


@dataclass(frozen=True)
class IndexValidationResult:
    """Result of validating the content index database."""

    ok: bool
    reason: str | None
    schema_version: str | None = None

    @classmethod
    def success(cls, schema_version: str) -> IndexValidationResult:
        return cls(ok=True, reason=None, schema_version=schema_version)

    @classmethod
    def failure(cls, reason: str) -> IndexValidationResult:
        return cls(ok=False, reason=reason, schema_version=None)


@dataclass(frozen=True)
class IndexReadResult:
    """Result of an index read operation."""

    data: dict[str, object] | None
    fallback_reason: str | None
    schema_version: str | None
    count: int
    index_available: bool

    @classmethod
    def fallback(cls, reason: str, count: int = 0) -> IndexReadResult:
        return cls(
            data=None,
            fallback_reason=reason,
            schema_version=None,
            count=count,
            index_available=False,
        )

    @classmethod
    def from_index(
        cls, data: dict[str, object], schema_version: str, count: int
    ) -> IndexReadResult:
        return cls(
            data=data,
            fallback_reason=None,
            schema_version=schema_version,
            count=count,
            index_available=True,
        )
