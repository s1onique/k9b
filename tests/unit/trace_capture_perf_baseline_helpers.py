"""Test helpers for trace-capture perf_baseline module.

This module contains:
- Fake trace generators
- Fake span builders
- Sample endpoints
- Temp artifact builders
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def make_fake_span(
    name: str,
    trace_id: str = "trace1",
    span_id: str = "span1",
    duration_ms: float = 10.0,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a fake span for testing.

    Args:
        name: Span name
        trace_id: Trace ID
        span_id: Span ID
        duration_ms: Duration in milliseconds
        attributes: Additional attributes

    Returns:
        Span dictionary
    """
    span: dict[str, Any] = {
        "name": name,
        "trace_id": trace_id,
        "span_id": span_id,
        "duration_ms": duration_ms,
    }
    if attributes:
        span["attributes"] = attributes
    return span


def make_fake_http_span(
    method: str,
    route: str,
    trace_id: str = "trace1",
    duration_ms: float = 25.0,
) -> dict[str, Any]:
    """Create a fake HTTP API span.

    Args:
        method: HTTP method
        route: API route
        trace_id: Trace ID
        duration_ms: Duration in milliseconds

    Returns:
        HTTP span dictionary
    """
    return make_fake_span(
        name=f"{method} {route}",
        trace_id=trace_id,
        attributes={
            "k9b.api.method": method,
            "k9b.api.route": route,
        },
        duration_ms=duration_ms,
    )


def make_fake_internal_span(
    operation: str,
    trace_id: str = "trace1",
    duration_ms: float = 15.0,
    item_kind: str | None = None,
) -> dict[str, Any]:
    """Create a fake internal span.

    Args:
        operation: Operation name (e.g., "k9b.incident_store.list")
        trace_id: Trace ID
        duration_ms: Duration in milliseconds
        item_kind: Optional item kind attribute

    Returns:
        Internal span dictionary
    """
    attrs: dict[str, Any] = {"k9b.operation": operation}
    if item_kind:
        attrs["k9b.item.kind"] = item_kind
    return make_fake_span(
        name=operation,
        trace_id=trace_id,
        attributes=attrs,
        duration_ms=duration_ms,
    )


def make_temp_jsonl(
    spans: list[dict[str, Any]],
) -> Path:
    """Create a temporary JSONL file with spans.

    Args:
        spans: List of span dictionaries

    Returns:
        Path to temporary file
    """
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for span in spans:
        f.write(json.dumps(span) + "\n")
    f.flush()
    return Path(f.name)


def make_sample_endpoints() -> list[dict[str, Any]]:
    """Create sample API endpoint results.

    Returns:
        List of sample endpoint results
    """
    return [
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
        {
            "method": "GET",
            "endpoint": "/api/health/details",
            "status_code": 200,
            "success": True,
            "latency_ms": 10.0,
            "trace_id": "trace3",
        },
    ]
