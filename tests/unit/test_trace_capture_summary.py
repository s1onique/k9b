"""Tests for trace summary generation and validation.

Tests cover:
1. valid trace output produces summary
2. missing traces fails verifier
3. only HTTP spans but no internal spans fails verifier
4. HTTP/internal spans with no shared trace ID fail verifier
5. raw incident ID in span name fails verifier
6. raw artifact payload marker fails verifier
7. bounded span names are preserved
8. trace IDs are extracted
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Import from trace-capture module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from trace_summary import (
    TraceSummary,
    check_artifact_payload_in_text,
    check_raw_incident_id_in_span,
    extract_trace_id,
    format_validation_report,
    generate_trace_summary,
    is_http_span,
    is_internal_span,
    validate_trace_summary,
)

# =============================================================================
# Test TraceSummary Dataclass
# =============================================================================


class TestTraceSummary:
    """Tests for TraceSummary dataclass."""

    def test_default_values(self) -> None:
        """Default values should be sensible."""
        summary = TraceSummary()

        assert summary.schema_version == "k9b.trace_capture.v1"
        assert summary.otel_enabled is False
        assert summary.service_name == "k9b-backend"
        assert summary.collector_received_traces is False
        assert summary.trace_count == 0
        assert summary.span_count == 0
        assert summary.http_span_count == 0
        assert summary.internal_span_count == 0
        assert summary.trace_ids == ()
        assert summary.span_names == frozenset()
        assert summary.normalized_route_names_present is False
        assert summary.http_and_internal_spans_share_trace_id is False
        assert summary.raw_incident_ids_in_span_names is False
        assert summary.raw_artifact_payload_detected is False

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce a serializable dict."""
        summary = TraceSummary(
            otel_enabled=True,
            service_name="test-service",
            trace_count=5,
            span_count=10,
            http_span_count=5,
            internal_span_count=5,
            trace_ids=("abc123", "def456"),
            span_names=frozenset({"k9b.api.route", "k9b.incident_store.list"}),
            normalized_route_names_present=True,
            http_and_internal_spans_share_trace_id=True,
        )

        data = summary.to_dict()

        assert data["otel_enabled"] is True
        assert data["service_name"] == "test-service"
        assert data["trace_count"] == 5
        assert data["span_count"] == 10
        assert data["http_span_count"] == 5
        assert data["internal_span_count"] == 5
        assert data["trace_ids"] == ["abc123", "def456"]
        assert set(data["span_names"]) == {"k9b.api.route", "k9b.incident_store.list"}
        assert data["normalized_route_names_present"] is True
        assert data["http_and_internal_spans_share_trace_id"] is True

    def test_from_dict_roundtrip(self) -> None:
        """from_dict should recreate TraceSummary."""
        data = {
            "schema_version": "k9b.trace_capture.v1",
            "generated_at": "2024-01-01T00:00:00+00:00",
            "otel_enabled": True,
            "service_name": "test-service",
            "collector_received_traces": True,
            "trace_count": 3,
            "span_count": 6,
            "http_span_count": 3,
            "internal_span_count": 3,
            "trace_ids": ["id1", "id2"],
            "span_names": ["span1", "span2"],
            "normalized_route_names_present": True,
            "http_and_internal_spans_share_trace_id": True,
            "raw_incident_ids_in_span_names": False,
            "raw_artifact_payload_detected": False,
        }

        summary = TraceSummary.from_dict(data)

        assert summary.otel_enabled is True
        assert summary.service_name == "test-service"
        assert summary.trace_count == 3
        assert summary.http_span_count == 3
        assert summary.internal_span_count == 3


# =============================================================================
# Test Span Classification
# =============================================================================


class TestIsHttpSpan:
    """Tests for is_http_span function."""

    def test_http_request_method_attribute(self) -> None:
        """Should detect HTTP span with http.request.method attribute."""
        assert is_http_span("GET /api/incidents", {"http.request.method": "GET"}) is True

    def test_k9b_api_method_attribute(self) -> None:
        """Should detect HTTP span with k9b.api.method attribute."""
        assert is_http_span("POST /api/incidents", {"k9b.api.method": "POST"}) is True

    def test_k9b_api_route_attribute(self) -> None:
        """Should detect HTTP span with k9b.api.route attribute."""
        assert is_http_span("GET /api/incidents", {"k9b.api.route": "/api/incidents"}) is True

    def test_internal_span_not_http(self) -> None:
        """Should not classify internal span as HTTP."""
        assert is_http_span("k9b.incident_store.list", {}) is False

    def test_empty_attributes(self) -> None:
        """Should return False for span with no HTTP markers."""
        assert is_http_span("some.operation", {}) is False


