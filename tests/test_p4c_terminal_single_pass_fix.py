"""Regression tests for P4c terminal single-pass acceptance.

These tests verify the fix for the split-brain success semantics where:
1. Backend-targeted diagnosis accepted terminal single-pass as valid
2. But outer P4c validator still required pass_count >= 2

See: scripts/k9b_otel_demo_lab_k8s_diagnosis_phase.py
See: scripts/otel_lab_contracts/p4c_diagnosis.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    extract_pass_run_ids,
)
from scripts.otel_lab_contracts.models import VerificationReport
from scripts.otel_lab_contracts.p4c_diagnosis import (
    _check_scheduling_markers_from_evidence,
    verify_p4c_diagnosis,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def verification_report() -> VerificationReport:
    """Create a fresh VerificationReport for each test."""
    return VerificationReport(passed=True)


class TestExtractPassRunIds:
    """Test extract_pass_run_ids helper function."""

    def test_extracts_pass_run_ids_direct(self) -> None:
        """Should extract pass_run_ids when present."""
        loop_summary = {"pass_run_ids": ["run-1", "run-2"]}
        result = extract_pass_run_ids(loop_summary)
        assert result == ["run-1", "run-2"]

    def test_extracts_diagnosis_loop_pass_run_ids_legacy(self) -> None:
        """Should extract diagnosis_loop_pass_run_ids (legacy field name)."""
        loop_summary = {"diagnosis_loop_pass_run_ids": ["legacy-1", "legacy-2"]}
        result = extract_pass_run_ids(loop_summary)
        assert result == ["legacy-1", "legacy-2"]

    def test_prefers_pass_run_ids_over_legacy(self) -> None:
        """Should prefer pass_run_ids when both present."""
        loop_summary = {
            "pass_run_ids": ["new-1"],
            "diagnosis_loop_pass_run_ids": ["old-1"],
        }
        result = extract_pass_run_ids(loop_summary)
        assert result == ["new-1"]

    def test_filters_none_values(self) -> None:
        """Should filter out None values."""
        loop_summary = {"pass_run_ids": ["run-1", None, "run-2"]}
        result = extract_pass_run_ids(loop_summary)
        assert result == ["run-1", "run-2"]

    def test_filters_empty_strings(self) -> None:
        """Should filter out empty strings."""
        loop_summary = {"pass_run_ids": ["run-1", "", "run-2"]}
        result = extract_pass_run_ids(loop_summary)
        assert result == ["run-1", "run-2"]

    def test_returns_empty_for_missing_fields(self) -> None:
        """Should return empty list when neither field present."""
        loop_summary = {"other_field": "value"}
        result = extract_pass_run_ids(loop_summary)
        assert result == []

    def test_returns_empty_for_empty_list(self) -> None:
        """Should return empty list when field is empty."""
        loop_summary: dict[str, list[str]] = {"pass_run_ids": []}
        result = extract_pass_run_ids(loop_summary)
        assert result == []


class TestSchedulingMarkersFromEvidence:
    """Test scheduling markers detection for terminal no-checks mode."""

    def test_finds_markers_in_p4c_verdict(self) -> None:
        """Should find scheduling markers in p4c_verdict."""
        evidence = {
            "p4c_verdict": {
                "matched_evidence": ["FailedScheduling", "Unschedulable"],
            },
        }
        result = _check_scheduling_markers_from_evidence(evidence)
        assert "FailedScheduling" in result
        assert "Unschedulable" in result

    def test_finds_markers_in_root_cause_summary(self) -> None:
        """Should find scheduling markers in root_cause_summary."""
        evidence = {
            "root_cause_summary": "The deployment is unschedulable due to nodeSelector mismatch",
        }
        result = _check_scheduling_markers_from_evidence(evidence)
        assert "unschedulable" in [m.lower() for m in result]

    def test_finds_markers_in_detection_evidence(self) -> None:
        """Should find scheduling markers in detection_evidence."""
        evidence = {
            "detection_evidence": {
                "events": [
                    {"reason": "FailedScheduling", "message": "0/1 nodes are available: 1 node(s) didn't match Pod's node selector"},
                ],
            },
        }
        result = _check_scheduling_markers_from_evidence(evidence)
        # Check that FailedScheduling was found (case-insensitive)
        assert any("failedscheduling" in m.lower() for m in result)
        # nodeSelector appears as camelCase in markers, lowercase in message - check presence
        assert len(result) >= 1  # At least one marker found


class TestVerifyP4cDiagnosisTerminalMode:
    """Test P4c diagnosis verification for terminal single-pass mode."""

    def test_terminal_single_pass_is_final_success(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Terminal no-checks single-pass should pass validation."""
        # Create diagnosis evidence with terminal mode fields
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "p4c_verdict": {
                "matched_evidence": ["FailedScheduling", "Unschedulable"],
                "success": True,
            },
            "root_cause_summary": "Terminal diagnosis reached without additional checks needed",
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(
            __import__("json").dumps(evidence)
        )

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is True
        checks = [c for c in verification_report.checks if c.passed]
        assert len(checks) >= 1
        p4c_check = next(c for c in checks if c.name == "p4c_diagnosis")
        assert p4c_check.details.get("success_mode") == "terminal_no_checks_single_pass"

    def test_terminal_mode_requires_scheduling_markers(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Terminal mode should fail if no scheduling markers found."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            # No p4c_verdict with scheduling markers
            "root_cause_summary": "Some unrelated diagnosis text",
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(
            __import__("json").dumps(evidence)
        )

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is False
        errors = [e for e in verification_report.errors if "scheduling markers" in e.lower()]
        assert len(errors) >= 1

    def test_multi_pass_still_requires_pass_count_2(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Multi-pass mode should still require pass_count >= 2."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            # No terminal_no_checks_accepted
            "pass_count": 1,  # Only 1 pass
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping deployment has a FailedScheduling due to nodeSelector mismatch",
            "scheduling_markers_found": ["FailedScheduling", "nodeSelector"],
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(
            __import__("json").dumps(evidence)
        )

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        # Should fail because pass_count < 2 and not terminal mode
        assert result is False
        errors = [e for e in verification_report.errors if "pass_count" in e.lower()]
        assert len(errors) >= 1

    def test_multi_pass_success_with_2_passes(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Multi-pass mode should pass with pass_count >= 2 and markers."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping deployment has a FailedScheduling due to nodeSelector mismatch",
            "read_only": True,
            "phase_result_reason": "diagnosis_rca_valid",
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(
            __import__("json").dumps(evidence)
        )

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is True
        checks = [c for c in verification_report.checks if c.passed]
        p4c_check = next(c for c in checks if c.name == "p4c_diagnosis")
        assert p4c_check.details.get("success_mode") == "multi_pass"
