"""Unit tests for perf_baseline_stats module.

Tests cover:
1. Percentile calculation (empty, single, multi)
2. Status code histogram building
3. Latency statistics aggregation
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from perf_baseline_stats import build_status_histogram, compute_latency_stats


class TestPercentileCalculation:
    """Tests for latency percentile computation."""

    def test_empty_list_returns_zeros(self) -> None:
        """Empty input returns zero values for all percentiles."""
        result = compute_latency_stats([])
        assert result == {"min": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}

    def test_single_value(self) -> None:
        """Single value returns same value for all percentiles."""
        result = compute_latency_stats([42.0])
        assert result["min"] == 42.0
        assert result["p50"] == 42.0
        assert result["p90"] == 42.0
        assert result["p95"] == 42.0
        assert result["p99"] == 42.0
        assert result["max"] == 42.0

    def test_sorted_latencies(self) -> None:
        """Percentiles are computed correctly for sorted data."""
        # 10 values from 1 to 10
        latencies = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = compute_latency_stats(latencies)

        assert result["min"] == 1.0
        assert result["max"] == 10.0
        # p50 should be ~5.5 (interpolated between 5 and 6)
        assert 5.0 <= result["p50"] <= 6.0
        # p90 should be ~9.1 (interpolated between 9 and 10)
        assert 9.0 <= result["p90"] <= 10.0

    def test_unsorted_input(self) -> None:
        """Unsorted input is handled correctly."""
        latencies = [10.0, 5.0, 15.0, 2.0, 8.0]
        result = compute_latency_stats(latencies)

        assert result["min"] == 2.0
        assert result["max"] == 15.0

    def test_identical_values(self) -> None:
        """All identical values return that value for all percentiles."""
        latencies = [100.0, 100.0, 100.0, 100.0, 100.0]
        result = compute_latency_stats(latencies)

        for key in ["min", "p50", "p90", "p95", "p99", "max"]:
            assert result[key] == 100.0

    def test_p95_calculation(self) -> None:
        """p95 is computed correctly."""
        # 20 values, p95 should be near the 19th value
        latencies = list(range(1, 21))
        result = compute_latency_stats(latencies)
        # p95 should be between 18 and 20
        assert 18.0 <= result["p95"] <= 20.0

    def test_p99_calculation(self) -> None:
        """p99 is computed correctly."""
        # 100 values from 1 to 100
        latencies = list(range(1, 101))
        result = compute_latency_stats(latencies)
        # p99 should be near the top
        assert 95.0 <= result["p99"] <= 100.0


class TestStatusHistogram:
    """Tests for status code histogram building."""

    def test_empty_list(self) -> None:
        """Empty input returns empty histogram."""
        result = build_status_histogram([])
        assert result == {}

    def test_single_status(self) -> None:
        """Single status code returns count of 1."""
        result = build_status_histogram([200])
        assert result == {"200": 1}

    def test_multiple_same_status(self) -> None:
        """Multiple same status codes are counted correctly."""
        result = build_status_histogram([200, 200, 200])
        assert result == {"200": 3}

    def test_multiple_different_status(self) -> None:
        """Different status codes are counted correctly."""
        result = build_status_histogram([200, 200, 404, 500, 404])
        assert result == {"200": 2, "404": 2, "500": 1}

    def test_none_becomes_error(self) -> None:
        """None status code becomes 'error' key."""
        result = build_status_histogram([200, None, None])
        assert result == {"200": 1, "error": 2}

    def test_mixed_none_and_status(self) -> None:
        """Mixed None and status codes are handled correctly."""
        result = build_status_histogram([None, 200, 201, None])
        assert result == {"200": 1, "201": 1, "error": 2}

    def test_all_errors(self) -> None:
        """All None values become 'error' key."""
        result = build_status_histogram([None, None, None])
        assert result == {"error": 3}

    def test_sorted_keys(self) -> None:
        """Keys are strings, not integers."""
        result = build_status_histogram([200, 404])
        assert "200" in result
        assert "404" in result
        assert 200 not in result  # type: ignore