class TestIsInternalSpan:
    """Tests for is_internal_span function."""

    def test_incident_store_span(self) -> None:
        """Should detect incident_store internal span."""
        assert is_internal_span("k9b.incident_store.list") is True

    def test_artifact_span(self) -> None:
        """Should detect artifact internal span."""
        assert is_internal_span("k9b.artifact.scan") is True

    def test_review_packet_span(self) -> None:
        """Should detect review_packet internal span."""
        assert is_internal_span("k9b.review_packet.load") is True

    def test_api_span_not_internal(self) -> None:
        """Should not classify API span as internal."""
        assert is_internal_span("k9b.api.GET /api/incidents") is False

    def test_non_k9b_span(self) -> None:
        """Should not classify non-k9b span as internal."""
        assert is_internal_span("some.other.span") is False


class TestExtractTraceId:
    """Tests for extract_trace_id function."""

    def test_trace_id_in_root(self) -> None:
        """Should extract trace_id from root of span dict."""
        span = {"trace_id": "abc123def456"}
        assert extract_trace_id(span) == "abc123def456"

    def test_trace_id_in_context(self) -> None:
        """Should extract trace_id from context."""
        span = {"context": {"trace_id": "abc123def456"}}
        assert extract_trace_id(span) == "abc123def456"

    def test_trace_id_not_found(self) -> None:
        """Should return None when trace_id not found."""
        span = {"name": "test-span"}
        assert extract_trace_id(span) is None


# =============================================================================
# Test Privacy Checks
# =============================================================================


class TestCheckRawIncidentIdInSpan:
    """Tests for check_raw_incident_id_in_span function."""

    def test_no_raw_id(self) -> None:
        """Should return False when no raw incident ID."""
        assert check_raw_incident_id_in_span("k9b.incident_store.list", {}) is False

    def test_raw_id_in_span_name(self) -> None:
        """Should detect raw UUID in span name."""
        # Use valid hex characters only (UUID format)
        assert check_raw_incident_id_in_span(
            "GET /api/incidents/1234abcd-5678-efab-9999-000000000000",
            {},
        ) is True

    def test_raw_id_in_attribute(self) -> None:
        """Should detect raw UUID in attributes."""
        # Use valid hex characters only (UUID format)
        assert check_raw_incident_id_in_span(
            "k9b.api.route",
            {"k9b.api.route": "/api/incidents/1234abcd-5678-efab-9999-000000000000"},
        ) is True


class TestCheckArtifactPayloadInText:
    """Tests for check_artifact_payload_in_text function."""

    def test_no_payload_markers(self) -> None:
        """Should return False when no payload markers."""
        text = "This is a normal log message with no sensitive data."
        assert check_artifact_payload_in_text(text) is False

    def test_kubeconfig_marker(self) -> None:
        """Should detect kubeconfig marker."""
        text = "Error loading kubeconfig from file"
        assert check_artifact_payload_in_text(text) is True

    def test_token_marker(self) -> None:
        """Should detect token marker."""
        text = "Bearer token found in request"
        assert check_artifact_payload_in_text(text) is True

    def test_private_key_marker(self) -> None:
        """Should detect private key marker."""
        text = "BEGIN_RSA_PRIVATE_KEY block detected"
        assert check_artifact_payload_in_text(text) is True


# =============================================================================
# Test Validation
# =============================================================================


