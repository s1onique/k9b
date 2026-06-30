"""Tests for OTel trace verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestOtelTraceVerification:
    """Tests for OTel trace verification."""

    def test_otel_trace_auto_skips_when_missing(self) -> None:
        """OTel traces in auto mode skip when no traces found."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.AUTO, report)

            assert result is True
            assert any(c.reason == "skipped_missing" for c in report.checks)

    def test_otel_trace_require_fails_when_missing(self) -> None:
        """OTel traces in require mode fails when no traces found."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is False
            assert any("required" in e.lower() and "trace" in e.lower() for e in report.errors)

    def test_otel_trace_skip_does_not_inspect(self) -> None:
        """OTel traces in skip mode does not inspect."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.SKIP, report)

            assert result is True
            assert any(c.reason == "skipped" for c in report.checks)

    def test_otel_trace_require_fails_when_trace_file_has_no_expected_spans(self) -> None:
        """OTel traces in require mode fails when traces exist but have no expected spans."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Trace file exists but contains unrelated spans
            trace = {
                "spans": [
                    {"name": "http.request", "span_id": "1"},
                    {"name": "database.query", "span_id": "2"},
                ],
                "events": [
                    {"name": "error"},
                ],
            }
            (artifact_dir / "traces.json").write_text(json.dumps(trace))

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is False
            assert any("expected" in e.lower() and "k9b" in e.lower() for e in report.errors)

    def test_otel_trace_require_passes_when_expected_spans_found(self) -> None:
        """OTel traces in require mode passes when expected k9b spans are found."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Trace file contains expected k9b spans
            trace = {
                "spans": [
                    {"name": "k9b.diagnosis_loop.budget", "span_id": "1"},
                    {"name": "k9b.diagnosis_loop.plan", "span_id": "2"},
                ],
                "events": [
                    {"name": "k9b.diagnosis_loop.checks_executed"},
                ],
            }
            (artifact_dir / "traces.json").write_text(json.dumps(trace))

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is True
            assert report.passed is True

    def test_otel_trace_auto_warns_when_no_expected_spans(self) -> None:
        """OTel traces in auto mode warns but doesn't fail when no expected spans."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Trace file exists but contains unrelated spans
            trace = {
                "spans": [
                    {"name": "http.request", "span_id": "1"},
                ],
            }
            (artifact_dir / "traces.json").write_text(json.dumps(trace))

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.AUTO, report)

            # Should pass but warn
            assert result is True
            assert any("warning" in w.lower() or "expected" in w.lower() for w in report.warnings)

    def test_otel_trace_require_accepts_expected_spans(self) -> None:
        """OTel traces in require mode accepts traces with expected spans."""
        from scripts.otel_lab_contracts import OtelTracesMode, VerificationReport, verify_otel_traces

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create trace artifact with expected spans
            trace = {
                "spans": [
                    {"name": "k9b.diagnosis_loop.budget", "span_id": "1"},
                    {"name": "k9b.diagnosis_loop.plan", "span_id": "2"},
                    {"name": "k9b.diagnosis_loop.gate", "span_id": "3"},
                    {"name": "k9b.diagnosis_loop.execute", "span_id": "4"},
                    {"name": "k9b.diagnosis_loop.artifact", "span_id": "5"},
                ],
                "events": [
                    {"name": "k9b.diagnosis_loop.checks_executed"},
                    {"name": "k9b.diagnosis_loop.artifact_written"},
                ],
            }
            (artifact_dir / "traces.json").write_text(json.dumps(trace))

            report = VerificationReport(passed=True)
            result = verify_otel_traces(artifact_dir, OtelTracesMode.REQUIRE, report)

            assert result is True
            assert any(c.name == "otel_traces" and c.passed for c in report.checks)
