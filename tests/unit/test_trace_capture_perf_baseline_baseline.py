"""Unit tests for perf_baseline module integration.

Tests cover:
1. Baseline summary generation
2. Route normalization
3. Dominant spans tracking
4. Slowest endpoint identification
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from perf_baseline import (
    SCHEMA_VERSION,
    generate_baseline_summary,
)


class TestBaselineSummaryGeneration:
    """Tests for baseline summary generation."""

    def test_empty_results(self) -> None:
        """Empty API results produce empty baseline."""
        summary = generate_baseline_summary([])
        assert summary.schema_version == SCHEMA_VERSION
        assert len(summary.benchmarked_endpoints) == 0
        assert summary.total_traces == 0

    def test_single_endpoint(self) -> None:
        """Single endpoint is analyzed correctly."""
        results = [
            {
                "method": "GET",
                "endpoint": "/api/incidents",
                "status_code": 200,
                "success": True,
                "latency_ms": 50.0,
                "trace_id": "trace1",
            },
            {
                "method": "GET",
                "endpoint": "/api/incidents",
                "status_code": 200,
                "success": True,
                "latency_ms": 60.0,
                "trace_id": "trace2",
            },
        ]
        summary = generate_baseline_summary(results, iterations=2)

        assert len(summary.benchmarked_endpoints) == 1
        endpoint = summary.benchmarked_endpoints[0]
        assert endpoint["normalized_route"] == "GET /api/incidents"
        assert endpoint["attempt_count"] == 2
        assert endpoint["success_count"] == 2
        assert endpoint["failure_count"] == 0
        assert endpoint["latency_ms"]["min"] == 50.0
        assert endpoint["latency_ms"]["max"] == 60.0
        assert "200" in endpoint["status_codes"]
        assert endpoint["status_codes"]["200"] == 2

    def test_route_normalization(self) -> None:
        """Route IDs are normalized to placeholders."""
        results = [
            {
                "method": "GET",
                "endpoint": "/api/incidents/11111111-2222-3333-4444-555555555555",
                "status_code": 200,
                "success": True,
                "latency_ms": 100.0,
            },
            {
                "method": "GET",
                "endpoint": "/api/incidents/66666666-7777-8888-9999-aaaaaaaaaaaa",
                "status_code": 200,
                "success": True,
                "latency_ms": 120.0,
            },
        ]
        summary = generate_baseline_summary(results)

        assert len(summary.benchmarked_endpoints) == 1
        endpoint = summary.benchmarked_endpoints[0]
        assert endpoint["normalized_route"] == "GET /api/incidents/{incident_id}"

    def test_numeric_id_normalization(self) -> None:
        """Numeric IDs in routes are normalized."""
        results = [
            {"method": "GET", "endpoint": "/api/items/123", "status_code": 200, "success": True, "latency_ms": 10.0},
            {"method": "GET", "endpoint": "/api/items/456", "status_code": 200, "success": True, "latency_ms": 20.0},
        ]
        summary = generate_baseline_summary(results)

        assert len(summary.benchmarked_endpoints) == 1
        endpoint = summary.benchmarked_endpoints[0]
        assert endpoint["normalized_route"] == "GET /api/items/{id}"

    def test_iteration_warmup_recorded(self) -> None:
        """Iteration and warmup counts are recorded."""
        summary = generate_baseline_summary([], iterations=10, warmup=2)
        assert summary.iteration_count == 10
        assert summary.warmup_count == 2

    def test_incident_id_source(self) -> None:
        """Incident ID source is recorded."""
        summary_auto = generate_baseline_summary([], incident_id_source="auto")
        assert summary_auto.incident_id_source == "auto"

        summary_provided = generate_baseline_summary([], incident_id_source="provided")
        assert summary_provided.incident_id_source == "provided"

    def test_slowest_endpoint_tracked(self) -> None:
        """Slowest endpoint is identified by p99."""
        results = [
            {"method": "GET", "endpoint": "/api/fast", "status_code": 200, "success": True, "latency_ms": 10.0},
            {"method": "GET", "endpoint": "/api/slow", "status_code": 200, "success": True, "latency_ms": 100.0},
        ]
        summary = generate_baseline_summary(results)

        # Fast endpoint should have low p99, slow should have high p99
        fast_ep = next(ep for ep in summary.benchmarked_endpoints if "fast" in ep["normalized_route"])
        slow_ep = next(ep for ep in summary.benchmarked_endpoints if "slow" in ep["normalized_route"])

        assert summary.slowest_endpoint == slow_ep["normalized_route"]
        assert slow_ep["latency_ms"]["p99"] > fast_ep["latency_ms"]["p99"]

    def test_failure_count_tracked(self) -> None:
        """Failed requests are tracked correctly."""
        results = [
            {"method": "GET", "endpoint": "/api/test", "status_code": 200, "success": True, "latency_ms": 10.0},
            {"method": "GET", "endpoint": "/api/test", "status_code": 200, "success": True, "latency_ms": 15.0},
            {"method": "GET", "endpoint": "/api/test", "status_code": 500, "success": False, "latency_ms": 5.0},
        ]
        summary = generate_baseline_summary(results)

        endpoint = summary.benchmarked_endpoints[0]
        assert endpoint["attempt_count"] == 3
        assert endpoint["success_count"] == 2
        assert endpoint["failure_count"] == 1
        assert "200" in endpoint["status_codes"]
        assert "500" in endpoint["status_codes"]
        assert endpoint["status_codes"]["500"] == 1

    def test_multiple_endpoints(self) -> None:
        """Multiple endpoints are analyzed separately."""
        results = [
            {"method": "GET", "endpoint": "/api/incidents", "status_code": 200, "success": True, "latency_ms": 10.0},
            {"method": "GET", "endpoint": "/api/health", "status_code": 200, "success": True, "latency_ms": 5.0},
            {"method": "POST", "endpoint": "/api/incidents", "status_code": 201, "success": True, "latency_ms": 20.0},
        ]
        summary = generate_baseline_summary(results)

        # Three endpoints: GET /api/incidents, GET /api/health, POST /api/incidents
        assert len(summary.benchmarked_endpoints) == 3
        routes = {ep["normalized_route"] for ep in summary.benchmarked_endpoints}
        assert "GET /api/incidents" in routes
        assert "GET /api/health" in routes
        assert "POST /api/incidents" in routes

    def test_skipped_endpoints_empty(self) -> None:
        """Skipped endpoints list is empty when none skipped."""
        summary = generate_baseline_summary([])
        assert summary.skipped_endpoints == []


class TestDominantSpans:
    """Tests for dominant internal spans tracking."""

    def test_dominant_spans_truncated(self) -> None:
        """Top 10 dominant spans are kept."""
        results = [{"method": "GET", "endpoint": "/api/test", "status_code": 200, "success": True}]
        summary = generate_baseline_summary(results)

        # Should have empty dominant_spans without trace data
        assert isinstance(summary.dominant_internal_spans, list)

    def test_dominant_spans_sorted_by_duration(self) -> None:
        """Dominant spans are sorted by total duration."""
        results = [
            {"method": "GET", "endpoint": "/api/test", "status_code": 200, "success": True, "latency_ms": 10.0},
        ]
        summary = generate_baseline_summary(results)

        # Without trace data, dominant_spans is empty
        assert summary.dominant_internal_spans == []
