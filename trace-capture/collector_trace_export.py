"""Converter for Collector OTLP JSON output to span JSONL format.

This module converts Collector file exporter OTLP JSON traces into the
span JSONL format expected by trace-capture and verify_index_perf_proof.py.

Collector file exporter outputs OTLP JSON format (one JSON object per trace batch).
This converter extracts spans and writes them in the expected format:

    {"trace_id": "...", "span_id": "...", "name": "...", ...}

Usage:
    python collector_trace_export.py \
        --input collector-traces.jsonl \
        --output spans.jsonl

    # Or as a library:
    from collector_trace_export import convert_collector_output
    spans = convert_collector_output(Path("collector-traces.jsonl"))
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "k9b.collector_export.v1"

# =============================================================================
# Span Format Expected by trace-capture
# =============================================================================

# Minimum required fields for span JSONL:
# - trace_id: hex string (32 chars)
# - span_id: hex string (16 chars)
# - name: span name (e.g., "k9b.content_index.query")
# - attributes: dict of span attributes
# - duration_ms: optional, may be absent

EXPECTED_SPAN_FIELDS = {"trace_id", "span_id", "name", "attributes"}


def hex_to_hex16(hex_str: str) -> str:
    """Convert trace ID to span ID format (16 hex chars for span IDs)."""
    # Span IDs are 8 bytes (16 hex chars), trace IDs are 16 bytes (32 hex chars)
    if len(hex_str) >= 16:
        return hex_str[:16]
    return hex_str.zfill(16)


def hex_to_hex32(hex_str: str) -> str:
    """Normalize to 32-char trace ID format."""
    if len(hex_str) >= 32:
        return hex_str[:32]
    return hex_str.zfill(32)


def is_valid_hex_id(hex_str: str | None, expected_len: int = 32) -> bool:
    """Check if string is a valid hex ID."""
    if not hex_str:
        return False
    if len(hex_str) < expected_len:
        return False
    try:
        int(hex_str[:expected_len], 16)
        return True
    except ValueError:
        return False


def extract_spans_from_otlp_json(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract spans from OTLP JSON format.

    Collector file exporter outputs one of:
    1. OTLP JSON format: {"resourceSpans": [{"scopeSpans": [{"spans": [...]}]}]}
    2. Simple JSON format: {"spans": [...]} (direct span array)
    3. Single span: {"name": "...", "trace_id": "..."}

    Args:
        obj: Parsed JSON object from collector output

    Returns:
        List of extracted span dictionaries
    """
    spans: list[dict[str, Any]] = []

    # Format 1: OTLP JSON (resourceSpans -> scopeSpans -> spans)
    if "resourceSpans" in obj:
        for resource_span in obj.get("resourceSpans", []):
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    extracted = _convert_otlp_span(span)
                    if extracted:
                        spans.append(extracted)

    # Format 2: Direct spans array
    elif "spans" in obj:
        for span in obj.get("spans", []):
            extracted = _convert_otlp_span(span)
            if extracted:
                spans.append(extracted)

    # Format 3: Single span object
    elif "name" in obj and "trace_id" in obj:
        extracted = _convert_otlp_span(obj)
        if extracted:
            spans.append(extracted)

    return spans


