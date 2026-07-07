"""Identity and correlation helpers for alert signals.

This module provides pure functions for computing alert signal identity
and correlation hints. These are used for future idempotency/deduplication
work in alert-to-incident promotion.

Design principles:
- Pure functions: no side effects
- Deterministic output for same input
- Do NOT promote to incidents
- Stable identity across normalization passes

Non-goals:
- Incident creation or mutation
- LLM-based classification
- Webhook endpoint implementation
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from .incident_alert_signal import (
    AlertCorrelationHints,
    AlertSignal,
)
from .incident_alert_signal_helpers import _enum_value

if TYPE_CHECKING:
    pass


# =============================================================================
# Stable Label Keys for Identity
# =============================================================================

# These labels are considered stable for identity computation
# (excludes transient labels like k9b.dev/source_type)
STABLE_IDENTITY_LABELS: frozenset[str] = frozenset({
    "alertname",
    "severity",
    "namespace",
    "pod",
    "deployment",
    "job",
    "instance",
    "host",
    "cluster",
})


# =============================================================================
# Identity Computation
# =============================================================================

def alert_signal_identity(signal: AlertSignal) -> str:
    """Compute stable identity string for an alert signal.

    This identity is used for deduplication and idempotency.
    It should be stable across normalization passes for the same alert.

    Identity inputs (in order of priority):
    1. source_instance
    2. external_fingerprint (if present)
    3. alertname
    4. starts_at (if present)
    5. status

    Fallback when fingerprint is absent:
    1. source_instance
    2. alertname
    3. stable selected labels (sorted)
    4. starts_at
    5. status

    Args:
        signal: The alert signal to compute identity for

    Returns:
        Stable identity string (hex digest)
    """
    parts: list[str] = [
        str(signal.source_instance),
        str(signal.alertname),
        _enum_value(signal.status),
    ]

    # Add fingerprint if available
    if signal.external_fingerprint:
        parts.append(str(signal.external_fingerprint))
    else:
        # Use stable labels for fallback identity
        stable_parts: list[str] = []
        for key, value in signal.labels:
            if key in STABLE_IDENTITY_LABELS:
                stable_parts.append(f"{key}={value}")
        # Sort for determinism
        stable_parts.sort()
        parts.append("|".join(stable_parts))

    # Add timestamp if available
    if signal.starts_at:
        parts.append(signal.starts_at.isoformat())

    # Combine and hash
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _iter_labels(
    labels: Mapping[object, object] | Iterable[tuple[object, object]],
) -> Iterable[tuple[str, str]]:
    """Iterate over labels as (key, value) tuples.

    Handles both Mapping (dict) and tuple[tuple[str, str]] formats.
    Normalizes keys and values to strings.
    """
    items = labels.items() if isinstance(labels, Mapping) else labels
    for key, value in items:
        yield str(key), str(value)


def alert_signal_correlation_hints(signal: AlertSignal) -> AlertCorrelationHints:
    """Compute correlation hints for an alert signal.

    These hints are used by future ACTs for:
    - Alert-to-incident correlation
    - Alert deduplication across sources
    - Grouping related alerts

    The hints include:
    - Core identity fields
    - Stable label subset for fuzzy matching
    - Temporal window hints
    - External references

    Args:
        signal: The alert signal to compute hints for

    Returns:
        AlertCorrelationHints with correlation metadata
    """
    # Extract stable labels for fuzzy matching
    stable_labels: list[tuple[str, str]] = []
    for key, value in _iter_labels(signal.labels):
        if key in STABLE_IDENTITY_LABELS:
            stable_labels.append((key, value))

    return AlertCorrelationHints(
        source_instance=signal.source_instance,
        alertname=signal.alertname,
        severity=signal.severity,
        stable_labels=tuple(stable_labels),
        starts_at=signal.starts_at,
        ends_at=signal.ends_at,
        external_fingerprint=signal.external_fingerprint,
        generator_url=signal.generator_url,
    )


# =============================================================================
# Identity Helpers for Lists
# =============================================================================

def dedupe_signals_by_identity(
    signals: list[AlertSignal],
) -> list[AlertSignal]:
    """Remove duplicate signals by identity.

    When duplicate identities are found, keeps the first occurrence.

    Args:
        signals: List of signals to deduplicate

    Returns:
        List of unique signals
    """
    seen: set[str] = set()
    result: list[AlertSignal] = []

    for signal in signals:
        identity = alert_signal_identity(signal)
        if identity not in seen:
            seen.add(identity)
            result.append(signal)

    return result


def group_signals_by_identity(
    signals: list[AlertSignal],
) -> dict[str, list[AlertSignal]]:
    """Group signals by identity.

    Args:
        signals: List of signals to group

    Returns:
        Dict mapping identity to list of signals with that identity
    """
    result: dict[str, list[AlertSignal]] = {}

    for signal in signals:
        identity = alert_signal_identity(signal)
        if identity not in result:
            result[identity] = []
        result[identity].append(signal)

    return result


# =============================================================================
# Signal Comparison
# =============================================================================

def signals_are_same_alert(
    a: AlertSignal,
    b: AlertSignal,
) -> bool:
    """Check if two signals represent the same alert.

    Two signals are considered the same if they have the same identity.

    Args:
        a: First signal
        b: Second signal

    Returns:
        True if signals have the same identity
    """
    return alert_signal_identity(a) == alert_signal_identity(b)


def signals_can_correlate(
    a: AlertSignal,
    b: AlertSignal,
) -> bool:
    """Check if two signals can potentially correlate.

    Signals can correlate if:
    - They have the same source instance
    - They have the same alertname
    - They overlap in time

    This is a loose correlation check, not an identity check.

    Args:
        a: First signal
        b: Second signal

    Returns:
        True if signals can potentially correlate
    """
    # Must be same source
    if a.source_instance != b.source_instance:
        return False

    # Must have same alertname
    if a.alertname != b.alertname:
        return False

    # Must overlap in time
    a_start = a.starts_at
    a_end = a.ends_at
    b_start = b.starts_at
    b_end = b.ends_at

    # Handle None values
    if a_start is None and b_start is None:
        return True  # Both have no start time
    if a_start is None:
        return b_end is None or b_start <= a_end  # type: ignore[operator]
    if b_start is None:
        return a_end is None or a_start <= b_end  # type: ignore[operator]

    # Both have start times - check for overlap
    a_end_ts = a_end.timestamp() if a_end else float("inf")
    b_end_ts = b_end.timestamp() if b_end else float("inf")

    return a_start.timestamp() <= b_end_ts and b_start.timestamp() <= a_end_ts


# =============================================================================
# Signal Selection for Deduplication
# =============================================================================

def select_latest_signal(
    signals: list[AlertSignal],
) -> AlertSignal | None:
    """Select the most recent signal from a list.

    Uses received_at for ordering.

    Args:
        signals: List of signals (should have same identity)

    Returns:
        Most recent signal or None if list is empty
    """
    if not signals:
        return None

    return max(signals, key=lambda s: s.received_at)


def select_signals_for_incident(
    signals: list[AlertSignal],
    max_count: int = 10,
) -> list[AlertSignal]:
    """Select signals suitable for attaching to an incident.

    Selects signals in priority order:
    1. Firing signals first
    2. Most recent signals first
    3. Limited to max_count

    Args:
        signals: List of signals to select from
        max_count: Maximum number of signals to return

    Returns:
        Selected signals
    """
    if not signals:
        return []

    # Sort: firing first, then by received_at
    sorted_signals = sorted(
        signals,
        key=lambda s: (
            0 if _enum_value(s.status) == "firing" else 1,  # firing first
            -s.received_at.timestamp(),  # most recent first
        ),
    )

    return sorted_signals[:max_count]


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Constants
    "STABLE_IDENTITY_LABELS",
    # Identity computation
    "alert_signal_identity",
    "alert_signal_correlation_hints",
    # Deduplication
    "dedupe_signals_by_identity",
    "group_signals_by_identity",
    # Comparison
    "signals_are_same_alert",
    "signals_can_correlate",
    # Selection
    "select_latest_signal",
    "select_signals_for_incident",
]
