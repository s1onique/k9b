"""Contract definitions for perf_baseline module.

This module contains:
- Schema version constants
- Privacy pattern constants
- Dataclasses for baseline types
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "k9b.perf_baseline.v1"

# =============================================================================
# Privacy Patterns - reuse from trace_summary
# =============================================================================

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
# Span Analysis Types
# =============================================================================


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
