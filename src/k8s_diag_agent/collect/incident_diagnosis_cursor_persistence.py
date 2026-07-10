"""Cursor persistence load/save algebra for automatic diagnosis loop.

This module replaces the stringly-typed optional pair:
    _load_scan_cursor(...) -> tuple[str | None, str | None]

With closed algebraic result variants:
- ScanCursorAbsent: No cursor file exists
- ScanCursorLoaded: Valid cursor token loaded
- ScanCursorReset: Legacy/invalid state cleared successfully
- ScanCursorReadDegraded: File system or cleanup failure

And persistence results:
- CursorPersistenceSucceeded: Save/clear operation completed
- CursorPersistenceDegraded: Save/clear failed but loop can continue
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .incident_diagnosis_pagination_types import OpaqueCursorToken


# =============================================================================
# Cursor Load Enums
# =============================================================================


class CursorResetReason(StrEnum):
    """Reasons for resetting/clearing the cursor."""

    LEGACY_FORMAT = "legacy_format"
    """Legacy cursor format detected."""

    LEGACY_STATE_SCHEMA = "legacy_state_schema"
    """Legacy state schema version detected."""

    UNKNOWN_STATE_SCHEMA = "unknown_state_schema"
    """Unknown state schema version."""

    INVALID_CURSOR_FIELD = "invalid_cursor_field"
    """Cursor token field is invalid."""

    INVALID_CURSOR_TOKEN = "invalid_cursor_token"
    """Cursor token could not be decoded."""

    UNSUPPORTED_CURSOR_VERSION = "unsupported_cursor_version"
    """Cursor token has unsupported version."""

    CORRUPTED_STATE_FILE = "corrupted_state_file"
    """State file is corrupted."""


class CursorPersistenceOperation(StrEnum):
    """Operations for persistence."""

    SAVE = "save"
    """Save cursor operation."""

    CLEAR = "clear"
    """Clear cursor operation."""


# =============================================================================
# Cursor Load Result Variants
# =============================================================================


@dataclass(frozen=True, slots=True)
class ScanCursorAbsent:
    """No cursor file exists."""

    pass


@dataclass(frozen=True, slots=True)
class ScanCursorLoaded:
    """Valid cursor token loaded from file.

    Attributes:
        token: The opaque cursor token.
    """

    token: OpaqueCursorToken


@dataclass(frozen=True, slots=True)
class ScanCursorReset:
    """Cursor was reset/cleared.

    Attributes:
        reason: Why the cursor was reset.
        observed_schema_version: The schema version that triggered reset, if any.
    """

    reason: CursorResetReason
    observed_schema_version: int | None = None


@dataclass(frozen=True, slots=True)
class ScanCursorReadDegraded:
    """Cursor read failed.

    Attributes:
        message: Error message describing the failure.
    """

    message: str


@dataclass(frozen=True, slots=True)
class ScanCursorResetDegraded:
    """Cursor reset was attempted but file cleanup failed.

    Attributes:
        reason: Why the cursor was reset.
        observed_schema_version: The schema version that triggered reset, if any.
        clear_operation: The failed clear operation.
        persistence_error: Error message from the failed clear.
    """

    reason: CursorResetReason
    observed_schema_version: int | None = None
    clear_operation: str | None = None
    persistence_error: str | None = None


# =============================================================================
# Type Alias
# =============================================================================


ScanCursorLoadResult: TypeAlias = (
    ScanCursorAbsent
    | ScanCursorLoaded
    | ScanCursorReset
    | ScanCursorReadDegraded
    | ScanCursorResetDegraded
)
"""Closed union of cursor load outcomes."""


# =============================================================================
# Persistence Result Variants
# =============================================================================


@dataclass(frozen=True, slots=True)
class CursorPersistenceSucceeded:
    """Persistence operation completed successfully."""

    pass


@dataclass(frozen=True, slots=True)
class CursorPersistenceDegraded:
    """Persistence operation failed.

    The diagnosis loop should continue even on degraded persistence.

    Attributes:
        operation: Which operation was attempted.
        message: Error message describing the failure.
    """

    operation: CursorPersistenceOperation
    message: str


CursorPersistenceResult: TypeAlias = CursorPersistenceSucceeded | CursorPersistenceDegraded
"""Closed union of persistence operation outcomes."""


__all__ = [
    "CursorResetReason",
    "CursorPersistenceOperation",
    "ScanCursorLoadResult",
    "ScanCursorAbsent",
    "ScanCursorLoaded",
    "ScanCursorReset",
    "ScanCursorReadDegraded",
    "ScanCursorResetDegraded",
    "CursorPersistenceResult",
    "CursorPersistenceSucceeded",
    "CursorPersistenceDegraded",
]
