"""Incident listing and pagination operations for automatic diagnosis loop.

This module handles incident listing, cursor loading, and page handling.
It is a leaf module that MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import assert_never

from .incident_diagnosis_auto_loop_cursor import (
    load_scan_cursor,
)
from .incident_diagnosis_cursor_persistence import (
    ScanCursorAbsent,
    ScanCursorLoaded,
    ScanCursorReadDegraded,
    ScanCursorReset,
    ScanCursorResetDegraded,
)
from .incident_diagnosis_dispatch import (
    list_incidents_for_diagnosis_page,
)
from .incident_diagnosis_pagination_results import (
    AutomaticPageCursorRejected,
    AutomaticPageListed,
    AutomaticPageListingFailed,
    AutomaticPageListResult,
    PageCursorRejected,
    PageListed,
    PageListingFailed,
)
from .incident_diagnosis_pagination_types import OpaqueCursorToken

_logger = logging.getLogger(__name__)


def load_cursor_for_scan(runs_dir: Path) -> tuple[OpaqueCursorToken | None, bool]:
    """Load persisted scan cursor for fair queuing.

    Returns:
        Tuple of (scan_cursor, cursor_was_present)
    """
    load_result = load_scan_cursor(runs_dir)
    match load_result:
        case ScanCursorAbsent():
            _logger.debug("No existing scan cursor")
            return None, False
        case ScanCursorLoaded(token=token):
            _logger.debug("Loaded existing scan cursor")
            return token, True
        case ScanCursorReset(reason=reason, observed_schema_version=version):
            _logger.info(
                "Automatic diagnosis cursor reset",
                extra={
                    "event": "automatic-diagnosis-cursor-reset",
                    "reset_reason": reason.value,
                    "observed_schema_version": version,
                },
            )
            return None, False
        case ScanCursorResetDegraded(reason=reason, observed_schema_version=version, persistence_error=err):
            _logger.warning(
                "Automatic diagnosis cursor reset degraded",
                extra={
                    "event": "automatic-diagnosis-cursor-reset-degraded",
                    "reset_reason": reason.value,
                    "observed_schema_version": version,
                    "persistence_error": err,
                },
            )
            return None, False
        case ScanCursorReadDegraded(message=message):
            _logger.warning(
                "Scan cursor read degraded, proceeding without cursor",
                extra={
                    "event": "scan-cursor-read-degraded",
                    "message": message,
                },
            )
            return None, False


def list_incidents_with_pagination(
    scan_cursor: OpaqueCursorToken | None,
    scan_bound: int,
) -> AutomaticPageListResult:
    """List incidents with cursor-based pagination.

    Returns a closed algebraic result (no optional triple):
    - AutomaticPageListed: Successful page listing
    - AutomaticPageCursorRejected: Caller-provided cursor was invalid
    - AutomaticPageListingFailed: Page listing operation failed

    Args:
        scan_cursor: Optional cursor token for resuming from previous scan
        scan_bound: Maximum number of incidents per page

    Returns:
        AutomaticPageListResult with exhaustive variants
    """
    from .incident_diagnosis_keyset_cursor import DiagnosisPageLimit

    page_result = list_incidents_for_diagnosis_page(
        limit=DiagnosisPageLimit(scan_bound),
        active_only=True,
        cursor=str(scan_cursor) if scan_cursor else None,
    )

    # Map dispatch-level results to orchestrator-level results
    # Exhaustive match protects closed result algebra when variants change
    match page_result:
        case PageListed(page=page):
            return AutomaticPageListed(page=page)
        case PageCursorRejected(failure=failure):
            return AutomaticPageCursorRejected(failure=failure)
        case PageListingFailed(failure=failure):
            return AutomaticPageListingFailed(failure=failure)
        case _ as unreachable:
            assert_never(unreachable)
