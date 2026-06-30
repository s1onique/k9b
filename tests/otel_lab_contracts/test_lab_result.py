"""Tests for lab result verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestLabResultVerification:
    """Tests for lab-result.json verification."""

    def test_lab_result_requires_success_field(self) -> None:
        """Lab result must have success/status/outcome field."""
        from scripts.otel_lab_contracts import VerificationReport, verify_lab_result

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"started_at": "2024-01-01T00:00:00Z"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("missing" in e.lower() and "success" in e.lower() for e in report.errors)

    def test_lab_result_requires_passed_when_flag_set(self) -> None:
        """Lab result must indicate success when --require-lab-passed is set."""
        from scripts.otel_lab_contracts import VerificationReport, verify_lab_result

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"success": False, "status": "failed"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("failure" in e.lower() for e in report.errors)

    def test_lab_result_tolerates_missing_when_flag_not_set(self) -> None:
        """Lab result failure is tolerated when --require-lab-passed not set."""
        from scripts.otel_lab_contracts import VerificationReport, verify_lab_result

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            lab_result = {"success": False, "status": "failed"}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, False, report)

            assert result is True

    def test_lab_result_success_false_without_status_is_failure_not_missing(self) -> None:
        """Lab result with success=false (no status/outcome) should be detected as failure."""
        from scripts.otel_lab_contracts import VerificationReport, verify_lab_result

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Only has success=false, no status or outcome
            lab_result = {"success": False}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            # require_passed=True should fail on success:false
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("failure" in e.lower() for e in report.errors)

    def test_lab_result_status_false_is_detected_as_failure(self) -> None:
        """Lab result with status=false (no success field) should be detected as failure."""
        from scripts.otel_lab_contracts import VerificationReport, verify_lab_result

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Only has status=false, no success field
            lab_result = {"status": False, "outcome": None}
            (artifact_dir / "lab-result.json").write_text(json.dumps(lab_result))

            report = VerificationReport(passed=True)
            result = verify_lab_result(artifact_dir, True, report)

            assert result is False
            assert any("failure" in e.lower() for e in report.errors)
