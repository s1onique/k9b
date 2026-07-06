"""Unit tests for perf_baseline_spans module.

Tests cover:
1. HTTP/internal span identification
2. Trace ID extraction
3. Trace grouping by trace ID
4. Span duration handling
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from perf_baseline_spans import (
    extract_trace_id,
    group_spans_by_trace,
    is_http_span,
    is_internal_span,
)


class TestSpanIdentification:
    """Tests for HTTP and internal span identification."""

    def test_http_span_with_method_attribute(self) -> None:
        """HTTP spans are identified by k9b.api.method attribute."""
        http_span = {"k9b.api.method": "GET", "k9b.api.route": "/api/incidents"}
        assert is_http_span("GET /api/incidents", http_span) is True

    def test_http_span_with_route_attribute(self) -> None:
        """HTTP spans are identified by k9b.api.route attribute."""
        http_span = {"k9b.api.route": "/api/test"}
        assert is_http_span("some name", http_span) is True

    def test_http_span_not_internal(self) -> None:
        """HTTP spans are not identified as internal."""
        internal_span = {"k9b.operation": "list"}
        assert is_http_span("k9b.incident_store.list", internal_span) is False

    def test_internal_span_identified(self) -> None:
        """Internal spans are identified by k9b. prefix but not k9b.api."""
        assert is_internal_span("k9b.incident_store.list") is True
        assert is_internal_span("k9b.artifact.scan") is True
        assert is_internal_span("k9b.api.GET") is False  # API spans are not internal
        assert is_internal_span("unrelated.span") is False


class TestTraceIdExtraction:
    """Tests for trace ID extraction."""

    def test_trace_id_direct(self) -> None:
        """Trace ID is extracted from top-level field."""
        span = {"trace_id": "abc123"}
        assert extract_trace_id(span) == "abc123"

    def test_trace_id_from_context(self) -> None:
        """Trace ID is extracted from context field."""
        span = {"context": {"trace_id": "abc123"}}
        assert extract_trace_id(span) == "abc123"

    def test_trace_id_prefers_direct(self) -> None:
        """Top-level trace_id takes precedence over context."""
        span = {"trace_id": "direct", "context": {"trace_id": "from_context"}}
        assert extract_trace_id(span) == "direct"

    def test_no_trace_id_returns_none(self) -> None:
        """Missing trace ID returns None."""
        span = {"name": "test"}
        assert extract_trace_id(span) is None

    def test_empty_trace_id_returns_none(self) -> None:
        """Empty trace ID returns None."""
        span = {"trace_id": ""}
        assert extract_trace_id(span) is None


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


class TestEdgeCases:
    """Tests for edge case handling."""

    def test_nested_spans_in_object(self) -> None:
        """Spans nested in 'spans' field are extracted."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "spans": [
                    {"name": "test", "trace_id": "t1", "span_id": "s1"}
                ]
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert "t1" in result
        finally:
            path.unlink()

    def test_invalid_json_skipped(self) -> None:
        """Invalid JSON lines are skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "valid", "trace_id": "t1"}\n')
            f.write("not valid json\n")
            f.write('{"name": "also valid", "trace_id": "t2"}\n')
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            assert "t1" in result
            assert "t2" in result
        finally:
            path.unlink()

    def test_sanitize_removes_sensitive_keys(self) -> None:
        """Internal spans have sensitive attributes removed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({
                "name": "k9b.internal.op",
                "trace_id": "trace1",
                "span_id": "s1",
                "attributes": {
                    "k9b.operation": "list",
                    "k9b.item.kind": "incident",
                    "secret_key": "should_be_removed",
                    "password": "should_be_removed",
                }
            }) + "\n")
            f.flush()
            path = Path(f.name)

        try:
            result = group_spans_by_trace(path)
            internal_span = result["trace1"].internal_spans[0]
            assert "k9b.operation" in internal_span["attributes"]
            assert "k9b.item.kind" in internal_span["attributes"]
            assert "secret_key" not in internal_span["attributes"]
            assert "password" not in internal_span["attributes"]
        finally:
            path.unlink()
