"""Unit tests for collector_trace_export module.

Tests the conversion of Collector OTLP JSON output to span JSONL format.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add trace-capture to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from collector_trace_export import (
    SCHEMA_VERSION,
    convert_collector_output,
    extract_spans_from_otlp_json,
    get_span_counts,
    hex_to_hex16,
    hex_to_hex32,
    is_valid_hex_id,
)

# =============================================================================
# Test Data Fixtures
# =============================================================================

SAMPLE_TRACE_ID = "d2e2f68762c40b02a72b6a97dec0666c"
SAMPLE_SPAN_ID = "8abd14e03c38145d"
SAMPLE_PARENT_SPAN_ID = "8abd14e03c38145e"


def create_otlp_span(
    trace_id: str = SAMPLE_TRACE_ID,
    span_id: str = SAMPLE_SPAN_ID,
    name: str = "k9b.content_index.query",
    parent_span_id: str | None = SAMPLE_PARENT_SPAN_ID,
    duration_ns: int = 1_500_000,
    attributes: list[dict] | None = None,
) -> dict:
    """Create a sample OTLP span in the standard format."""
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 1,
        "startTimeUnixNano": "1704067200000000000",
        "endTimeUnixNano": "1704067200015000000",
        "attributes": attributes or [
            {"key": "k9b.api.method", "value": {"stringValue": "GET"}},
            {"key": "k9b.api.route", "value": {"stringValue": "/api/incidents"}},
        ],
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    if duration_ns:
        span["durationNanoSeconds"] = str(duration_ns)
    return span


def create_otlp_json_format(spans: list[dict]) -> dict:
    """Create OTLP JSON format with resourceSpans wrapper."""
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {"spans": spans}
                ]
            }
        ]
    }


def create_simple_spans_format(spans: list[dict]) -> dict:
    """Create simple JSON format with direct spans array."""
    return {"spans": spans}


def create_single_span_format(span: dict) -> dict:
    """Create single span JSON format."""
    return {
        "trace_id": span["traceId"],
        "span_id": span["spanId"],
        "name": span["name"],
        "attributes": {},
    }


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHexConversion:
    """Tests for hex ID conversion utilities."""

    def test_hex_to_hex16(self):
        """Test span ID conversion to 16-char format."""
        # Already correct length
        assert hex_to_hex16("8abd14e03c38145d") == "8abd14e03c38145d"
        # Longer than 16 chars - should truncate
        assert hex_to_hex16("00000000000000008abd14e03c38145d") == "0000000000000000"
        # Shorter than 16 chars - should pad with zeros on the left
        assert hex_to_hex16("8abd14e03c381") == "0008abd14e03c381"

    def test_hex_to_hex32(self):
        """Test trace ID conversion to 32-char format."""
        # Already correct length
        assert hex_to_hex32("d2e2f68762c40b02a72b6a97dec0666c") == "d2e2f68762c40b02a72b6a97dec0666c"
        # Longer than 32 chars - should truncate
        assert hex_to_hex32("d2e2f68762c40b02a72b6a97dec0666cd2e2f68762c40b02a72b6a97dec0666c") == "d2e2f68762c40b02a72b6a97dec0666c"
        # Shorter than 32 chars - should pad with zeros on the left
        assert hex_to_hex32("d2e2f68762c40b02a72b6a97dec0") == "0000d2e2f68762c40b02a72b6a97dec0"

    def test_is_valid_hex_id(self):
        """Test hex ID validation."""
        # Valid
        assert is_valid_hex_id("d2e2f68762c40b02a72b6a97dec0666c", 32)
        assert is_valid_hex_id("8abd14e03c38145d", 16)
        # Invalid
        assert not is_valid_hex_id(None, 32)
        assert not is_valid_hex_id("", 32)
        assert not is_valid_hex_id("not-hex", 32)
        assert not is_valid_hex_id("abc", 16)  # Too short


# =============================================================================
# Test OTLP Span Extraction
# =============================================================================

class TestExtractSpansFromOtlpJson:
    """Tests for span extraction from OTLP JSON formats."""

    def test_extract_from_otlp_json_format(self):
        """Test extraction from standard OTLP resourceSpans format."""
        spans = [
            create_otlp_span(name="GET /api/incidents"),
            create_otlp_span(name="k9b.content_index.query"),
        ]
        otlp_json = create_otlp_json_format(spans)

        extracted = extract_spans_from_otlp_json(otlp_json)

        assert len(extracted) == 2
        assert extracted[0]["name"] == "GET /api/incidents"
        assert extracted[1]["name"] == "k9b.content_index.query"
        # Verify trace_id normalization
        assert len(extracted[0]["trace_id"]) == 32
        assert len(extracted[1]["span_id"]) == 16

    def test_extract_from_simple_spans_format(self):
        """Test extraction from simple spans array format."""
        spans = [
            create_otlp_span(name="GET /api/health"),
        ]
        simple_json = create_simple_spans_format(spans)

        extracted = extract_spans_from_otlp_json(simple_json)

        assert len(extracted) == 1
        assert extracted[0]["name"] == "GET /api/health"

    def test_extract_from_single_span_format(self):
        """Test extraction from single span format."""
        span = create_otlp_span(name="k9b.incident_store.list")
        single_json = create_single_span_format(span)

        extracted = extract_spans_from_otlp_json(single_json)

        assert len(extracted) == 1

    def test_extract_with_attributes_conversion(self):
        """Test that OTLP attribute format is converted correctly."""
        span = create_otlp_span(
            name="GET /api/incidents",
            attributes=[
                {"key": "http.request.method", "value": {"stringValue": "GET"}},
                {"key": "http.route", "value": {"stringValue": "/api/incidents"}},
                {"key": "k9b.result.count", "value": {"intValue": 5}},
            ]
        )
        otlp_json = create_otlp_json_format([span])

        extracted = extract_spans_from_otlp_json(otlp_json)

        assert len(extracted) == 1
        attrs = extracted[0]["attributes"]
        assert attrs["http.request.method"] == "GET"
        assert attrs["http.route"] == "/api/incidents"
        assert attrs["k9b.result.count"] == 5

    def test_extract_preserves_duration(self):
        """Test that duration is converted from nanoseconds to milliseconds."""
        # Use a large value (>1e9) to ensure it's treated as nanoseconds
        span = create_otlp_span(duration_ns=1_500_000_000)  # 1.5 seconds in ns
        otlp_json = create_otlp_json_format([span])

        extracted = extract_spans_from_otlp_json(otlp_json)

        assert len(extracted) == 1
        assert "duration_ms" in extracted[0]
        assert extracted[0]["duration_ms"] == pytest.approx(1500.0, rel=0.1)

    def test_extract_handles_missing_duration(self):
        """Test that missing duration results in None."""
        # Create span without duration_ns parameter (default 0 which is falsy)
        span = create_otlp_span(duration_ns=1_000_000)  # Add duration first
        del span["durationNanoSeconds"]  # Then remove it to test missing case
        otlp_json = create_otlp_json_format([span])

        extracted = extract_spans_from_otlp_json(otlp_json)

        assert len(extracted) == 1
        assert "duration_ms" not in extracted[0]

    def test_extract_content_index_spans(self):
        """Test extraction of content index span names."""
        spans = [
            create_otlp_span(name="k9b.content_index.query"),
            create_otlp_span(name="k9b.content_index.open"),
            create_otlp_span(name="k9b.content_index.validate"),
            create_otlp_span(name="k9b.content_index.fallback"),
            create_otlp_span(name="k9b.api.incidents"),
        ]
        otlp_json = create_otlp_json_format(spans)

        extracted = extract_spans_from_otlp_json(otlp_json)

        names = {s["name"] for s in extracted}
        assert "k9b.content_index.query" in names
        assert "k9b.content_index.open" in names
        assert "k9b.content_index.validate" in names
        assert "k9b.content_index.fallback" in names
        assert "k9b.api.incidents" in names

    def test_extract_rejects_invalid_trace_id(self):
        """Test that spans with invalid trace IDs are rejected."""
        span = create_otlp_span(trace_id="invalid")
        otlp_json = create_otlp_json_format([span])

        extracted = extract_spans_from_otlp_json(otlp_json)

        assert len(extracted) == 0


# =============================================================================
# Test Converter
# =============================================================================

class TestConvertCollectorOutput:
    """Tests for the main convert function."""

    def test_convert_jsonl_input(self, tmp_path: Path):
        """Test conversion of JSONL input."""
        input_file = tmp_path / "input.jsonl"
        output_file = tmp_path / "output.jsonl"

        spans = [
            create_otlp_span(name="GET /api/incidents"),
            create_otlp_span(name="k9b.content_index.query"),
        ]
        otlp_json = create_otlp_json_format(spans)

        # Write as JSONL (one JSON object per line)
        with open(input_file, "w") as f:
            f.write(json.dumps(otlp_json) + "\n")
            f.write(json.dumps(otlp_json) + "\n")

        result = convert_collector_output(input_file, output_file)

        assert len(result) == 4  # 2 spans * 2 lines
        assert output_file.exists()

        # Check output format
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) == 4
            for line in lines:
                obj = json.loads(line)
                assert "trace_id" in obj
                assert "span_id" in obj
                assert "name" in obj

    def test_convert_single_json_input(self, tmp_path: Path):
        """Test conversion of single JSON object."""
        input_file = tmp_path / "input.json"
        output_file = tmp_path / "output.jsonl"

        spans = [create_otlp_span(name="GET /api/health")]
        otlp_json = create_otlp_json_format(spans)

        with open(input_file, "w") as f:
            json.dump(otlp_json, f)

        result = convert_collector_output(input_file, output_file)

        assert len(result) == 1
        assert result[0]["name"] == "GET /api/health"

    def test_convert_empty_file(self, tmp_path: Path):
        """Test conversion of empty file."""
        input_file = tmp_path / "empty.jsonl"
        output_file = tmp_path / "output.jsonl"
        input_file.write_text("")

        result = convert_collector_output(input_file, output_file)

        assert len(result) == 0

    def test_convert_nonexistent_file(self):
        """Test conversion of nonexistent file."""
        result = convert_collector_output("/nonexistent/path.jsonl")

        assert len(result) == 0

    def test_convert_verbose_output(self, tmp_path: Path, capsys):
        """Test verbose output."""
        input_file = tmp_path / "input.jsonl"
        output_file = tmp_path / "output.jsonl"

        spans = [create_otlp_span(name="GET /api/incidents")]
        otlp_json = create_otlp_json_format(spans)
        with open(input_file, "w") as f:
            f.write(json.dumps(otlp_json) + "\n")

        result = convert_collector_output(input_file, output_file, verbose=True)

        captured = capsys.readouterr()
        assert "Line 1: extracted 1 spans" in captured.out
        assert f"Wrote {len(result)} spans to" in captured.out


# =============================================================================
# Test Span Counts
# =============================================================================

class TestGetSpanCounts:
    """Tests for span counting functionality."""

    def test_count_total_and_traces(self):
        """Test total and unique trace counting."""
        spans = [
            {"trace_id": "trace1", "name": "span1"},
            {"trace_id": "trace1", "name": "span2"},
            {"trace_id": "trace2", "name": "span3"},
        ]

        counts = get_span_counts(spans)

        assert counts["total"] == 3
        assert counts["trace_count"] == 2

    def test_count_with_duration(self):
        """Test duration count."""
        spans = [
            {"trace_id": "trace1", "name": "span1", "duration_ms": 1.5},
            {"trace_id": "trace2", "name": "span2"},  # No duration
            {"trace_id": "trace3", "name": "span3", "duration_ms": 2.0},
        ]

        counts = get_span_counts(spans)

        assert counts["with_duration"] == 2

    def test_count_with_parent(self):
        """Test parent span count."""
        spans = [
            {"trace_id": "trace1", "name": "span1", "parent_span_id": "parent1"},
            {"trace_id": "trace2", "name": "span2"},  # No parent
            {"trace_id": "trace3", "name": "span3", "parent_span_id": "parent3"},
        ]

        counts = get_span_counts(spans)

        assert counts["with_parent"] == 2

    def test_count_by_prefix(self):
        """Test prefix-based counting."""
        spans = [
            {"trace_id": "trace1", "name": "k9b.content_index.query"},
            {"trace_id": "trace2", "name": "k9b.content_index.open"},
            {"trace_id": "trace3", "name": "k9b.api.incidents"},
            {"trace_id": "trace4", "name": "GET /api/health"},
            {"trace_id": "trace5", "name": "k9b.incident_store.list"},
        ]

        counts = get_span_counts(spans)

        assert counts["prefix_k9b.content_index"] == 2
        assert counts["prefix_k9b.api"] == 1
        assert counts["prefix_k9b.incident"] == 1
        assert counts["prefix_k9b.health"] == 0


# =============================================================================
# Test Schema Version
# =============================================================================

class TestSchemaVersion:
    """Tests for schema version constant."""

    def test_schema_version_format(self):
        """Test that schema version follows expected format."""
        assert SCHEMA_VERSION.startswith("k9b.")
        assert SCHEMA_VERSION.endswith(".v1")
