"""Freshness helpers shared between scheduler logs and UI payloads."""

from __future__ import annotations


def freshness_status(age_seconds: float | None, expected_interval_seconds: int | None) -> str | None:
    """Describe how fresh a run is relative to the expected scheduler interval."""
    if age_seconds is None or expected_interval_seconds is None:
        return None
    if age_seconds <= expected_interval_seconds:
        return "fresh"
    if age_seconds <= expected_interval_seconds * 2:
        return "delayed"
    return "stale"
