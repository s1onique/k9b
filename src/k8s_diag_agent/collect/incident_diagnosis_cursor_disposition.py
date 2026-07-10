"""Cursor disposition state machine for automatic diagnosis loop.

This module provides a PURE state transition function that decides whether to:
- Save the scan cursor (partial page or more pages exist)
- Clear the scan cursor (final page consumed)
- Keep the scan cursor unchanged (explicit selection, listing failure)

The function has NO side effects - no filesystem, no logging, no clocks, no store access.

Truth table:
| Condition                                      | Result                               |
|------------------------------------------------|--------------------------------------|
| Explicit incident IDs                           | KeepScanCursorUnchanged              |
| Listing failed before page acquisition          | KeepScanCursorUnchanged              |
| No page rows and cursor suffix exhausted        | ClearScanCursor                     |
| examined < page_rows and cursor exists          | SaveScanCursor                      |
| All rows examined and has_more=True             | SaveScanCursor                      |
| All rows examined and has_more=False            | ClearScanCursor                     |
| A save required but no last cursor exists       | CursorDispositionInvariantError      |
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .incident_diagnosis_keyset_cursor import IncidentDiagnosisCursor


# =============================================================================
# Cursor Disposition Enums
# =============================================================================


class CursorSaveReason(StrEnum):
    """Reasons for saving the cursor."""

    PARTIAL_PAGE = "partial_page"
    """Not all rows in the page were examined."""

    MORE_PAGES = "more_pages"
    """All rows examined but more pages exist."""


class CursorClearReason(StrEnum):
    """Reasons for clearing the cursor."""

    FINAL_PAGE_CONSUMED = "final_page_consumed"
    """All rows examined and no more pages exist."""

    EMPTY_SUFFIX_REACHED = "empty_suffix_reached"
    """No page rows and cursor suffix exhausted."""


class CursorKeepReason(StrEnum):
    """Reasons for keeping the cursor unchanged."""

    EXPLICIT_INCIDENT_SELECTION = "explicit_incident_selection"
    """Explicit incident IDs were provided."""

    NO_ROW_EXAMINED = "no_row_examined"
    """Listing failed before any rows were examined."""

    LISTING_FAILED = "listing_failed"
    """Page listing operation failed."""


# =============================================================================
# Cursor Disposition Variants
# =============================================================================


@dataclass(frozen=True, slots=True)
class SaveScanCursor:
    """Decision to save the scan cursor.

    Attributes:
        cursor: The cursor to save.
        reason: Why the cursor is being saved.
    """

    cursor: IncidentDiagnosisCursor
    reason: CursorSaveReason


@dataclass(frozen=True, slots=True)
class ClearScanCursor:
    """Decision to clear the scan cursor.

    Attributes:
        reason: Why the cursor is being cleared.
    """

    reason: CursorClearReason


@dataclass(frozen=True, slots=True)
class KeepScanCursorUnchanged:
    """Decision to keep the cursor unchanged.

    Attributes:
        reason: Why the cursor is not being modified.
    """

    reason: CursorKeepReason


# =============================================================================
# Type Alias
# =============================================================================


CursorDisposition: TypeAlias = SaveScanCursor | ClearScanCursor | KeepScanCursorUnchanged
"""Closed union of cursor disposition outcomes."""


# =============================================================================
# Invariant Error
# =============================================================================


class CursorDispositionInvariantError(RuntimeError):
    """Raised when cursor disposition invariants are violated.

    This happens when a save is required but no last cursor exists.
    """

    pass


# =============================================================================
# Pure Decision Function
# =============================================================================


def decide_cursor_disposition(
    *,
    automatic_selection: bool,
    examined_rows: int,
    page_rows: int,
    has_more: bool,
    last_examined_cursor: IncidentDiagnosisCursor | None,
    listing_failed: bool = False,
    cursor_was_present: bool = False,
) -> CursorDisposition:
    """Decide cursor disposition based on page consumption.

    This is a PURE function with no side effects.

    Truth table for empty suffix:
    | examined_rows | page_rows | cursor_was_present | Result                |
    |---------------|----------|-------------------|------------------------|
    | 0             | 0        | false             | KeepScanCursorUnchanged|
    | 0             | 0        | true              | ClearScanCursor        |

    Args:
        automatic_selection: True if this is automatic selection, False for explicit IDs
        examined_rows: Number of rows examined in this run
        page_rows: Total number of rows in the page
        has_more: True if there are more pages after this one
        last_examined_cursor: Cursor of the last examined row, if any
        listing_failed: True if page listing failed
        cursor_was_present: True if a cursor was loaded at the start of the scan

    Returns:
        CursorDisposition variant indicating what to do with the cursor

    Raises:
        CursorDispositionInvariantError: If a save is required but no cursor exists
    """
    # Explicit incident IDs: never modify cursor
    if not automatic_selection:
        return KeepScanCursorUnchanged(reason=CursorKeepReason.EXPLICIT_INCIDENT_SELECTION)

    # Listing failed: keep unchanged
    if listing_failed:
        return KeepScanCursorUnchanged(reason=CursorKeepReason.LISTING_FAILED)

    # Empty page: determine disposition based on cursor history
    # Note: This check must come before page_fully_examined because 0 >= 0 is True
    # and would incorrectly trigger FINAL_PAGE_CONSUMED for empty suffix cases.
    #
    # Key distinction: EMPTY_SUFFIX_REACHED happens when:
    # - page_rows=0 (no data found) AND cursor_was_present=True (cursor existed)
    #   This means cursor jumped past all remaining data
    #
    # This is independent of has_more because:
    # - has_more=True: More pages exist, but current query returned 0 rows (gap)
    # - has_more=False: No more pages, but cursor existed (exhausted suffix)
    #
    # Both cases mean "cursor existed but no data found after it"
    if page_rows == 0:
        if cursor_was_present:
            # Empty suffix reached after cursor was present - clear cursor
            return ClearScanCursor(reason=CursorClearReason.EMPTY_SUFFIX_REACHED)
        else:
            # Empty first scan with no cursor - keep unchanged
            return KeepScanCursorUnchanged(reason=CursorKeepReason.NO_ROW_EXAMINED)

    # Determine if page was fully examined
    page_fully_examined = examined_rows >= page_rows

    if page_fully_examined:
        # All rows examined
        if has_more:
            # More pages exist - save cursor to advance to next page
            if last_examined_cursor is None:
                raise CursorDispositionInvariantError(
                    "Save required (more pages) but no last cursor exists"
                )
            return SaveScanCursor(
                cursor=last_examined_cursor,
                reason=CursorSaveReason.MORE_PAGES,
            )
        else:
            # Final page consumed - clear cursor
            return ClearScanCursor(reason=CursorClearReason.FINAL_PAGE_CONSUMED)
    else:
        # Partial page examined - save cursor to resume mid-page
        if last_examined_cursor is None:
            raise CursorDispositionInvariantError(
                "Save required (partial page) but no last cursor exists"
            )
        return SaveScanCursor(
            cursor=last_examined_cursor,
            reason=CursorSaveReason.PARTIAL_PAGE,
        )


__all__ = [
    "CursorSaveReason",
    "CursorClearReason",
    "CursorKeepReason",
    "CursorDisposition",
    "CursorDispositionInvariantError",
    "SaveScanCursor",
    "ClearScanCursor",
    "KeepScanCursorUnchanged",
    "decide_cursor_disposition",
]
