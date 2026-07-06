"""Span analysis for perf_baseline module.

This module contains:
- HTTP/internal span identification
- Trace ID extraction
- Span grouping by trace
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perf_baseline_contract import SpanBreakdown


def is_http_span(span_name: str, attributes: dict[str, Any]) -> bool:
    """Determine if a span is an HTTP request span."""
    if "k9b.api.method" in attributes or "http.request.method" in attributes:
        return True
    if attributes.get("k9b.api.route"):
        return True
    return False


def is_internal_span(span_name: str) -> bool:
    """Determine if a span is an internal operation span."""
    if span_name.startswith("k9b.api."):
        return False
    return span_name.startswith("k9b.")


def extract_trace_id(span: dict[str, Any]) -> str | None:
    """Extract trace ID from a span."""
    trace_id = span.get("trace_id") or span.get("context", {}).get("trace_id")
    return trace_id if trace_id else None


def group_spans_by_trace(
    trace_jsonl_path: Path,
) -> dict[str, SpanBreakdown]:
    """Group spans by trace ID and compute breakdown.

    Args:
        trace_jsonl_path: Path to JSONL trace file

    Returns:
        Dictionary mapping trace_id to SpanBreakdown
    """
    trace_spans: dict[str, list[dict[str, Any]]] = {}
    trace_routes: dict[str, str] = {}

    spans = _parse_jsonl_traces(trace_jsonl_path)

    for span in spans:
        trace_id = extract_trace_id(span)
        if not trace_id:
            continue

        if trace_id not in trace_spans:
            trace_spans[trace_id] = []
        trace_spans[trace_id].append(span)

        # Extract normalized route from HTTP spans
        if is_http_span(span.get("name", ""), span.get("attributes", {})):
            route = span.get("attributes", {}).get(
                "k9b.api.route", span.get("name", "")
            )
            if route and trace_id not in trace_routes:
                trace_routes[trace_id] = route

    # Build breakdown for each trace
    breakdowns: dict[str, SpanBreakdown] = {}
    for trace_id, spans in trace_spans.items():
        breakdown = SpanBreakdown(
            trace_id=trace_id,
            route=trace_routes.get(trace_id, "unknown"),
            span_count=len(spans),
        )

        for span in spans:
            name = span.get("name", "")
            attrs = span.get("attributes", {})
            duration_ms = span.get("duration_ms", 0.0)

            if is_http_span(name, attrs):
                breakdown.http_span_count += 1
                breakdown.http_span_duration_ms += duration_ms
            elif is_internal_span(name):
                breakdown.internal_span_duration_ms_total += duration_ms
                breakdown.internal_spans.append({
                    "name": name,
                    "duration_ms": round(duration_ms, 2),
                    "attributes": _sanitize_attributes(attrs),
                })

        breakdowns[trace_id] = breakdown

    return breakdowns


def _parse_jsonl_traces(path: Path) -> list[dict[str, Any]]:
    """Parse JSONL trace file."""
    spans: list[dict[str, Any]] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "spans" in obj:
                        spans.extend(obj["spans"])
                    elif "name" in obj:
                        spans.append(obj)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return spans


def _sanitize_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive values from span attributes.

    Only includes bounded low-cardinality attributes.
    """
    allowed_keys = {"k9b.operation", "k9b.item.kind", "k9b.source"}
    safe_attrs: dict[str, Any] = {}

    for key, value in attrs.items():
        if key in allowed_keys and isinstance(value, (str, int, float, bool)):
            safe_attrs[key] = value

    return safe_attrs
