"""Unit tests for perf_baseline_contract module.

Tests cover:
1. Schema version format
2. BaselineSummary creation and serialization
3. EndpointBaseline creation and serialization
4. SpanBreakdown creation and serialization
5. Skipped endpoint handling
6. Privacy checks (check_raw_incident_id, check_artifact_payload)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from perf_baseline_contract import (
    SCHEMA_VERSION,
    BaselineSummary,
    EndpointBaseline,
    SpanBreakdown,
    check_artifact_payload,
    check_raw_incident_id,
)


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


class TestBaselineSummary:
    """Tests for BaselineSummary dataclass."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        summary = BaselineSummary()
        assert summary.schema_version == SCHEMA_VERSION
        assert summary.benchmarked_endpoints == []
        assert summary.skipped_endpoints == []
        assert summary.slowest_endpoint == ""
        assert summary.total_traces == 0

    def test_custom_values(self) -> None:
        """Custom values are preserved."""
        summary = BaselineSummary(
            benchmarked_endpoints=[{"route": "/api/test"}],
            skipped_endpoints=["/api/runtime-status"],
            slowest_endpoint="GET /api/slow",
            total_traces=10,
        )
        assert len(summary.benchmarked_endpoints) == 1
        assert len(summary.skipped_endpoints) == 1
        assert summary.slowest_endpoint == "GET /api/slow"
        assert summary.total_traces == 10

    def test_to_dict_serialization(self) -> None:
        """to_dict returns serializable dictionary."""
        summary = BaselineSummary(
            iteration_count=5,
            warmup_count=2,
            incident_id_source="provided",
        )
        data = summary.to_dict()
        assert data["iteration_count"] == 5
        assert data["warmup_count"] == 2
        assert data["incident_id_source"] == "provided"


class TestEndpointBaseline:
    """Tests for EndpointBaseline dataclass."""

    def test_creation(self) -> None:
        """EndpointBaseline is created correctly."""
        endpoint = EndpointBaseline(
            method="GET",
            route="/api/incidents",
            normalized_route="GET /api/incidents",
            attempt_count=10,
            success_count=8,
            failure_count=2,
        )
        assert endpoint.method == "GET"
        assert endpoint.attempt_count == 10
        assert endpoint.success_count == 8
        assert endpoint.failure_count == 2

    def test_latency_defaults(self) -> None:
        """Latency defaults to zeros."""
        endpoint = EndpointBaseline(
            method="GET",
            route="/api/test",
            normalized_route="GET /api/test",
        )
        assert endpoint.latency_ms["min"] == 0.0
        assert endpoint.latency_ms["p50"] == 0.0
        assert endpoint.latency_ms["max"] == 0.0

    def test_to_dict_bounds_trace_ids(self) -> None:
        """to_dict limits trace_ids to 100."""
        endpoint = EndpointBaseline(
            method="GET",
            route="/api/test",
            normalized_route="GET /api/test",
            trace_ids=[f"trace{i}" for i in range(150)],
        )
        data = endpoint.to_dict()
        assert len(data["trace_ids"]) == 100


class TestSpanBreakdown:
    """Tests for SpanBreakdown dataclass."""

    def test_creation(self) -> None:
        """SpanBreakdown is created correctly."""
        breakdown = SpanBreakdown(
            trace_id="trace123",
            route="/api/incidents",
            span_count=5,
            http_span_count=1,
            http_span_duration_ms=25.0,
        )
        assert breakdown.trace_id == "trace123"
        assert breakdown.span_count == 5
        assert breakdown.http_span_count == 1

    def test_to_dict_rounds_duration(self) -> None:
        """to_dict rounds durations to 2 decimal places."""
        breakdown = SpanBreakdown(
            trace_id="trace123",
            route="/api/test",
            internal_span_duration_ms_total=15.567,
        )
        data = breakdown.to_dict()
        assert data["internal_span_duration_ms_total"] == 15.57


class TestSkippedEndpoints:
    """Tests for skipped endpoint handling."""

    def test_skipped_endpoints_in_summary(self) -> None:
        """Skipped endpoints are recorded in summary."""
        summary = BaselineSummary(
            benchmarked_endpoints=[],
            skipped_endpoints=["/api/runtime-status", "/api/fleet"],
        )
        assert len(summary.skipped_endpoints) == 2
        assert "/api/runtime-status" in summary.skipped_endpoints


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
