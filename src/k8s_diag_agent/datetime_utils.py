"""Centralized datetime normalization utilities for UTC-aware comparison safety.

All runtime comparison/order/freshness datetimes must be timezone-aware UTC.
This module provides:
- parse_iso_to_utc: Parse ISO timestamp strings to aware UTC datetime
- ensure_utc: Normalize any datetime (naive or aware) to aware UTC
- now_utc: Current time as aware UTC datetime
- fromtimestamp_utc: POSIX timestamp to aware UTC datetime
- mtime_to_utc: File mtime to aware UTC datetime

See: docs/doctrine/30-output-contracts.md for comparison safety contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def now_utc() -> datetime:
    """Return current time as timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    If the datetime is already aware (has tzinfo), convert to UTC.
    If naive, assume UTC and add UTC timezone (note: this is a conversion,
    not parsing - only use for datetimes known to be UTC).
    """
    if value.tzinfo is None:
        # Naive datetime: assume UTC and attach timezone
        return value.replace(tzinfo=UTC)
    # Already aware: convert to UTC
    return value.astimezone(UTC)


def parse_iso_to_utc(value: str | None | object) -> datetime | None:
    """Parse an ISO 8601 timestamp string to timezone-aware UTC datetime.

    Handles:
    - Strings with explicit timezone offset (e.g., +00:00, -05:00)
    - Strings with 'Z' suffix (ISO 8601 legacy format)
    - Naive strings (no timezone): treats as UTC, attaches UTC timezone

    Returns None for empty/None inputs.
    Returns aware UTC datetime for all valid inputs.
    """
    if not isinstance(value, str) or not value:
        return None
    # Normalize 'Z' suffix to +00:00 for consistent parsing
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    # Note: Python 3.11+ accepts offset without colon (e.g., +0000, -0500)
    # directly via fromisoformat(), so no explicit normalization needed here.
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Normalize to UTC aware datetime
    return ensure_utc(parsed)


def parse_iso_or_now(value: str | None) -> datetime:
    """Parse ISO timestamp string to UTC aware datetime, or return current UTC time.

    Used when a fallback to 'now' is acceptable.
    """
    parsed = parse_iso_to_utc(value)
    return parsed if parsed is not None else now_utc()


def fromtimestamp_utc(timestamp: float | int) -> datetime:
    """Convert POSIX timestamp to timezone-aware UTC datetime."""
    return datetime.fromtimestamp(timestamp, tz=UTC)


def mtime_to_utc(path: Path) -> datetime | None:
    """Convert file mtime to timezone-aware UTC datetime.

    Returns None if the file doesn't exist or cannot be stat'd.
    """
    try:
        return fromtimestamp_utc(path.stat().st_mtime)
    except OSError:
        return None


# Alias for backwards compatibility during migration
def _legacy_parse_timestamp(value: str | None) -> datetime | None:
    """Legacy parser - DEPRECATED, use parse_iso_to_utc instead.

    This function has the same behavior as the old _parse_timestamp
    but is kept for reference during migration.
    """
    return parse_iso_to_utc(value)
