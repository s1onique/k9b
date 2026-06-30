"""Tests for OTel Demo K8s-native diagnosis - Verifier.

These tests verify standalone verifier function.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestK8sDiagnosisVerifier:
    """Test standalone verifier function."""

    def test_verifier_returns_false_when_diagnosis_evidence_missing(self) -> None:
        """Verifier returns False when diagnosis evidence doesn't exist."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        artifact_dir = Path("/tmp/nonexistent")
        result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
        assert result["verified"] is False
        # reason is canonical phase result reason
        assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
        # phase_result_reason has the detailed reason
        assert result["phase_result_reason"] == "p3c_evidence_not_found"

    def test_verifier_returns_false_when_p3c_evidence_missing(self) -> None:
        """Verifier returns False when P3c evidence doesn't exist."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Only create diagnosis dir, not P3c dir
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)

            evidence = {
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": "Root cause is shipping deployment",
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            # reason is canonical phase result reason
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            # phase_result_reason has the detailed reason
            assert result["phase_result_reason"] == "p3c_evidence_not_found"

    def test_verifier_returns_false_when_p3c_discovery_failed(self) -> None:
        """Verifier returns False when P3c discovery success is False."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create P3c evidence with failed discovery
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": False,
                "failure_reason": "no_incident_found",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert "p3c_validation_failed" in result["phase_result_reason"]

    def test_verifier_returns_false_when_p3c_validation_failed(self) -> None:
        """Verifier returns False when P3c validation_success is False."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create P3c evidence with failed validation
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": False,
                "incident_id": "inc-123",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert "p3c_validation_failed" in result["phase_result_reason"]

    def test_verifier_returns_false_when_no_incident_id(self) -> None:
        """Verifier returns False when P3c has no incident_id."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)

            evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": None,  # Missing incident_id
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert "p3c_validation_failed" in result["phase_result_reason"]

    def test_verifier_returns_false_when_pass_count_less_than_2(self) -> None:
        """Verifier returns False when diagnosis has less than 2 passes."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence with only 1 pass (with real loop metadata)
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 1,  # Only 1 pass!
                "read_only": True,
                "root_cause_summary": "The shipping deployment has nodeSelector...",
                "executed_checks": [],
                # Required real loop metadata
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/some/path/pass1.json"],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert result["phase_result_reason"] == "insufficient_passes"
            assert result["pass_count"] == 1

    def test_verifier_returns_false_when_root_cause_missing(self) -> None:
        """Verifier returns False when root cause doesn't mention required terms."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence with valid passes but missing root cause terms
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 2,
                "read_only": True,
                # Include "shipping" to pass shipping check, but no scheduling markers
                "root_cause_summary": "The shipping deployment has an issue",  # Missing scheduling root cause!
                "executed_checks": [],
                # Required real loop metadata
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/some/path/pass1.json", "/some/path/pass2.json"],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_scheduling_root_cause"

    def test_verifier_returns_false_when_mutating_commands_found(self) -> None:
        """Verifier returns False when mutating commands are in executed checks."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence with mutating check
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": "The shipping deployment has an impossible nodeSelector...",
                "executed_checks": ["kubectl apply -f deployment.yaml"],  # Mutating!
                # Required real loop metadata
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/some/path/pass1.json", "/some/path/pass2.json"],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert result["phase_result_reason"] == "read_only_contract_violated"

    def test_verifier_returns_false_when_simulation_used(self) -> None:
        """Verifier returns False when simulation is used instead of real loop."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence with simulation metadata
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                # Simulation metadata - should be rejected
                "diagnosis_source": "simulated_diagnosis_loop",
                "simulation_used": True,
                "real_loop_invoked": False,
                "real_pass_artifacts_found": False,
                "pass_artifact_paths": [],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert result["phase_result_reason"] == "simulation_used_but_not_allowed"

    def test_verifier_returns_false_when_real_loop_not_invoked(self) -> None:
        """Verifier returns False when real loop was not invoked."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence without real loop invocation
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 2,
                "read_only": True,
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
                "executed_checks": [],
                # Real loop not invoked
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": False,  # Not invoked!
                "real_pass_artifacts_found": False,
                "pass_artifact_paths": [],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert result["phase_result_reason"] == "real_loop_not_invoked"

    def test_verifier_returns_false_when_real_pass_artifacts_missing(self) -> None:
        """Verifier returns False when real pass artifacts are missing."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence without pass artifacts
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 0,
                "read_only": True,
                "root_cause_summary": "",
                "executed_checks": [],
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": True,  # Invoked but no artifacts
                "real_pass_artifacts_found": False,  # No artifacts!
                "pass_artifact_paths": [],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is False
            assert result["reason"] == "diagnosis_missing_mult_pass_evidence"
            assert result["phase_result_reason"] == "real_pass_artifacts_missing"

    def test_verifier_passes_with_valid_diagnosis(self) -> None:
        """Verifier passes when all validations pass."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            # Create valid P3c evidence
            detection_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            detection_dir.mkdir(parents=True)
            detection_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (detection_dir / "detection-evidence.json").write_text(json.dumps(detection_evidence))

            # Create diagnosis evidence with all required elements (real loop)
            diagnosis_dir = artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis"
            diagnosis_dir.mkdir(parents=True)
            diagnosis_evidence = {
                "phase": "p4c-k8s-multipass-diagnosis",
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
                "target_namespace": "otel-demo",
                "pass_count": 2,
                "pass_run_ids": ["run-pass1", "run-pass2"],
                "read_only": True,
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing. No node in the cluster has "
                    "this label, so the shipping pod cannot be scheduled."
                ),
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                # Real loop metadata
                "diagnosis_source": "k9b_automatic_diagnosis_loop",
                "simulation_used": False,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/some/path/run-pass1.json", "/some/path/run-pass2.json"],
            }
            (diagnosis_dir / "diagnosis-evidence.json").write_text(json.dumps(diagnosis_evidence))

            result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert result["verified"] is True
            assert result["incident_id"] == "inc-123"
            assert result["pass_count"] == 2
            assert result["phase_result_reason"] == "diagnosis_rca_valid"
