"""Unit tests for index performance proof verification.

Tests for:
- Delta calculation
- Improvement percentage
- No-regression threshold logic
- Fallback-span detection
- Content-index span counting
- Privacy check
- Honest negative-improvement reporting
"""

from __future__ import annotations

# Import from verify_index_perf_proof modules
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "trace-capture"))

from verify_index_perf_proof_contract import (
    INDEXED_ENDPOINT_ROUTES,
    LatencyDelta,
    PerfProofSummary,
    VerificationResult,
)
from verify_index_perf_proof_latency import (
    check_no_regression,
    compute_improvement_percent,
    compute_latency_delta,
)
from verify_index_perf_proof_logic import verify_index_db
from verify_index_perf_proof_spans import (
    CONTENT_INDEX_FALLBACK_SPAN_NAMES,
    CONTENT_INDEX_QUERY_SPAN_NAMES,
    check_artifact_payload,
    check_privacy_in_file,
    check_raw_incident_id,
    count_content_index_spans,
)


class TestDeltaCalculation:
    """Tests for delta calculation functions."""

    def test_compute_latency_delta_improvement(self) -> None:
        """Test delta calculation when index improves latency."""
        disabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}
        enabled = {"p50": 80.0, "p90": 160.0, "p99": 240.0}

        delta = compute_latency_delta(disabled, enabled)

        # Positive delta = improvement
        assert delta.p50_delta_ms == 20.0
        assert delta.p90_delta_ms == 40.0
        assert delta.p99_delta_ms == 60.0
        assert delta.p50_improvement_percent == 20.0
        assert delta.p90_improvement_percent == 20.0
        assert delta.p99_improvement_percent == 20.0

    def test_compute_latency_delta_regression(self) -> None:
        """Test delta calculation when index regresses latency."""
        disabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}
        enabled = {"p50": 120.0, "p90": 240.0, "p99": 360.0}

        delta = compute_latency_delta(disabled, enabled)

        # Negative delta = regression
        assert delta.p50_delta_ms == -20.0
        assert delta.p90_delta_ms == -40.0
        assert delta.p99_delta_ms == -60.0
        assert delta.p50_improvement_percent == -20.0
        assert delta.p90_improvement_percent == -20.0
        assert delta.p99_improvement_percent == -20.0

    def test_compute_latency_delta_zero(self) -> None:
        """Test delta calculation when latencies are equal."""
        stats = {"p50": 100.0, "p90": 200.0, "p99": 300.0}

        delta = compute_latency_delta(stats, stats)

        assert delta.p50_delta_ms == 0.0
        assert delta.p90_delta_ms == 0.0
        assert delta.p99_delta_ms == 0.0
        assert delta.p50_improvement_percent == 0.0
        assert delta.p90_improvement_percent == 0.0
        assert delta.p99_improvement_percent == 0.0

    def test_compute_latency_delta_missing_keys(self) -> None:
        """Test delta calculation with missing keys."""
        disabled = {"p50": 100.0}
        enabled: dict[str, float] = {}

        delta = compute_latency_delta(disabled, enabled)

        assert delta.disabled_p50_ms == 100.0
        assert delta.enabled_p50_ms == 0.0
        assert delta.p50_delta_ms == 100.0
        assert delta.p50_improvement_percent == 100.0  # 100/100 * 100

    def test_compute_improvement_percent_positive(self) -> None:
        """Test improvement percentage calculation with positive delta."""
        percent = compute_improvement_percent(20.0, 100.0)
        assert percent == 20.0

    def test_compute_improvement_percent_negative(self) -> None:
        """Test improvement percentage calculation with negative delta."""
        percent = compute_improvement_percent(-20.0, 100.0)
        assert percent == -20.0

    def test_compute_improvement_percent_zero_baseline(self) -> None:
        """Test improvement percentage with zero baseline."""
        percent = compute_improvement_percent(10.0, 0.0)
        assert percent == 0.0


class TestNoRegressionThreshold:
    """Tests for no-regression threshold logic."""

    def test_no_regression_within_threshold(self) -> None:
        """Test that regression within threshold is acceptable."""
        delta = LatencyDelta(
            p50_improvement_percent=-3.0,  # 3% regression
        )
        assert check_no_regression(delta, threshold_percent=5.0) is True

    def test_no_regression_at_threshold(self) -> None:
        """Test that regression at threshold is acceptable."""
        delta = LatencyDelta(
            p50_improvement_percent=-5.0,  # 5% regression
        )
        assert check_no_regression(delta, threshold_percent=5.0) is True

    def test_no_regression_exceeds_threshold(self) -> None:
        """Test that regression exceeding threshold fails."""
        delta = LatencyDelta(
            p50_improvement_percent=-10.0,  # 10% regression
        )
        assert check_no_regression(delta, threshold_percent=5.0) is False

    def test_no_regression_improvement(self) -> None:
        """Test that improvement always passes."""
        delta = LatencyDelta(
            p50_improvement_percent=20.0,  # 20% improvement
        )
        assert check_no_regression(delta, threshold_percent=5.0) is True


