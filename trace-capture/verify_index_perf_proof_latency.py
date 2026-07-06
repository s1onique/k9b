"""Latency calculation functions for index performance proof verification."""

from __future__ import annotations

from verify_index_perf_proof_contract import LatencyDelta


def compute_latency_delta(
    disabled_stats: dict[str, float | None],
    enabled_stats: dict[str, float | None],
) -> LatencyDelta:
    """Compute latency delta between disabled and enabled runs.

    Args:
        disabled_stats: Latency stats from disabled run
        enabled_stats: Latency stats from enabled run

    Returns:
        LatencyDelta with computed deltas and percentages
    """
    delta = LatencyDelta()

    def _get_float(d: dict[str, float | None], key: str) -> float:
        """Get float value from dict, handling None gracefully."""
        val = d.get(key, 0.0)
        return val if val is not None else 0.0

    # Extract values (handle missing keys and None values gracefully)
    delta.disabled_p50_ms = _get_float(disabled_stats, "p50")
    delta.enabled_p50_ms = _get_float(enabled_stats, "p50")
    delta.disabled_p90_ms = _get_float(disabled_stats, "p90")
    delta.enabled_p90_ms = _get_float(enabled_stats, "p90")
    delta.disabled_p99_ms = _get_float(disabled_stats, "p99")
    delta.enabled_p99_ms = _get_float(enabled_stats, "p99")

    # Compute deltas (positive = improvement, negative = regression)
    delta.p50_delta_ms = delta.disabled_p50_ms - delta.enabled_p50_ms
    delta.p90_delta_ms = delta.disabled_p90_ms - delta.enabled_p90_ms
    delta.p99_delta_ms = delta.disabled_p99_ms - delta.enabled_p99_ms

    # Compute improvement percentages
    if delta.disabled_p50_ms > 0:
        delta.p50_improvement_percent = (delta.p50_delta_ms / delta.disabled_p50_ms) * 100
    if delta.disabled_p90_ms > 0:
        delta.p90_improvement_percent = (delta.p90_delta_ms / delta.disabled_p90_ms) * 100
    if delta.disabled_p99_ms > 0:
        delta.p99_improvement_percent = (delta.p99_delta_ms / delta.disabled_p99_ms) * 100

    return delta


def compute_improvement_percent(delta_ms: float, baseline_ms: float) -> float:
    """Compute improvement percentage from delta.

    Args:
        delta_ms: Latency delta in milliseconds (positive = improvement)
        baseline_ms: Baseline latency in milliseconds

    Returns:
        Improvement percentage (positive = improvement, negative = regression)
    """
    if baseline_ms <= 0:
        return 0.0
    return (delta_ms / baseline_ms) * 100


def check_no_regression(delta: LatencyDelta, threshold_percent: float = 5.0) -> bool:
    """Check if there's no significant regression.

    Args:
        delta: Latency delta
        threshold_percent: Acceptable regression threshold (default 5%)

    Returns:
        True if no significant regression
    """
    # p50 should not regress by more than threshold
    if delta.p50_improvement_percent < -threshold_percent:
        return False
    return True