def _convert_otlp_span(span: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single OTLP span to trace-capture format.

    Args:
        span: OTLP span dictionary

    Returns:
        Converted span dictionary or None if invalid
    """
    # Extract trace_id
    trace_id = span.get("traceId") or span.get("trace_id")
    if trace_id:
        trace_id = trace_id.lower()
        if not is_valid_hex_id(trace_id, 32):
            return None
        trace_id = hex_to_hex32(trace_id)
    else:
        return None

    # Extract span_id
    span_id = span.get("spanId") or span.get("span_id")
    if span_id:
        span_id = span_id.lower()
        if not is_valid_hex_id(span_id, 16):
            return None
        span_id = hex_to_hex16(span_id)
    else:
        return None

    # Extract name
    name = span.get("name", "")

    # Extract attributes
    attributes: dict[str, Any] = {}
    raw_attrs = span.get("attributes", [])
    if isinstance(raw_attrs, list):
        # OTLP format: [{"key": "...", "value": ...}]
        for attr in raw_attrs:
            if isinstance(attr, dict) and "key" in attr:
                key = attr["key"]
                value = attr.get("value", attr.get("stringValue", attr.get("intValue", None)))
                # Handle OTLP value types
                if isinstance(value, dict):
                    value = (
                        value.get("stringValue")
                        or value.get("intValue")
                        or value.get("doubleValue")
                        or value.get("boolValue")
                        or str(value)
                    )
                attributes[key] = value
    elif isinstance(raw_attrs, dict):
        # Already a dict
        attributes = raw_attrs

    # Extract duration (nanoseconds -> milliseconds)
    duration_ms: float | None = None
    raw_duration = span.get("durationNanoSeconds") or span.get("durationNano") or span.get("durationNanos")
    if raw_duration is None:
        raw_duration = span.get("durationMs") or span.get("duration")
    if raw_duration is not None:
        try:
            duration_ns = float(raw_duration)
            # Convert nanoseconds to milliseconds
            if duration_ns > 1e9:  # Likely in nanoseconds
                duration_ms = duration_ns / 1_000_000
            else:
                # Already in milliseconds
                duration_ms = duration_ns
        except (ValueError, TypeError):
            duration_ms = None

    # Extract parent span ID if present
    parent_span_id = span.get("parentSpanId") or span.get("parent_span_id")
    if parent_span_id:
        parent_span_id = parent_span_id.lower()
        if is_valid_hex_id(parent_span_id, 16):
            parent_span_id = hex_to_hex16(parent_span_id)
        else:
            parent_span_id = None

    # Build result
    result: dict[str, Any] = {
        "trace_id": trace_id,
        "span_id": span_id,
        "name": name,
        "attributes": attributes,
    }

    # Add optional fields only if they exist
    if parent_span_id:
        result["parent_span_id"] = parent_span_id
    if duration_ms is not None:
        result["duration_ms"] = round(duration_ms, 2)

    # OTLP standard fields
    if "kind" in span:
        result["kind"] = span["kind"]
    if "status" in span:
        result["status"] = span["status"]
    if "startTimeUnixNano" in span:
        result["start_time_unix_nano"] = span["startTimeUnixNano"]
    if "endTimeUnixNano" in span:
        result["end_time_unix_nano"] = span["endTimeUnixNano"]

    return result


def convert_collector_output(
    input_path: Path | str,
    output_path: Path | str | None = None,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Convert Collector OTLP JSON output to span JSONL format.

    Args:
        input_path: Path to Collector output file (JSON or JSONL)
        output_path: Optional path for output JSONL file
        verbose: Print progress information

    Returns:
        List of converted spans
    """
    input_path = Path(input_path)
    all_spans: list[dict[str, Any]] = []

    if not input_path.exists():
        if verbose:
            print(f"Input file not found: {input_path}", file=sys.stderr)
        return all_spans

    # Determine if input is JSONL (multiple JSON objects, one per line)
    # or a single JSON object/array
    with open(input_path) as f:
        content = f.read().strip()

    if not content:
        if verbose:
            print("Input file is empty", file=sys.stderr)
        return all_spans

    # Check if it's JSONL (first char is '{', but contains multiple lines)
    lines = content.split("\n")
    is_jsonl = len(lines) > 1 or not content.startswith("[")

    if is_jsonl:
        # JSONL format: one JSON object per line
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                spans = extract_spans_from_otlp_json(obj)
                all_spans.extend(spans)
                if verbose and spans:
                    print(f"Line {i + 1}: extracted {len(spans)} spans")
            except json.JSONDecodeError as e:
                if verbose:
                    print(f"Line {i + 1}: JSON decode error: {e}", file=sys.stderr)
    else:
        # Single JSON object or array
        try:
            obj = json.loads(content)
            if isinstance(obj, list):
                # Array of spans or trace objects
                for item in obj:
                    if isinstance(item, dict):
                        spans = extract_spans_from_otlp_json(item)
                        all_spans.extend(spans)
            else:
                # Single object
                spans = extract_spans_from_otlp_json(obj)
                all_spans.extend(spans)
        except json.JSONDecodeError as e:
            if verbose:
                print(f"JSON decode error: {e}", file=sys.stderr)

    # Write output if path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for span in all_spans:
                f.write(json.dumps(span, separators=(",", ":")) + "\n")
        if verbose:
            print(f"Wrote {len(all_spans)} spans to {output_path}")

    return all_spans


def get_span_counts(spans: list[dict[str, Any]]) -> dict[str, int]:
    """Count spans by various categories.

    Args:
        spans: List of span dictionaries

    Returns:
        Dictionary with span counts by category
    """
    counts: dict[str, int] = {
        "total": len(spans),
        "trace_count": len({s.get("trace_id") for s in spans if s.get("trace_id")}),
        "with_duration": sum(1 for s in spans if s.get("duration_ms") is not None),
        "with_parent": sum(1 for s in spans if s.get("parent_span_id") is not None),
    }

    # Count by prefix
    prefix_counts: dict[str, int] = {}
    for span in spans:
        name = span.get("name", "")
        for prefix in ["k9b.content_index", "k9b.api", "k9b.incident", "k9b.health"]:
            if name.startswith(prefix):
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    # Always include all prefixes, even if count is 0
    for prefix in ["k9b.content_index", "k9b.api", "k9b.incident", "k9b.health"]:
        counts[f"prefix_{prefix}"] = prefix_counts.get(prefix, 0)

    return counts


def print_summary(spans: list[dict[str, Any]], verbose: bool = False) -> None:
    """Print summary of converted spans.

    Args:
        spans: List of converted spans
        verbose: Print detailed information
    """
    counts = get_span_counts(spans)

    print(f"Converted {counts['total']} spans from {counts['trace_count']} traces")
    print(f"  With duration: {counts['with_duration']}")
    print(f"  With parent span: {counts['with_parent']}")

    if verbose:
        # Print prefix breakdown
        print("\nSpan name prefixes:")
        for key, value in sorted(counts.items()):
            if key.startswith("prefix_"):
                print(f"  {key[7:]}: {value}")


# =============================================================================
# CLI Interface
# =============================================================================


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert Collector OTLP JSON to span JSONL format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert collector output to spans:
  python collector_trace_export.py --input collector-traces.json --output spans.jsonl

  # Use with verbose output:
  python collector_trace_export.py -i collector-traces.json -o spans.jsonl -v

  # Read from stdin (JSONL):
  cat collector-output.jsonl | python collector_trace_export.py -o spans.jsonl
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Input file from Collector (JSON or JSONL)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Output JSONL file for converted spans",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Convert
    print(f"Converting {args.input} -> {args.output}")
    spans = convert_collector_output(
        args.input,
        args.output,
        verbose=args.verbose,
    )

    # Print summary
    print_summary(spans, verbose=args.verbose)

    return 0 if spans else 1


if __name__ == "__main__":
    sys.exit(main())