class TestFallbackSpanDetection:
    """Tests for fallback-span detection."""

    def test_fallback_span_recognized(self) -> None:
        """Test that fallback spans are properly recognized."""
        spans = [
            {"name": "k9b.content_index.fallback", "attributes": {"reason": "index_not_found"}},
        ]
        query_count, fallback_count = count_content_index_spans(spans)

        assert query_count == 0
        assert fallback_count == 1

    def test_query_span_recognized(self) -> None:
        """Test that query spans are properly recognized."""
        spans = [
            {"name": "k9b.content_index.query", "attributes": {"kind": "list_incidents"}},
        ]
        query_count, fallback_count = count_content_index_spans(spans)

        assert query_count == 1
        assert fallback_count == 0

    def test_mixed_spans(self) -> None:
        """Test counting mixed query and fallback spans."""
        spans = [
            {"name": "k9b.content_index.query", "attributes": {}},
            {"name": "k9b.content_index.open", "attributes": {}},
            {"name": "k9b.content_index.fallback", "attributes": {}},
            {"name": "k9b.api.incidents", "attributes": {}},  # Should not count
        ]
        query_count, fallback_count = count_content_index_spans(spans)

        assert query_count == 2
        assert fallback_count == 1

    def test_empty_spans(self) -> None:
        """Test counting with empty span list."""
        query_count, fallback_count = count_content_index_spans([])
        assert query_count == 0
        assert fallback_count == 0


class TestContentIndexSpanCounting:
    """Tests for content-index span counting."""

    def test_span_names_defined(self) -> None:
        """Test that span names are properly defined."""
        assert "k9b.content_index.query" in CONTENT_INDEX_QUERY_SPAN_NAMES
        assert "k9b.content_index.open" in CONTENT_INDEX_QUERY_SPAN_NAMES
        assert "k9b.content_index.validate" in CONTENT_INDEX_QUERY_SPAN_NAMES
        assert "k9b.content_index.fallback" in CONTENT_INDEX_FALLBACK_SPAN_NAMES

    def test_indexed_endpoints_defined(self) -> None:
        """Test that indexed endpoints are properly defined."""
        assert "GET /api/incidents" in INDEXED_ENDPOINT_ROUTES
        assert "GET /api/incidents/{incident_id}" in INDEXED_ENDPOINT_ROUTES


