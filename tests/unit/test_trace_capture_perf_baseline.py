"""Unit tests for trace-capture perf_baseline module.

Tests cover:
1. Percentile calculation
2. Status code histogram
3. Baseline summary generation
4. Skipped endpoint handling
5. Trace grouping by trace ID
6. HTTP/internal span counting
7. Privacy check failure on raw incident ID
8. Privacy check failure on payload marker
9. No-duration span records handling
"""

from __future__ import annotations

import json

# Import the module under test
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from perf_baseline import (
    SCHEMA_VERSION,
    BaselineSummary,
    build_status_histogram,
    check_artifact_payload,
    check_raw_incident_id,
    compute_latency_stats,
    generate_baseline_summary,
    group_spans_by_trace,
)

# =============================================================================
# Test: Percentile Calculation
# =============================================================================


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


# =============================================================================
# Test: Status Code Histogram
# =============================================================================


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


# =============================================================================
# Test: Privacy Checks
# =============================================================================


class TestPrivacyChecks:
    """Tests for privacy violation detection."""

    def test_no_incident_id(self) -> None:
        """Clean text with no incident IDs returns False."""
        text = "This is a normal span name without any IDs"
        assert check_raw_incident_id(text) is False

    def test_uuid_incident_id_detected(self) -> None:
        """Raw UUID incident ID is detected."""
        text = "k9b.incident_store.list 12345678-1234-1234-1234-123456789abc"
        assert check_raw_incident_id(text) is True

    def test_partial_uuid_not_detected(self) -> None:
        """Partial UUID is not flagged as incident ID."""
        text = "trace-abc123"
        assert check_raw_incident_id(text) is False

    def test_no_payload_marker(self) -> None:
        """Clean text with no payload markers returns False."""
        text = "This is normal span data without any sensitive markers"
        assert check_artifact_payload(text) is False

    def test_kubeconfig_detected(self) -> None:
        """'kubeconfig' payload marker is detected."""
        text = "context: kubeconfig section found"
        assert check_artifact_payload(text) is True

    def test_token_detected(self) -> None:
        """'token' payload marker is detected (case insensitive)."""
        text = "Authorization: Bearer token123"
        assert check_artifact_payload(text) is True

    def test_begin_private_key_detected(self) -> None:
        """'BEGIN_PRIVATE_KEY' marker is detected."""
        text = "BEGIN_PRIVATE_KEY marker found in data"
        assert check_artifact_payload(text) is True

    def test_secret_detected(self) -> None:
        """'secret' payload marker is detected."""
        text = "secret_key: my_secret_value"
        assert check_artifact_payload(text) is True


# =============================================================================
# Test: Trace Grouping
# =============================================================================


