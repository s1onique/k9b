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

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Privacy patterns - reuse from trace_summary
RAW_INCIDENT_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

ARTIFACT_PAYLOAD_MARKERS = [
    "BEGIN_CREDENTIALS",
    "BEGIN_PRIVATE_KEY",
    "BEGIN_RSA_PRIVATE_KEY",
    "BEGIN_EC_PRIVATE_KEY",
    "BEGIN_OPENSSH_PRIVATE_KEY",
    "BEGIN_GPG_PRIVATE_KEY_BLOCK",
    "kubeconfig",
    "token",
    "bearer",
    "secret",
]

_ARTIFACT_PAYLOAD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in ARTIFACT_PAYLOAD_MARKERS
]

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "k9b.perf_baseline.v1"

# =============================================================================
# Latency Statistics
# =============================================================================


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


# =============================================================================
# Status Code Histogram
# =============================================================================


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


# =============================================================================
# Span Analysis
# =============================================================================


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


@dataclass
class SpanBreakdown:
    """Breakdown of spans for a trace."""

    trace_id: str
    route: str  # Normalized route name
    span_count: int = 0
    http_span_count: int = 0
    http_span_duration_ms: float = 0.0
    internal_span_duration_ms_total: float = 0.0
    internal_spans: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "route": self.route,
            "span_count": self.span_count,
            "http_span_count": self.http_span_count,
            "http_span_duration_ms": round(self.http_span_duration_ms, 2),
            "internal_span_duration_ms_total": round(self.internal_span_duration_ms_total, 2),
            "internal_spans": self.internal_spans,
        }


def group_spans_by_trace(
    trace_jsonl_path: Path,
) -> dict[str, SpanBreakdown]:
    """Group spans by trace ID and compute breakdown.

    Args:
        trace_jsonl_path: Path to JSONL trace file

    Returns:
        Dictionary mapping trace_id to SpanBreakdown
    """
    trace_spans: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trace_routes: dict[str, str] = {}

    spans = _parse_jsonl_traces(trace_jsonl_path)

    for span in spans:
        trace_id = extract_trace_id(span)
        if not trace_id:
            continue

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


# =============================================================================
# Endpoint Baseline
# =============================================================================


@dataclass
class EndpointBaseline:
    """Performance baseline for a single endpoint."""

    method: str
    route: str
    normalized_route: str  # e.g., "GET /api/incidents"
    attempt_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    status_codes: dict[str, int] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(
        default_factory=lambda: {
            "min": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0
        }
    )
    trace_ids: list[str] = field(default_factory=list)
    span_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "method": self.method,
            "route": self.route,
            "normalized_route": self.normalized_route,
            "attempt_count": self.attempt_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "status_codes": self.status_codes,
            "latency_ms": {k: round(v, 2) for k, v in self.latency_ms.items()},
            "trace_ids": self.trace_ids[:100],  # Bounded
            "span_breakdown": self.span_breakdown,
        }


# =============================================================================
# Baseline Summary
# =============================================================================


@dataclass
class BaselineSummary:
    """Summary of API performance baseline."""

    schema_version: str = SCHEMA_VERSION
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    benchmarked_endpoints: list[dict[str, Any]] = field(default_factory=list)
    skipped_endpoints: list[str] = field(default_factory=list)
    slowest_endpoint: str = ""
    dominant_internal_spans: list[dict[str, Any]] = field(default_factory=list)
    total_traces: int = 0
    total_spans: int = 0
    http_span_count: int = 0
    internal_span_count: int = 0
    iteration_count: int = 0
    warmup_count: int = 0
    incident_id_source: str = "auto"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "benchmarked_endpoints": self.benchmarked_endpoints,
            "skipped_endpoints": self.skipped_endpoints,
            "slowest_endpoint": self.slowest_endpoint,
            "dominant_internal_spans": self.dominant_internal_spans,
            "total_traces": self.total_traces,
            "total_spans": self.total_spans,
            "http_span_count": self.http_span_count,
            "internal_span_count": self.internal_span_count,
            "iteration_count": self.iteration_count,
            "warmup_count": self.warmup_count,
            "incident_id_source": self.incident_id_source,
        }


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


def _normalize_route(method: str, endpoint: str) -> str:
    """Normalize route by replacing IDs with template placeholders."""
    import re
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
# Privacy Checks
# =============================================================================


def check_raw_incident_id(text: str) -> bool:
    """Check if raw incident ID appears in text."""
    return bool(RAW_INCIDENT_ID_PATTERN.search(text))


def check_artifact_payload(text: str) -> bool:
    """Check if artifact payload markers appear in text."""
    for pattern in _ARTIFACT_PAYLOAD_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =============================================================================
# Artifact Writing
# =============================================================================


def write_baseline_artifacts(
    summary: BaselineSummary,
    spans_jsonl: list[dict[str, Any]],
    artifact_dir: Path,
) -> dict[str, Path]:
    """Write baseline artifacts to disk.

    Args:
        summary: Baseline summary
        spans_jsonl: List of span breakdown records
        artifact_dir: Directory to write to

    Returns:
        Dictionary mapping artifact name to path
    """
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    # Write main baseline
    baseline_path = artifact_dir / "backend-api-baseline.json"
    baseline_path.write_text(json.dumps(summary.to_dict(), indent=2))
    paths["baseline"] = baseline_path

    # Write summary
    summary_path = artifact_dir / "backend-api-baseline-summary.json"
    summary_data = {
        "schema_version": summary.schema_version,
        "generated_at": summary.generated_at,
        "total_traces": summary.total_traces,
        "total_spans": summary.total_spans,
        "http_span_count": summary.http_span_count,
        "internal_span_count": summary.internal_span_count,
        "slowest_endpoint": summary.slowest_endpoint,
        "iteration_count": summary.iteration_count,
        "warmup_count": summary.warmup_count,
        "endpoint_count": len(summary.benchmarked_endpoints),
    }
    summary_path.write_text(json.dumps(summary_data, indent=2))
    paths["summary"] = summary_path

    # Write trace IDs
    trace_ids_path = artifact_dir / "backend-api-baseline-trace-ids.txt"
    trace_ids = set()
    for endpoint in summary.benchmarked_endpoints:
        trace_ids.update(endpoint.get("trace_ids", []))
    trace_ids_path.write_text("\n".join(sorted(trace_ids)))
    paths["trace_ids"] = trace_ids_path

    # Write spans JSONL
    spans_path = artifact_dir / "backend-api-baseline-spans.jsonl"
    with open(spans_path, "w") as f:
        for span in spans_jsonl:
            f.write(json.dumps(span) + "\n")
    paths["spans"] = spans_path

    return paths
