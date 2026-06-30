"""Tests for P4c diagnosis verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestP4cDiagnosisVerification:
    """Tests for P4c diagnosis contract verification."""

    def test_p4c_requires_shipping_identity(self) -> None:
        """P4c requires shipping reference in root_cause_summary."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p4c_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "Generic deployment issue",  # No shipping!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("shipping" in e.lower() for e in report.errors)

    def test_p4c_requires_scheduling_marker(self) -> None:
        """P4c requires scheduling root-cause marker."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p4c_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "The shipping deployment has issues",  # No scheduling marker!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("scheduling" in e.lower() for e in report.errors)

    def test_p4c_rejects_generic_deployment_unavailable(self) -> None:
        """P4c rejects diagnosis without scheduling-specific evidence."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p4c_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": "The shipping deployment is unavailable",  # No nodeSelector!
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("scheduling" in e.lower() for e in report.errors)

    def test_p4c_accepts_valid_scheduling_diagnosis(self) -> None:
        """P4c accepts diagnosis with scheduling-specific evidence."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p4c_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": True,
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": ("The shipping deployment has an impossible nodeSelector k9b.dev/otel-lab-node=missing. No node has this label, so the pod cannot be scheduled (FailedScheduling)."),
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_p4c_rejects_simulation(self) -> None:
        """P4c rejects when real_loop_invoked is False."""
        from scripts.otel_lab_contracts import VerificationReport, verify_p4c_diagnosis

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            evidence = {
                "real_loop_invoked": False,  # Simulation!
                "incident_id": "inc-123",
                "pass_count": 2,
                "root_cause_summary": ("The shipping deployment has nodeSelector k9b.dev/otel-lab-node=missing"),
                "executed_checks": [],
                "read_only": True,
                "phase_result_reason": "diagnosis_rca_valid",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            report = VerificationReport(passed=True)
            result = verify_p4c_diagnosis(artifact_dir, report)

            assert result is False
            assert any("simulation" in e.lower() or "real_loop" in e.lower() for e in report.errors)
