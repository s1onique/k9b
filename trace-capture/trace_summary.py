"""Trace summary generation and validation for k9b backend trace capture lab.

This module provides:
- TraceSummary dataclass for structured trace evidence
- generate_trace_summary() to parse collector output into summary
- validate_trace_summary() to verify trace requirements
- Privacy checks for trace artifacts
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "k9b.trace_capture.v1"

# =============================================================================
# Privacy Marker Patterns
# =============================================================================

# Patterns that indicate raw sensitive data in trace artifacts
RAW_INCIDENT_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)

# Patterns for artifact payload markers (should not appear in trace artifacts)
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

# Compiled patterns for efficiency
_ARTIFACT_PAYLOAD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in ARTIFACT_PAYLOAD_MARKERS
]


# =============================================================================
# Trace Summary Dataclass
# =============================================================================


@dataclass(frozen=True)
class TraceSummary:
    """Summary of captured traces for verification.

    Attributes:
        schema_version: Schema version for compatibility
        generated_at: ISO-8601 timestamp when summary was generated
        otel_enabled: Whether OTel was enabled during capture
        service_name: Service name used for traces
        collector_received_traces: Whether collector received any traces
        trace_count: Number of unique traces captured
        span_count: Total number of spans captured
        http_span_count: Number of HTTP request spans
        internal_span_count: Number of internal operation spans
        trace_ids: List of captured trace IDs (bounded)
        span_names: Set of unique span names (bounded)
        normalized_route_names_present: Whether normalized routes are used
        http_and_internal_spans_share_trace_id: Whether spans share trace IDs
        raw_incident_ids_in_span_names: Whether raw IDs leaked into span names
        raw_artifact_payload_detected: Whether payload markers were detected
    """

    schema_version: str = SCHEMA_VERSION
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    otel_enabled: bool = False
    service_name: str = "k9b-backend"
    collector_received_traces: bool = False
    trace_count: int = 0
    span_count: int = 0
    http_span_count: int = 0
    internal_span_count: int = 0
    trace_ids: tuple[str, ...] = field(default_factory=tuple)
    span_names: frozenset[str] = field(default_factory=frozenset)
    normalized_route_names_present: bool = False
    http_and_internal_spans_share_trace_id: bool = False
    raw_incident_ids_in_span_names: bool = False
    raw_artifact_payload_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "otel_enabled": self.otel_enabled,
            "service_name": self.service_name,
            "collector_received_traces": self.collector_received_traces,
            "trace_count": self.trace_count,
            "span_count": self.span_count,
            "http_span_count": self.http_span_count,
            "internal_span_count": self.internal_span_count,
            "trace_ids": list(self.trace_ids),
            "span_names": sorted(self.span_names),
            "normalized_route_names_present": self.normalized_route_names_present,
            "http_and_internal_spans_share_trace_id": self.http_and_internal_spans_share_trace_id,
            "raw_incident_ids_in_span_names": self.raw_incident_ids_in_span_names,
            "raw_artifact_payload_detected": self.raw_artifact_payload_detected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceSummary:
        """Create from dictionary (e.g., loaded from JSON)."""
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            generated_at=data.get("generated_at", datetime.now(UTC).isoformat()),
            otel_enabled=data.get("otel_enabled", False),
            service_name=data.get("service_name", "k9b-backend"),
            collector_received_traces=data.get("collector_received_traces", False),
            trace_count=data.get("trace_count", 0),
            span_count=data.get("span_count", 0),
            http_span_count=data.get("http_span_count", 0),
            internal_span_count=data.get("internal_span_count", 0),
            trace_ids=tuple(data.get("trace_ids", [])),
            span_names=frozenset(data.get("span_names", [])),
            normalized_route_names_present=data.get("normalized_route_names_present", False),
            http_and_internal_spans_share_trace_id=data.get(
                "http_and_internal_spans_share_trace_id", False
            ),
            raw_incident_ids_in_span_names=data.get("raw_incident_ids_in_span_names", False),
            raw_artifact_payload_detected=data.get("raw_artifact_payload_detected", False),
        )


# =============================================================================
# Span Classification
# =============================================================================


def is_http_span(span_name: str, attributes: dict[str, Any]) -> bool:
    """Determine if a span is an HTTP request span.

    HTTP spans typically have:
    - k9b.api.method attribute
    - k9b.api.route attribute
    - http.request.method attribute

    Args:
        span_name: The span name
        attributes: Span attributes

    Returns:
        True if this is an HTTP request span
    """
    if "k9b.api.method" in attributes or "http.request.method" in attributes:
        return True
    if attributes.get("k9b.api.route"):
        return True
    return False


def is_internal_span(span_name: str) -> bool:
    """Determine if a span is an internal operation span.

    Internal spans have names starting with 'k9b.' but NOT 'k9b.api.'
    Examples:
    - k9b.incident_store.list
    - k9b.artifact.scan
    - k9b.review_packet.load

    Args:
        span_name: The span name

    Returns:
        True if this is an internal operation span
    """
    if span_name.startswith("k9b.api."):
        return False
    return span_name.startswith("k9b.")


def extract_trace_id(span: dict[str, Any]) -> str | None:
    """Extract trace ID from a span.

    Args:
        span: Span dictionary

    Returns:
        Trace ID string or None if not found
    """
    trace_id = span.get("trace_id") or span.get("context", {}).get("trace_id")
    return trace_id if trace_id else None


def check_raw_incident_id_in_span(span_name: str, attributes: dict[str, Any]) -> bool:
    """Check if raw incident ID appears in span name or attributes.

    Args:
        span_name: The span name
        attributes: Span attributes

    Returns:
        True if raw incident ID is detected
    """
    # Check span name
    if RAW_INCIDENT_ID_PATTERN.search(span_name):
        return True

    # Check attributes (string values only)
    for key, value in attributes.items():
        if isinstance(value, str) and RAW_INCIDENT_ID_PATTERN.search(value):
            return True

    return False


def check_artifact_payload_in_text(text: str) -> bool:
    """Check if artifact payload markers appear in text.

    Args:
        text: Text to check

    Returns:
        True if payload marker is detected
    """
    for pattern in _ARTIFACT_PAYLOAD_PATTERNS:
        if pattern.search(text):
            return True
    return False


# =============================================================================
# Trace Summary Generation
# =============================================================================


def generate_trace_summary(
    collector_output_path: Path | str | None = None,
    trace_json_path: Path | str | None = None,
    otel_enabled: bool = True,
    service_name: str = "k9b-backend",
) -> TraceSummary:
    """Generate trace summary from collector output files.

    Parses trace artifacts and produces a structured summary with
    privacy checks and span classification.

    Args:
        collector_output_path: Path to collector debug output log
        trace_json_path: Path to JSONL trace file from file exporter
        otel_enabled: Whether OTel was enabled during capture
        service_name: Service name from environment

    Returns:
        TraceSummary with parsed/counted trace data
    """
    trace_ids: list[str] = []
    span_names: set[str] = set()
    http_span_count = 0
    internal_span_count = 0
    raw_id_in_spans = False
    payload_in_text = False

    # Parse JSONL trace file if available
    if trace_json_path:
        trace_json_path = Path(trace_json_path)
        if trace_json_path.exists():
            parsed_spans = _parse_jsonl_traces(trace_json_path)
            for span in parsed_spans:
                trace_id = extract_trace_id(span)
                if trace_id and trace_id not in trace_ids:
                    trace_ids.append(trace_id)

                span_name = span.get("name", "")
                attributes = span.get("attributes", {})

                span_names.add(span_name)

                if is_http_span(span_name, attributes):
                    http_span_count += 1
                elif is_internal_span(span_name):
                    internal_span_count += 1

                if check_raw_incident_id_in_span(span_name, attributes):
                    raw_id_in_spans = True

                # Check attributes for payload markers
                for val in attributes.values():
                    if isinstance(val, str) and check_artifact_payload_in_text(val):
                        payload_in_text = True
                        break

    # Also check collector output log for raw incident IDs
    if collector_output_path:
        collector_output_path = Path(collector_output_path)
        if collector_output_path.exists():
            content = collector_output_path.read_text(errors="replace")
            if check_artifact_payload_in_text(content):
                payload_in_text = True

    # Check if HTTP and internal spans share trace IDs
    http_and_internal_share_trace = False
    if trace_json_path:
        trace_json_path = Path(trace_json_path)
        if trace_json_path.exists():
            http_and_internal_share_trace = _check_http_internal_trace_sharing(
                Path(trace_json_path)
            )

    # Normalize trace IDs (bounded to 100)
    bounded_trace_ids = tuple(trace_ids[:100])

    return TraceSummary(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        otel_enabled=otel_enabled,
        service_name=service_name,
        collector_received_traces=len(trace_ids) > 0 or http_span_count > 0 or internal_span_count > 0,
        trace_count=len(set(trace_ids)),
        span_count=len(span_names) if span_names else (http_span_count + internal_span_count),
        http_span_count=http_span_count,
        internal_span_count=internal_span_count,
        trace_ids=bounded_trace_ids,
        span_names=frozenset(list(span_names)[:100]),
        normalized_route_names_present=_has_normalized_routes(span_names),
        http_and_internal_spans_share_trace_id=http_and_internal_share_trace,
        raw_incident_ids_in_span_names=raw_id_in_spans,
        raw_artifact_payload_detected=payload_in_text,
    )


def _parse_jsonl_traces(path: Path) -> list[dict[str, Any]]:
    """Parse JSONL trace file.

    Args:
        path: Path to JSONL file

    Returns:
        List of parsed span dictionaries
    """
    spans: list[dict[str, Any]] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # Handle both single spans and trace wrappers
                    if "spans" in obj:
                        spans.extend(obj["spans"])
                    elif "name" in obj:
                        spans.append(obj)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return spans


def _check_http_internal_trace_sharing(path: Path) -> bool:
    """Check if HTTP and internal spans share trace IDs.

    Args:
        path: Path to JSONL trace file

    Returns:
        True if at least one trace contains both HTTP and internal spans
    """
    trace_spans: dict[str, tuple[bool, bool]] = {}  # trace_id -> (has_http, has_internal)

    for span in _parse_jsonl_traces(path):
        trace_id = extract_trace_id(span)
        if not trace_id:
            continue

        span_name = span.get("name", "")
        attributes = span.get("attributes", {})

        has_http = is_http_span(span_name, attributes)
        has_internal = is_internal_span(span_name)

        if trace_id in trace_spans:
            existing_http, existing_internal = trace_spans[trace_id]
            trace_spans[trace_id] = (existing_http or has_http, existing_internal or has_internal)
        else:
            trace_spans[trace_id] = (has_http, has_internal)

    # Check if any trace has both HTTP and internal spans
    for has_http, has_internal in trace_spans.values():
        if has_http and has_internal:
            return True

    return False


def _has_normalized_routes(span_names: set[str]) -> bool:
    """Check if span names use normalized route templates.

    Args:
        span_names: Set of span names

    Returns:
        True if normalized routes are present
    """
    normalized_markers = [
        "{incident_id}",
        "{run_id}",
        "{source_id}",
        "/api/incidents",
        "/api/health",
        "/api/runs",
    ]

    for name in span_names:
        for marker in normalized_markers:
            if marker in name:
                return True

    return False


# =============================================================================
# Trace Summary Validation
# =============================================================================


class TraceValidationError(Exception):
    """Validation error for trace summary."""

    pass


def validate_trace_summary(summary: TraceSummary) -> list[str]:
    """Validate trace summary against requirements.

    Args:
        summary: TraceSummary to validate

    Returns:
        List of validation failure messages (empty if all pass)
    """
    failures: list[str] = []

    if summary.trace_count == 0:
        failures.append("No traces captured (trace_count == 0)")

    if summary.span_count == 0:
        failures.append("No spans captured (span_count == 0)")

    if summary.http_span_count == 0:
        failures.append("No HTTP spans captured (http_span_count == 0)")

    if summary.internal_span_count == 0:
        failures.append("No internal spans captured (internal_span_count == 0)")

    if not summary.http_and_internal_spans_share_trace_id:
        failures.append(
            "HTTP and internal spans do not share trace IDs "
            "(http_and_internal_spans_share_trace_id == False)"
        )

    if len(summary.trace_ids) == 0:
        failures.append("No trace IDs extracted (trace_ids is empty)")

    if summary.raw_incident_ids_in_span_names:
        failures.append("Raw incident IDs found in span names")

    if summary.raw_artifact_payload_detected:
        failures.append("Raw artifact payload markers detected in trace artifacts")

    if not summary.normalized_route_names_present:
        failures.append("Normalized route names not present in span names")

    return failures


def format_validation_report(failures: list[str]) -> str:
    """Format validation failures into a report string.

    Args:
        failures: List of validation failure messages

    Returns:
        Formatted report string
    """
    if not failures:
        return "✓ All trace capture requirements met"

    lines = ["✗ Trace capture validation failed:"]
    for i, failure in enumerate(failures, 1):
        lines.append(f"  {i}. {failure}")

    return "\n".join(lines)