class TestValidateTraceSummary:
    """Tests for validate_trace_summary function."""

    def test_valid_summary_passes(self) -> None:
        """Valid summary should pass all checks."""
        summary = TraceSummary(
            otel_enabled=True,
            trace_count=1,
            span_count=5,
            http_span_count=2,
            internal_span_count=3,
            trace_ids=("abc123",),
            span_names=frozenset({"GET /api/incidents", "k9b.incident_store.list"}),
            normalized_route_names_present=True,
            http_and_internal_spans_share_trace_id=True,
        )

        failures = validate_trace_summary(summary)
        assert failures == []

    def test_missing_traces_fails(self) -> None:
        """Should fail when trace_count is zero."""
        summary = TraceSummary(trace_count=0)

        failures = validate_trace_summary(summary)
        assert any("No traces captured" in f for f in failures)

    def test_missing_spans_fails(self) -> None:
        """Should fail when span_count is zero."""
        summary = TraceSummary(span_count=0)

        failures = validate_trace_summary(summary)
        assert any("No spans captured" in f for f in failures)

    def test_missing_http_spans_fails(self) -> None:
        """Should fail when http_span_count is zero."""
        summary = TraceSummary(http_span_count=0, internal_span_count=5)

        failures = validate_trace_summary(summary)
        assert any("No HTTP spans" in f for f in failures)

    def test_missing_internal_spans_fails(self) -> None:
        """Should fail when internal_span_count is zero."""
        summary = TraceSummary(http_span_count=5, internal_span_count=0)

        failures = validate_trace_summary(summary)
        assert any("No internal spans" in f for f in failures)

    def test_no_shared_trace_id_fails(self) -> None:
        """Should fail when HTTP and internal spans don't share trace IDs."""
        summary = TraceSummary(
            http_span_count=5,
            internal_span_count=5,
            http_and_internal_spans_share_trace_id=False,
        )

        failures = validate_trace_summary(summary)
        assert any("do not share trace IDs" in f for f in failures)

    def test_empty_trace_ids_fails(self) -> None:
        """Should fail when trace_ids is empty."""
        summary = TraceSummary(trace_ids=())

        failures = validate_trace_summary(summary)
        assert any("No trace IDs extracted" in f for f in failures)

    def test_raw_incident_id_fails(self) -> None:
        """Should fail when raw incident IDs detected."""
        summary = TraceSummary(raw_incident_ids_in_span_names=True)

        failures = validate_trace_summary(summary)
        assert any("Raw incident IDs" in f for f in failures)

    def test_raw_payload_fails(self) -> None:
        """Should fail when raw payload markers detected."""
        summary = TraceSummary(raw_artifact_payload_detected=True)

        failures = validate_trace_summary(summary)
        assert any("payload markers" in f for f in failures)

    def test_no_normalized_routes_fails(self) -> None:
        """Should fail when normalized routes not present."""
        summary = TraceSummary(normalized_route_names_present=False)

        failures = validate_trace_summary(summary)
        assert any("Normalized route names" in f for f in failures)


class TestFormatValidationReport:
    """Tests for format_validation_report function."""

    def test_empty_failures(self) -> None:
        """Should return success message when no failures."""
        result = format_validation_report([])
        assert "✓" in result
        assert "All trace capture requirements met" in result

    def test_failures_formatted(self) -> None:
        """Should format failures with numbers."""
        failures = ["Failure 1", "Failure 2"]
        result = format_validation_report(failures)

        assert "✗" in result
        assert "1. Failure 1" in result
        assert "2. Failure 2" in result


# =============================================================================
# Test Summary Generation from JSONL
# =============================================================================


