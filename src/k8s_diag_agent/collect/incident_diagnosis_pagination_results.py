"""Page-list result unions for incident diagnosis pagination.

This module replaces the stringly-typed optional triple:
    tuple[IncidentDiagnosisPage | None, CursorDecodeFailure | None, str | None]

With closed algebraic result variants that make invalid states unrepresentable:
- PageListed: Successful page listing
- PageCursorRejected: Cursor decoding failed
- PageListingFailed: Page listing operation failed

Every consumer MUST exhaustively handle all variants using match statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .incident_diagnosis_dispatch_page import (
        CursorDecodeFailure,
        IncidentDiagnosisPage,
    )


# =============================================================================
# Listing Failure Classification
# =============================================================================


class IncidentPageListingFailureKind(StrEnum):
    """Classified failure kinds for incident page listing.

    Every listing failure MUST be classified into one of these kinds.
    Do not return unclassified error strings from page-list functions.
    """

    MISSING_BACKEND_URL = "missing_backend_url"
    """Backend URL not configured."""

    MISSING_INTERNAL_TOKEN = "missing_internal_token"
    """Internal API token not configured."""

    UNAUTHORIZED = "unauthorized"
    """401/403 status code from backend."""

    FORBIDDEN = "forbidden"
    """403 status code from backend."""

    TIMEOUT = "timeout"
    """Request timed out."""

    INVALID_JSON = "invalid_json"
    """Response body is not valid JSON."""

    PROTOCOL_VIOLATION = "protocol_violation"
    """Response structure violates the contract."""

    STORE_UNAVAILABLE = "store_unavailable"
    """Local store is unavailable."""

    TRANSPORT_FAILURE = "transport_failure"
    """Network/connection failure."""

    INTERNAL_ERROR = "internal_error"
    """Unexpected internal error."""


# =============================================================================
# Result Variants
# =============================================================================


@dataclass(frozen=True, slots=True)
class IncidentPageListingFailure:
    """Classified failure for incident page listing.

    Attributes:
        kind: Classified failure kind from IncidentPageListingFailureKind
        message: Human-readable error message
        status_code: HTTP status code if available, None otherwise
    """

    kind: IncidentPageListingFailureKind
    message: str
    status_code: int | None = None


@dataclass(frozen=True, slots=True)
class PageListed:
    """Successful page listing result.

    Attributes:
        page: The incident diagnosis page with incidents and pagination info.
    """

    page: IncidentDiagnosisPage


@dataclass(frozen=True, slots=True)
class PageCursorRejected:
    """Cursor decoding failed before page listing.

    Attributes:
        failure: The cursor decode failure details.
    """

    failure: CursorDecodeFailure


@dataclass(frozen=True, slots=True)
class PageListingFailed:
    """Page listing operation failed.

    Attributes:
        failure: Classified failure with kind, message, and status code.
    """

    failure: IncidentPageListingFailure


# =============================================================================
# Orchestrator-Level Pagination Result (for list_incidents_with_pagination)
# =============================================================================


@dataclass(frozen=True, slots=True)
class AutomaticPageListed:
    """Successful page listing at the orchestrator level.

    Attributes:
        page: The incident diagnosis page with incidents and pagination info.
    """

    page: IncidentDiagnosisPage


@dataclass(frozen=True, slots=True)
class AutomaticPageCursorRejected:
    """Cursor decoding failed at the orchestrator level (caller-provided cursor).

    Attributes:
        failure: The cursor decode failure details.
    """

    failure: CursorDecodeFailure


@dataclass(frozen=True, slots=True)
class AutomaticPageListingFailed:
    """Page listing operation failed at the orchestrator level.

    Attributes:
        failure: Classified failure with kind, message, and status code.
    """

    failure: IncidentPageListingFailure


# =============================================================================
# Type Alias for Union
# =============================================================================


IncidentPageListResult: TypeAlias = PageListed | PageCursorRejected | PageListingFailed
"""Closed union of all possible page-list outcomes.

Consumers MUST exhaustively handle all three variants using match statements
with assert_never() for the unreachable case.

Example:
    from typing import assert_never

    match result:
        case PageListed(page=page):
            return handle_page(page)
        case PageCursorRejected(failure=failure):
            return handle_cursor_error(failure)
        case PageListingFailed(failure=failure):
            return handle_listing_error(failure)
        case _ as unreachable:
            assert_never(unreachable)
"""


AutomaticPageListResult: TypeAlias = (
    AutomaticPageListed | AutomaticPageCursorRejected | AutomaticPageListingFailed
)
"""Closed union for orchestrator-level pagination results.

Replaces the optional-result triple:
    tuple[IncidentDiagnosisPage | None, ... | None, str | None]

Example:
    from typing import assert_never

    match result:
        case AutomaticPageListed(page=page):
            return page, False
        case AutomaticPageCursorRejected(failure=failure):
            return None, True
        case AutomaticPageListingFailed(failure=failure):
            return None, True
        case _ as unreachable:
            assert_never(unreachable)
"""


__all__ = [
    "AutomaticPageCursorRejected",
    "AutomaticPageListed",
    "AutomaticPageListingFailed",
    "AutomaticPageListResult",
    "IncidentPageListingFailureKind",
    "IncidentPageListingFailure",
    "IncidentPageListResult",
    "PageListed",
    "PageCursorRejected",
    "PageListingFailed",
]