class TestPrivacyCheck:
    """Tests for privacy check functions."""

    def test_raw_incident_id_detected(self) -> None:
        """Test that raw incident IDs are detected."""
        text = "incident-12345678-1234-1234-1234-123456789abc-summary"
        assert check_raw_incident_id(text) is True

    def test_raw_incident_id_not_detected(self) -> None:
        """Test that sanitized text passes."""
        text = "incident-{incident_id}-summary"
        assert check_raw_incident_id(text) is False

    def test_artifact_payload_detected(self) -> None:
        """Test that artifact payload markers are detected."""
        markers = [
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
        for marker in markers:
            assert check_artifact_payload(marker) is True

    def test_artifact_payload_not_detected(self) -> None:
        """Test that safe text passes."""
        text = "This is a safe summary without any sensitive markers"
        assert check_artifact_payload(text) is False

    def test_check_privacy_in_file_passes(self) -> None:
        """Test privacy check on safe file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"summary": "Safe incident summary"}')
            path = Path(f.name)

        try:
            passed, violations = check_privacy_in_file(path)
            assert passed is True
            assert len(violations) == 0
        finally:
            path.unlink(missing_ok=True)

    def test_check_privacy_in_file_fails(self) -> None:
        """Test privacy check on file with raw incident ID."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"incident_id": "12345678-1234-1234-1234-123456789abc"}')
            path = Path(f.name)

        try:
            passed, violations = check_privacy_in_file(path)
            assert passed is False
            assert len(violations) > 0
        finally:
            path.unlink(missing_ok=True)


class TestIndexDBVerification:
    """Tests for index DB verification."""

    def test_verify_index_db_missing(self) -> None:
        """Test verification of missing database."""
        valid, msg = verify_index_db(Path("/nonexistent/path.sqlite"))
        assert valid is False
        assert "not found" in msg.lower() or "not specified" in msg.lower()

    def test_verify_index_db_none(self) -> None:
        """Test verification with None path."""
        valid, msg = verify_index_db(None)
        assert valid is False
        assert "not specified" in msg.lower()


class TestLatencyDelta:
    """Tests for LatencyDelta dataclass."""

    def test_latency_delta_to_dict(self) -> None:
        """Test LatencyDelta serialization."""
        delta = LatencyDelta(
            disabled_p50_ms=100.0,
            enabled_p50_ms=80.0,
            p50_delta_ms=20.0,
            p50_improvement_percent=20.0,
        )
        result = delta.to_dict()

        assert result["disabled_p50_ms"] == 100.0
        assert result["enabled_p50_ms"] == 80.0
        assert result["p50_delta_ms"] == 20.0
        assert result["p50_improvement_percent"] == 20.0

    def test_latency_delta_rounding(self) -> None:
        """Test that values are properly rounded."""
        delta = LatencyDelta(
            disabled_p50_ms=100.123456,
            enabled_p50_ms=80.789012,
            p50_delta_ms=19.334444,
            p50_improvement_percent=19.3344,
        )
        result = delta.to_dict()

        assert result["disabled_p50_ms"] == 100.12
        assert result["enabled_p50_ms"] == 80.79
        assert result["p50_delta_ms"] == 19.33
        assert result["p50_improvement_percent"] == 19.33


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verification_result_to_dict(self) -> None:
        """Test VerificationResult serialization."""
        result = VerificationResult(
            index_db_valid=True,
            disabled_run_success=True,
            enabled_run_success=True,
            enabled_emits_content_index_spans=True,
            fallback_spans_for_indexed_endpoints=True,
            api_shape_compatible=True,
            privacy_check_passed=True,
            errors=[],
            warnings=["Minor warning"],
        )
        d = result.to_dict()

        assert d["index_db_valid"] is True
        assert d["disabled_run_success"] is True
        assert d["enabled_run_success"] is True
        assert d["enabled_emits_content_index_spans"] is True
        assert d["fallback_spans_for_indexed_endpoints"] is True
        assert d["api_shape_compatible"] is True
        assert d["privacy_check_passed"] is True
        assert d["errors"] == []
        assert d["warnings"] == ["Minor warning"]


class TestPerfProofSummary:
    """Tests for PerfProofSummary dataclass."""

    def test_perf_proof_summary_to_dict(self) -> None:
        """Test PerfProofSummary serialization."""
        summary = PerfProofSummary(
            schema_version="k9b.index_perf_proof.v1",
            index_enabled_default=False,
            index_db_valid=True,
            endpoints_compared=["GET /api/incidents"],
            disabled={"trace_count": 10, "span_count": 100},
            enabled={"trace_count": 10, "span_count": 100, "content_index_query_span_count": 5},
            latency_delta={"GET /api/incidents": {"p50_delta_ms": 10.0}},
            api_shape_compatible=True,
            privacy_check_passed=True,
        )
        d = summary.to_dict()

        assert d["schema_version"] == "k9b.index_perf_proof.v1"
        assert d["index_enabled_default"] is False
        assert d["index_db_valid"] is True
        assert d["endpoints_compared"] == ["GET /api/incidents"]
        assert d["disabled"]["trace_count"] == 10
        assert d["enabled"]["content_index_query_span_count"] == 5
        assert d["latency_delta"]["GET /api/incidents"]["p50_delta_ms"] == 10.0


class TestHonestNegativeImprovementReporting:
    """Tests for honest negative-improvement reporting."""

    def test_negative_delta_reported_correctly(self) -> None:
        """Test that negative improvements are reported honestly."""
        disabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}
        enabled = {"p50": 120.0, "p90": 240.0, "p99": 360.0}

        delta = compute_latency_delta(disabled, enabled)

        # Negative values indicate regression
        assert delta.p50_delta_ms == -20.0
        assert delta.p50_improvement_percent == -20.0

    def test_small_improvement_reported_correctly(self) -> None:
        """Test that small improvements are reported correctly."""
        disabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}
        enabled = {"p50": 99.0, "p90": 199.0, "p99": 299.0}

        delta = compute_latency_delta(disabled, enabled)

        # Small improvement
        assert delta.p50_delta_ms == 1.0
        assert delta.p50_improvement_percent == 1.0

    def test_zero_improvement_reported_correctly(self) -> None:
        """Test that zero improvements are reported correctly."""
        disabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}
        enabled = {"p50": 100.0, "p90": 200.0, "p99": 300.0}

        delta = compute_latency_delta(disabled, enabled)

        # Zero improvement
        assert delta.p50_delta_ms == 0.0
        assert delta.p50_improvement_percent == 0.0


class TestEdgeCases:
    """Tests for edge cases in delta calculation."""

    def test_empty_stats(self) -> None:
        """Test delta calculation with empty stats."""
        delta = compute_latency_delta({}, {})

        assert delta.disabled_p50_ms == 0.0
        assert delta.enabled_p50_ms == 0.0
        assert delta.p50_delta_ms == 0.0
        assert delta.p50_improvement_percent == 0.0

    def test_none_values_in_stats(self) -> None:
        """Test delta calculation handles None gracefully."""
        disabled: dict[str, float | None] = {"p50": 100.0}
        enabled: dict[str, float | None] = {"p50": None}

        delta = compute_latency_delta(disabled, enabled)

        assert delta.disabled_p50_ms == 100.0
        assert delta.enabled_p50_ms == 0.0  # None treated as 0
