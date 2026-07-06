"""Statistics computation for perf_baseline module.

This module contains:
- Percentile calculation (p50, p90, p95, p99)
- Status code histogram building
- Latency statistics aggregation
"""

from __future__ import annotations

from collections import defaultdict


def compute_latency_stats(latencies_ms: list[float]) -> dict[str, float]:
    """Compute latency statistics from a list of latencies.

    Args:
        latencies_ms: List of latency values in milliseconds

    Returns:
        Dictionary with min, p50, p90, p95, p99, max
    """
    if not latencies_ms:
        return {"min": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

    sorted_latencies = sorted(latencies_ms)

    def percentile(sorted_values: list[float], p: float) -> float:
        """Compute percentile from sorted values."""
        if not sorted_values:
            return 0.0
        idx = (p / 100.0) * (len(sorted_values) - 1)
        lower = int(idx)
        upper = lower + 1
        if upper >= len(sorted_values):
            return sorted_values[-1]
        weight = idx - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    return {
        "min": sorted_latencies[0],
        "p50": percentile(sorted_latencies, 50),
        "p90": percentile(sorted_latencies, 90),
        "p95": percentile(sorted_latencies, 95),
        "p99": percentile(sorted_latencies, 99),
        "max": sorted_latencies[-1],
    }


def build_status_histogram(
    status_codes: list[int | None],
) -> dict[str, int]:
    """Build histogram of status codes.

    Args:
        status_codes: List of HTTP status codes (None for failures)

    Returns:
        Dictionary mapping status code string to count
    """
    histogram: dict[str, int] = defaultdict(int)
    for code in status_codes:
        key = str(code) if code is not None else "error"
        histogram[key] += 1
    return dict(histogram)
