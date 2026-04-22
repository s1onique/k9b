"""Drilldown execution helpers for the health loop.

Extracts drilldown-trigger determination helpers from loop.py into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides the drilldown logic that:
1. Determines whether a drilldown should be triggered for a cluster
2. Computes the set of drilldown reasons (manual, regression, patterns, etc.)

These are pure helpers with no runner orchestration logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .image_pull_secret import BROKEN_IMAGE_PULL_SECRET_REASON
from .loop_history import HealthHistoryEntry, HealthRating
from .utils import normalize_ref

if TYPE_CHECKING:
    from .loop import HealthSnapshotRecord


def determine_drilldown_reasons(
    record: HealthSnapshotRecord,
    previous_history: dict[str, HealthHistoryEntry],
    manual_drilldown_contexts: set[str],
    warning_event_threshold: int,
) -> tuple[str, ...]:
    """Determine the reasons for triggering a drilldown for a cluster.

    Evaluates multiple signals to decide if drilldown collection is warranted:
    - Manual request (explicit context in manual drilldown set)
    - Health regression (previously healthy, now degraded)
    - Specific workload issues (CrashLoopBackOff, ImagePullBackOff)
    - Warning event threshold exceeded
    - Job failures
    - Image pull secret issues
    - Pattern-based reasons from assessment

    Args:
        record: The current health snapshot record with assessment
        previous_history: Prior health entries indexed by cluster_id
        manual_drilldown_contexts: Set of contexts that were manually requested for drilldown
        warning_event_threshold: Minimum warning events to trigger drilldown (0 = any)

    Returns:
        Tuple of unique drilldown reason strings, ordered by first occurrence.
        Empty tuple if no drilldown is warranted.
    """
    if not record.assessment:
        return ()

    reasons: list[str] = []
    normalized_context = normalize_ref(record.target.context)
    if normalized_context in manual_drilldown_contexts:
        reasons.append("manual_request")

    prev_entry = previous_history.get(record.snapshot.metadata.cluster_id)
    if (
        prev_entry
        and prev_entry.health_rating == HealthRating.HEALTHY
        and record.assessment.rating == HealthRating.DEGRADED
    ):
        reasons.append("health_regression")

    pod_counts = record.snapshot.health_signals.pod_counts
    if pod_counts.crash_loop_backoff > 0:
        reasons.append("CrashLoopBackOff")
    if pod_counts.image_pull_backoff > 0:
        reasons.append("ImagePullBackOff")

    warning_events = record.snapshot.health_signals.warning_events
    threshold_met = (
        len(warning_events) > 0
        if warning_event_threshold <= 0
        else len(warning_events) >= warning_event_threshold
    )
    if threshold_met:
        reasons.append("warning_event_threshold")

    if record.snapshot.health_signals.job_failures > 0:
        reasons.append("job_failures")

    if record.image_pull_secret_insight:
        reasons.append(BROKEN_IMAGE_PULL_SECRET_REASON)

    reasons.extend(record.pattern_reasons)

    # Deduplicate while preserving order
    unique_reasons: tuple[str, ...] = tuple(dict.fromkeys(reasons))
    return unique_reasons


def format_drilldown_reasons(reasons: tuple[str, ...]) -> str:
    """Format drilldown reasons as a human-readable string.

    Args:
        reasons: Tuple of drilldown reason strings

    Returns:
        Comma-separated string of reasons, or "none" if empty
    """
    if not reasons:
        return "none"
    return ", ".join(reasons)
