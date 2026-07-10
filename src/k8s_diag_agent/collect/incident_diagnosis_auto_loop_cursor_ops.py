"""Cursor persistence operations for automatic diagnosis loop.

This module handles cursor save/clear/logging operations.
It is a leaf module that MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import assert_never

from .incident_diagnosis_auto_loop_cursor import (
    clear_scan_cursor,
    save_scan_cursor,
)
from .incident_diagnosis_cursor_disposition import (
    ClearScanCursor,
    KeepScanCursorUnchanged,
    SaveScanCursor,
)
from .incident_diagnosis_cursor_persistence import (
    CursorPersistenceDegraded,
)
from .incident_diagnosis_keyset_cursor import encode_cursor
from .incident_diagnosis_pagination_types import OpaqueCursorToken

_logger = logging.getLogger(__name__)


def handle_cursor_save(
    disposition: SaveScanCursor,
    runs_dir: Path,
) -> None:
    """Handle saving the scan cursor with logging."""
    cursor = disposition.cursor
    save_reason: str = disposition.reason.value
    cursor_token = encode_cursor(cursor)
    save_result = save_scan_cursor(runs_dir, OpaqueCursorToken(cursor_token))

    if isinstance(save_result, CursorPersistenceDegraded):
        _logger.warning(
            "Scan cursor save degraded",
            extra={
                "event": "scan-cursor-save-degraded",
                "operation": save_result.operation.value,
                "message": save_result.message,
                "reason": save_reason,
            },
        )

    _logger.info(
        "Saved scan cursor",
        extra={
            "event": "scan-cursor-saved",
            "cursor_incident_id": cursor.incident_id,
            "reason": save_reason,
        },
    )


def handle_cursor_clear(
    disposition: ClearScanCursor,
    runs_dir: Path,
) -> None:
    """Handle clearing the scan cursor with logging."""
    clear_reason: str = disposition.reason.value
    clear_result = clear_scan_cursor(runs_dir)

    if isinstance(clear_result, CursorPersistenceDegraded):
        _logger.warning(
            "Scan cursor clear degraded",
            extra={
                "event": "scan-cursor-clear-degraded",
                "operation": clear_result.operation.value,
                "message": clear_result.message,
                "reason": clear_reason,
            },
        )

    _logger.info(
        "Cleared scan cursor",
        extra={
            "event": "scan-cursor-cleared",
            "reason": clear_reason,
        },
    )


def handle_cursor_unchanged(
    disposition: KeepScanCursorUnchanged,
) -> None:
    """Handle keeping cursor unchanged with debug logging."""
    keep_reason: str = disposition.reason.value
    _logger.debug(
        "Cursor unchanged",
        extra={
            "event": "scan-cursor-unchanged",
            "reason": keep_reason,
        },
    )


def handle_cursor_disposition(
    disposition: ClearScanCursor | KeepScanCursorUnchanged | SaveScanCursor,
    runs_dir: Path,
) -> None:
    """Handle the result of decide_cursor_disposition().

    This function dispatches to the appropriate handler based on disposition type
    using exhaustive match to catch any future variants.
    """
    match disposition:
        case SaveScanCursor():
            handle_cursor_save(disposition, runs_dir)
        case ClearScanCursor():
            handle_cursor_clear(disposition, runs_dir)
        case KeepScanCursorUnchanged():
            handle_cursor_unchanged(disposition)
        case _ as unreachable:
            assert_never(unreachable)