class TestTraceGrouping:
    """Tests for span grouping by trace ID."""

    def test_empty_file(self) -> None:
        """Empty JSONL file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert result == {}
        finally:
            path.unlink()

    def test_single_trace(self) -> None:
        """Single trace with multiple spans is grouped correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "GET /api/incidents",
                "trace_id": "abc123def456789012345678901234ab",
                "span_id": "span1",
                "attributes": {"k9b.api.method": "GET", "k9b.api.route": "/api/incidents"},
                "duration_ms": 25.0
            }) + "\n")
            f.write(json.dumps({
                "name": "k9b.incident_store.list",
                "trace_id": "abc123def456789012345678901234ab",
                "span_id": "span2",
                "attributes": {},
                "duration_ms": 15.5
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert "abc123def456789012345678901234ab" in result
            breakdown = result["abc123def456789012345678901234ab"]
            assert breakdown.span_count == 2
            assert breakdown.route == "/api/incidents"
            assert breakdown.http_span_duration_ms == 25.0
            assert breakdown.internal_span_duration_ms_total == 15.5
            assert len(breakdown.internal_spans) == 1
            assert breakdown.internal_spans[0]["name"] == "k9b.incident_store.list"
        finally:
            path.unlink()

    def test_multiple_traces(self) -> None:
        """Multiple traces are grouped into separate breakdowns."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "GET /api/incidents",
                "trace_id": "trace1",
                "span_id": "s1",
                "attributes": {"k9b.api.method": "GET", "k9b.api.route": "/api/incidents"}
            }) + "\n")
            f.write(json.dumps({
                "name": "GET /api/health/details",
                "trace_id": "trace2",
                "span_id": "s2",
                "attributes": {"k9b.api.method": "GET", "k9b.api.route": "/api/health/details"}
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert len(result) == 2
            assert "trace1" in result
            assert "trace2" in result
            assert result["trace1"].route == "/api/incidents"
            assert result["trace2"].route == "/api/health/details"
        finally:
            path.unlink()

    def test_span_without_trace_id_skipped(self) -> None:
        """Spans without trace_id are skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "GET /api/incidents",
                "span_id": "s1",
                "attributes": {"k9b.api.method": "GET", "k9b.api.route": "/api/incidents"}
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert result == {}
        finally:
            path.unlink()

    def test_duration_absent_handled(self) -> None:
        """Span records without duration_ms default to 0."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "k9b.internal.op",
                "trace_id": "trace1",
                "span_id": "s1",
                "attributes": {}
            }) + "\n")  # No duration_ms field
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert "trace1" in result
            breakdown = result["trace1"]
            assert breakdown.internal_span_duration_ms_total == 0.0
            assert breakdown.internal_spans[0]["duration_ms"] == 0.0
        finally:
            path.unlink()


# =============================================================================
# Test: Baseline Summary Generation
# =============================================================================


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


# =============================================================================
# Test: Skipped Endpoint Handling
# =============================================================================


class TestSkippedEndpointHandling:
    """Tests for skipped endpoint tracking."""

    def test_skipped_endpoints_in_summary(self) -> None:
        """Skipped endpoints are recorded in summary."""
        summary = BaselineSummary(
            benchmarked_endpoints=[],
            skipped_endpoints=["/api/runtime-status", "/api/fleet"],
        )
        assert len(summary.skipped_endpoints) == 2
        assert "/api/runtime-status" in summary.skipped_endpoints


# =============================================================================
# Test: HTTP/Internal Span Counting
# =============================================================================


class TestSpanCounting:
    """Tests for HTTP and internal span counting."""

    def test_http_span_identified(self) -> None:
        """HTTP spans are identified by k9b.api.method attribute."""
        from perf_baseline import is_http_span

        http_span = {"k9b.api.method": "GET", "k9b.api.route": "/api/incidents"}
        assert is_http_span("GET /api/incidents", http_span) is True

        internal_span = {"k9b.operation": "list"}
        assert is_http_span("k9b.incident_store.list", internal_span) is False

    def test_internal_span_identified(self) -> None:
        """Internal spans are identified by k9b. prefix but not k9b.api."""
        from perf_baseline import is_internal_span

        assert is_internal_span("k9b.incident_store.list") is True
        assert is_internal_span("k9b.artifact.scan") is True
        assert is_internal_span("k9b.api.GET") is False  # API spans are not internal
        assert is_internal_span("unrelated.span") is False


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge case handling."""

    def test_dominant_spans_truncated(self) -> None:
        """Top 10 dominant spans are kept."""
        results = [{"method": "GET", "endpoint": "/api/test", "status_code": 200, "success": True}]
        summary = generate_baseline_summary(results)

        # Should have empty dominant_spans without trace data
        assert isinstance(summary.dominant_internal_spans, list)

    def test_span_breakdown_with_no_duration(self) -> None:
        """Span breakdown handles missing duration honestly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "k9b.test.op",
                "trace_id": "trace1",
                "span_id": "s1",
                "attributes": {}
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            breakdowns = group_spans_by_trace(path)
            breakdown = breakdowns["trace1"]
            # Duration should default to 0 when absent
            assert breakdown.internal_span_duration_ms_total == 0.0
            assert breakdown.internal_spans[0]["duration_ms"] == 0.0
        finally:
            path.unlink()


# =============================================================================
# Test: Schema Version
# =============================================================================


class TestSchemaVersion:
    """Tests for schema version consistency."""

    def test_schema_version_format(self) -> None:
        """Schema version follows expected format."""
        assert SCHEMA_VERSION.startswith("k9b.")
        assert ".v" in SCHEMA_VERSION

    def test_summary_uses_schema_version(self) -> None:
        """BaselineSummary uses correct schema version."""
        summary = BaselineSummary()
        assert summary.schema_version == SCHEMA_VERSION

    def test_summary_to_dict_includes_schema(self) -> None:
        """to_dict includes schema_version."""
        summary = BaselineSummary()
        data = summary.to_dict()
        assert "schema_version" in data
        assert data["schema_version"] == SCHEMA_VERSION
