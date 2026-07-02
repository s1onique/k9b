"""Tests for P4c contract verifier with normalized outcome."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.otel_lab_contracts.models import VerificationReport
from scripts.otel_lab_contracts.p4c_diagnosis import (
    _check_scheduling_markers_from_evidence,
    verify_p4c_diagnosis,
)


@pytest.fixture
def verification_report() -> VerificationReport:
    """Create a fresh VerificationReport for each test."""
    return VerificationReport(passed=True)


class TestVerifyP4cWithNormalizedOutcome:
    """Tests for contract verifier with normalized p4c_outcome."""

    def test_terminal_single_pass_with_normalized_outcome_passes(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Contract verifier accepts terminal single-pass with normalized outcome."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "p4c_outcome": {
                "success": True,
                "mode": "terminal_single_pass",
                "pass_count": 1,
                "pass_run_ids": ["run-1"],
                "review_artifact_paths": [],
                "failure_reasons": [],
            },
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(__import__("json").dumps(evidence))

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is True

    def test_multipass_failure_with_normalized_outcome_fails(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Contract verifier reports multipass failure from normalized outcome."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "p4c_outcome": {
                "success": False,
                "mode": "multipass",
                "pass_count": 1,
                "pass_run_ids": [],
                "review_artifact_paths": [],
                "failure_reasons": ["insufficient_passes: 1 < 2"],
            },
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(__import__("json").dumps(evidence))

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is False


class TestVerifyP4cLegacyFallback:
    """Tests for legacy fallback when p4c_outcome is absent."""

    def test_terminal_single_pass_legacy_fallback_uses_tmp_path(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Legacy fallback uses tmp_path, not repo-relative paths."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "p4c_verdict": {
                "matched_evidence": ["FailedScheduling"],
                "success": True,
            },
            "root_cause_summary": "Terminal diagnosis reached",
            # No p4c_outcome - uses legacy fallback
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(__import__("json").dumps(evidence))

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is True

    def test_multipass_legacy_fallback_requires_2_passes(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Legacy fallback requires pass_count >= 2 for multipass."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping deployment has FailedScheduling",
            # No p4c_outcome - uses legacy fallback
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(__import__("json").dumps(evidence))

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is False


class TestVerifyP4cTerminalMode:
    """Tests for terminal single-pass mode in contract verifier."""

    def test_terminal_single_pass_requires_scheduling_markers(
        self, tmp_path: Path, verification_report: VerificationReport
    ) -> None:
        """Terminal mode fails without scheduling markers."""
        diagnosis_dir = tmp_path / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
        diagnosis_dir.mkdir(parents=True)

        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            # No p4c_verdict with scheduling markers
            "root_cause_summary": "Some unrelated text",
        }
        (diagnosis_dir / "diagnosis-evidence.json").write_text(__import__("json").dumps(evidence))

        result = verify_p4c_diagnosis(tmp_path, verification_report)

        assert result is False
        errors = [e for e in verification_report.errors if "scheduling markers" in e.lower()]
        assert len(errors) >= 1


class TestCheckSchedulingMarkersFromEvidence:
    """Tests for scheduling markers detection."""

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
                    {"reason": "FailedScheduling", "message": "0/1 nodes are available"},
                ],
            },
        }
        result = _check_scheduling_markers_from_evidence(evidence)
        assert any("failedscheduling" in m.lower() for m in result)