class TestGenerateTraceSummary:
    """Tests for generate_trace_summary function."""

    def test_empty_jsonl_produces_empty_summary(self) -> None:
        """Empty JSONL should produce summary with zero counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            jsonl_path.write_text("")

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert summary.trace_count == 0
            assert summary.span_count == 0
            assert summary.http_span_count == 0
            assert summary.internal_span_count == 0

    def test_http_span_in_jsonl(self) -> None:
        """Should count HTTP spans from JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            jsonl_path.write_text(
                json.dumps({
                    "trace_id": "abc123",
                    "name": "GET /api/incidents",
                    "attributes": {
                        "k9b.api.method": "GET",
                        "k9b.api.route": "/api/incidents",
                    },
                }) + "\n"
            )

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert summary.http_span_count == 1
            assert summary.trace_count == 1
            assert "GET /api/incidents" in summary.span_names

    def test_internal_span_in_jsonl(self) -> None:
        """Should count internal spans from JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            jsonl_path.write_text(
                json.dumps({
                    "trace_id": "abc123",
                    "name": "k9b.incident_store.list",
                    "attributes": {"k9b.operation": "list"},
                }) + "\n"
            )

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert summary.internal_span_count == 1
            assert summary.trace_count == 1

    def test_http_and_internal_share_trace(self) -> None:
        """Should detect HTTP and internal spans sharing trace ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            # Both spans have the same trace_id
            jsonl_path.write_text(
                json.dumps({
                    "trace_id": "shared123",
                    "name": "GET /api/incidents",
                    "attributes": {"k9b.api.method": "GET"},
                }) + "\n"
                + json.dumps({
                    "trace_id": "shared123",
                    "name": "k9b.incident_store.list",
                    "attributes": {"k9b.operation": "list"},
                }) + "\n"
            )

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert summary.http_and_internal_spans_share_trace_id is True
            assert summary.http_span_count == 1
            assert summary.internal_span_count == 1

    def test_trace_ids_extracted(self) -> None:
        """Should extract trace IDs from spans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            jsonl_path.write_text(
                json.dumps({"trace_id": "id1", "name": "span1", "attributes": {}}) + "\n"
                + json.dumps({"trace_id": "id2", "name": "span2", "attributes": {}}) + "\n"
            )

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert len(summary.trace_ids) == 2
            assert "id1" in summary.trace_ids
            assert "id2" in summary.trace_ids

    def test_bounded_trace_ids(self) -> None:
        """Should bound trace IDs to 100."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            lines = [
                json.dumps({"trace_id": f"id{i:03d}", "name": f"span{i}", "attributes": {}})
                for i in range(150)
            ]
            jsonl_path.write_text("\n".join(lines) + "\n")

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert len(summary.trace_ids) <= 100

    def test_raw_id_detection(self) -> None:
        """Should detect raw incident ID in span."""
        with tempfile.TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "traces.jsonl"
            # Use valid hex characters only (UUID format)
            jsonl_path.write_text(
                json.dumps({
                    "trace_id": "abc123",
                    "name": "GET /api/incidents/1234abcd-5678-efab-9999-000000000000",
                    "attributes": {},
                }) + "\n"
            )

            summary = generate_trace_summary(trace_json_path=jsonl_path)

            assert summary.raw_incident_ids_in_span_names is True


# =============================================================================
# Test Verifier with Mock Data
# =============================================================================


class TestVerifierIntegration:
    """Integration tests for verifier with complete mock data."""

    def test_full_verification_passes(self) -> None:
        """Complete valid summary should pass all verifications."""
        summary = TraceSummary(
            otel_enabled=True,
            service_name="k9b-backend",
            collector_received_traces=True,
            trace_count=1,
            span_count=6,
            http_span_count=3,
            internal_span_count=3,
            trace_ids=("validtraceid12345678901234567",),
            span_names=frozenset({
                "GET /api/health/details",
                "GET /api/incidents",
                "GET /api/incidents/{incident_id}",
                "k9b.incident_store.list",
                "k9b.incident_store.get",
                "k9b.artifact.scan",
            }),
            normalized_route_names_present=True,
            http_and_internal_spans_share_trace_id=True,
            raw_incident_ids_in_span_names=False,
            raw_artifact_payload_detected=False,
        )

        failures = validate_trace_summary(summary)
        assert failures == [], f"Unexpected failures: {failures}"

    def test_full_verification_with_uuid_trace_ids(self) -> None:
        """Summary with UUID-format trace IDs should pass."""
        import uuid

        trace_id = uuid.uuid4().hex
        summary = TraceSummary(
            otel_enabled=True,
            service_name="k9b-backend",
            collector_received_traces=True,
            trace_count=1,
            span_count=4,
            http_span_count=2,
            internal_span_count=2,
            trace_ids=(trace_id,),
            span_names=frozenset({
                "GET /api/incidents",
                "POST /api/incidents/{incident_id}/automatic-diagnosis-review/handoff",
                "k9b.incident_store.list",
                "k9b.review_packet.load",
            }),
            normalized_route_names_present=True,
            http_and_internal_spans_share_trace_id=True,
            raw_incident_ids_in_span_names=False,
            raw_artifact_payload_detected=False,
        )

        failures = validate_trace_summary(summary)
        assert failures == [], f"Unexpected failures: {failures}"
