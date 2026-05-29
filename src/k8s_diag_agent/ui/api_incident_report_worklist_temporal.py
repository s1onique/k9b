"""Temporal context derivation for operator worklist items.

This module provides timestamp parsing and staleness classification for worklist items.

This module is an extraction from api_incident_report_worklist.py to reduce its
LLM-friendly file size while preserving backward-compatible re-exports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

# =============================================================================
# Constants - Staleness Thresholds
# =============================================================================

_STALENESS_FRESH_SECONDS = 5 * 60  # < 5 minutes
_STALENESS_AGING_SECONDS = 30 * 60  # 5-30 minutes
# > 30 minutes = stale


# =============================================================================
# Timestamp Parsing
# =============================================================================


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to datetime."""
    if not timestamp_str:
        return None
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    return None


# =============================================================================
# Temporal Context Derivation
# =============================================================================


def _derive_temporal_context(
    first_recommended_at: str | None,
    last_state_changed_at: str | None,
    current_run_timestamp: str | None,
) -> tuple[str | None, str | None, int | None, Literal["fresh", "aging", "stale", "unknown"] | None]:
    """Derive temporal context for a worklist item."""
    # Handle insufficient timing data first
    if not first_recommended_at or not current_run_timestamp:
        return first_recommended_at, last_state_changed_at, None, "unknown"

    now_dt = _parse_timestamp(current_run_timestamp)
    first_dt = _parse_timestamp(first_recommended_at)

    if not now_dt or not first_dt:
        return first_recommended_at, last_state_changed_at, None, "unknown"

    delta = now_dt - first_dt
    age_seconds = int(delta.total_seconds())

    if age_seconds < 0:
        return first_recommended_at, last_state_changed_at, None, "unknown"

    if age_seconds < _STALENESS_FRESH_SECONDS:
        staleness: Literal["fresh", "aging", "stale", "unknown"] = "fresh"
    elif age_seconds < _STALENESS_AGING_SECONDS:
        staleness = "aging"
    else:
        staleness = "stale"

    return first_recommended_at, last_state_changed_at, age_seconds, staleness
