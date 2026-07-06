"""Performance baseline module for k9b backend API benchmarking.

This module provides:
- Latency statistics (p50, p90, p95, p99, min, max)
- Span breakdown analysis
- Baseline summary generation
- Privacy-safe trace correlation

Usage:
    from perf_baseline import (
        compute_latency_stats,
        generate_baseline_summary,
        group_spans_by_trace,
    )

    stats = compute_latency_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    # stats = {'min': 10.0, 'p50': 30.0, 'p90': 50.0, 'p95': 50.0, 'p99': 50.0, 'max': 50.0}
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Re-export all public symbols from submodules for backward compatibility
from perf_baseline_artifacts import write_baseline_artifacts
from perf_baseline_contract import (
    SCHEMA_VERSION,
    BaselineSummary,
    EndpointBaseline,
    SpanBreakdown,
    check_artifact_payload,
    check_raw_incident_id,
)
from perf_baseline_spans import (
    extract_trace_id,
    group_spans_by_trace,
    is_http_span,
    is_internal_span,
)
from perf_baseline_stats import build_status_histogram, compute_latency_stats

__all__ = [
    # Schema
    "SCHEMA_VERSION",
    # Stats
    "compute_latency_stats",
    "build_status_histogram",
    # Spans
    "is_http_span",
    "is_internal_span",
    "extract_trace_id",
    "group_spans_by_trace",
    # Contract
    "BaselineSummary",
    "EndpointBaseline",
    "SpanBreakdown",
    "check_raw_incident_id",
    "check_artifact_payload",
    # Artifacts
    "write_baseline_artifacts",
    # High-level
    "generate_baseline_summary",
]


# =============================================================================
# Route Normalization (kept here as it's used by generate_baseline_summary)
# =============================================================================


def _normalize_route(method: str, endpoint: str) -> str:
    """Normalize route by replacing IDs with template placeholders."""
    route = endpoint
    # Replace UUIDs with {incident_id}
    route = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{incident_id}",
        route,
    )
    # Replace numeric IDs with {id}
    route = re.sub(r"/\d+(?=/|$)", "/{id}", route)
    return f"{method} {route}"


def _compute_span_breakdown(
    trace_ids: list[str],
    trace_jsonl_path: Path | None,
) -> dict[str, Any]:
    """Compute span breakdown for given trace IDs."""
    if not trace_jsonl_path or not trace_jsonl_path.exists():
        return {
            "http_span_count": 0,
            "internal_span_count": 0,
            "dominant_internal_spans": [],
        }

    breakdowns = group_spans_by_trace(trace_jsonl_path)

    # Filter to only include requested trace IDs
    relevant_breakdowns = {
        tid: bd for tid, bd in breakdowns.items() if tid in trace_ids
    }

    http_count = 0
    internal_count = 0
    span_totals: dict[str, float] = defaultdict(float)

    for bd in relevant_breakdowns.values():
        http_count += bd.http_span_count
        internal_count += len(bd.internal_spans)
        for span in bd.internal_spans:
            span_totals[span["name"]] += span.get("duration_ms", 0.0)

    dominant = sorted(
        [{"name": name, "total_duration_ms": round(dur, 2)} for name, dur in span_totals.items()],
        key=lambda x: x["total_duration_ms"],  # type: ignore[arg-type,return-value]
        reverse=True,
    )[:5]

    return {
        "http_span_count": http_count,
        "internal_span_count": internal_count,
        "dominant_internal_spans": dominant,
    }


# =============================================================================
# Baseline Summary Generation
# =============================================================================


def generate_baseline_summary(
    api_results: list[dict[str, Any]],
    trace_jsonl_path: Path | None = None,
    iterations: int = 1,
    warmup: int = 0,
    incident_id_source: str = "auto",
) -> BaselineSummary:
    """Generate performance baseline summary from API results.

    Args:
        api_results: List of API exercise results
        trace_jsonl_path: Optional path to trace JSONL file
        iterations: Number of benchmark iterations
        warmup: Number of warmup iterations
        incident_id_source: Source of incident ID (auto, provided, none)

    Returns:
        BaselineSummary with computed statistics
    """
    # Group results by normalized route
    route_results: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for result in api_results:
        method = result.get("method", "GET")
        endpoint = result.get("endpoint", "")
        # Normalize route template
        normalized = _normalize_route(method, endpoint)
        route_results[normalized].append(result)

    # Build endpoint baselines
    endpoints: list[dict[str, Any]] = []
    slowest_route = ""
    slowest_p99 = 0.0
    dominant_spans: dict[str, float] = defaultdict(float)

    for normalized_route, results in sorted(route_results.items()):
        latencies = [
            result.get("latency_ms", 0.0)
            for result in results
            if result.get("success", False)
        ]
        status_codes = [result.get("status_code") for result in results]
        trace_ids = [result.get("trace_id", "") for result in results if result.get("trace_id")]

        success_count = sum(1 for r in results if r.get("success", False))
        failure_count = len(results) - success_count

        endpoint_baseline = EndpointBaseline(
            method=results[0].get("method", "GET") if results else "GET",
            route=results[0].get("endpoint", "") if results else normalized_route,
            normalized_route=normalized_route,
            attempt_count=len(results),
            success_count=success_count,
            failure_count=failure_count,
            status_codes=build_status_histogram(status_codes),
            latency_ms=compute_latency_stats(latencies),
            trace_ids=[tid for tid in trace_ids if tid],
            span_breakdown=_compute_span_breakdown(trace_ids, trace_jsonl_path),
        )

        endpoints.append(endpoint_baseline.to_dict())

        # Track slowest endpoint
        if endpoint_baseline.latency_ms["p99"] > slowest_p99:
            slowest_p99 = endpoint_baseline.latency_ms["p99"]
            slowest_route = normalized_route

    # Aggregate span counts from traces
    total_traces = 0
    total_spans = 0
    http_span_count = 0
    internal_span_count = 0

    if trace_jsonl_path and trace_jsonl_path.exists():
        breakdowns = group_spans_by_trace(trace_jsonl_path)
        total_traces = len(breakdowns)

        for breakdown in breakdowns.values():
            total_spans += breakdown.span_count
            http_span_count += breakdown.http_span_count
            internal_span_count += len(breakdown.internal_spans)

            for internal_span in breakdown.internal_spans:
                name = internal_span.get("name", "")
                duration = internal_span.get("duration_ms", 0.0)
                dominant_spans[name] += duration

    # Top dominant internal spans
    top_spans = sorted(
        [{"name": name, "total_duration_ms": round(dur, 2)} for name, dur in dominant_spans.items()],
        key=lambda x: x["total_duration_ms"],  # type: ignore[arg-type,return-value]
        reverse=True,
    )[:10]

    return BaselineSummary(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        benchmarked_endpoints=endpoints,
        skipped_endpoints=[],
        slowest_endpoint=slowest_route,
        dominant_internal_spans=top_spans,
        total_traces=total_traces,
        total_spans=total_spans,
        http_span_count=http_span_count,
        internal_span_count=internal_span_count,
        iteration_count=iterations,
        warmup_count=warmup,
        incident_id_source=incident_id_source,
    )
