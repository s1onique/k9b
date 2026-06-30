"""Tests for main verification flow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestMainVerification:
    """Tests for main verification flow."""

    def test_full_verification_passes_with_valid_artifacts(self) -> None:
        """Full verification passes with complete valid artifacts."""
        from scripts.otel_lab_contracts import OtelTracesMode, verify_live_lab_contracts

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create valid lab result
            (artifact_dir / "lab-result.json").write_text(
                json.dumps(
                    {
                        "success": True,
                        "status": "passed",
                    }
                )
            )

            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            (detection_dir / "detection-evidence.json").write_text(
                json.dumps(
                    {
                        "discovery_success": True,
                        "incident_id": "inc-123",
                        "candidate_class": "pending_pod",
                        "target_namespace": "otel-demo",
                        "root_cause_summary": "The shipping deployment has issues",
                        "shipping_reference_found": True,
                        "namespace_matches": True,
                    }
                )
            )

            # Create valid P4c evidence
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            (diagnosis_dir / "diagnosis-evidence.json").write_text(
                json.dumps(
                    {
                        "real_loop_invoked": True,
                        "incident_id": "inc-123",
                        "pass_count": 2,
                        "root_cause_summary": ("The shipping deployment has nodeSelector k9b.dev/otel-lab-node=missing. FailedScheduling event indicates pod cannot be scheduled."),
                        "executed_checks": ["kubectl_get_pods"],
                        "read_only": True,
                        "phase_result_reason": "diagnosis_rca_valid",
                    }
                )
            )

            # Create valid pass artifact
            loop_dir = diagnosis_dir / "loop-passes"
            loop_dir.mkdir(parents=True)
            (loop_dir / "pass-1.json").write_text(
                json.dumps(
                    {
                        "loop_run_id": "run-1",
                        "incident_id": "inc-123",
                        "pass_index": 1,
                        "case_file_hash": "abc123",
                        "proposed_checks": [],
                        "accepted_checks": [],
                        "rejected_checks": [],
                        "check_fingerprints": [],
                        "new_evidence_hashes": [],
                        "duplicate_check_count": 0,
                        "unsafe_check_count": 0,
                        "root_cause_summary": "Test",
                        "confidence": "high",
                        "should_continue": True,
                        "stop_reason": None,
                        "safety_metadata": {
                            "policy_enforced": True,
                            "mutating_checks_executed_count": 0,
                            "sensitive_reads_executed_count": 0,
                        },
                        "gate_summary": {"rejected_checks": []},
                    }
                )
            )

            report = verify_live_lab_contracts(
                artifact_dir=artifact_dir,
                scenario="unschedulable-shipping",
                require_lab_passed=True,
                otel_traces_mode=OtelTracesMode.AUTO,
            )

            assert report.passed is True
