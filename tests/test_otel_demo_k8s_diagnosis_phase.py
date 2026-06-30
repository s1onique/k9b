"""Tests for OTel Demo K8s-native diagnosis - Phase function.

These tests verify the P4c phase function correctly:
- Propagates real-loop metadata into evidence
- Validates read-only contract
- Fails when real loop is not invoked
- Produces artifacts that pass the verifier
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestPhaseMetadataPropagation:
    """Test metadata propagation from _run_diagnosis_loop to evidence."""

    def test_phase_propagates_real_loop_metadata(self) -> None:
        """Phase writes real_loop_invoked=True when _run_diagnosis_loop returns it."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_REAL,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock diagnosis loop returning real loop metadata
            real_loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
                "simulation_used": False,
                "automatic_loop_enabled": True,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/path/pass1.json", "/path/pass2.json"],
                "provider_invocation_attempted": True,
                "review_packet_found": True,
                "diagnosis_loop_module": "k8s_diag_agent.collect.incident_diagnosis_auto_loop",
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
                "requested_checks": [],
                "executed_checks": [],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
                "artifact_path": "/path",
                "review_packet_path": "/path/review.json",
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=real_loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Read the evidence artifact
            evidence_path = (
                artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
            )
            evidence = json.loads(evidence_path.read_text())

            # Verify metadata was propagated
            assert evidence["diagnosis_source"] == DIAGNOSIS_SOURCE_REAL
            assert evidence["simulation_used"] is False
            assert evidence["real_loop_invoked"] is True
            assert evidence["real_pass_artifacts_found"] is True
            assert evidence["pass_artifact_paths"] == ["/path/pass1.json", "/path/pass2.json"]
            assert evidence["provider_invocation_attempted"] is True
            assert evidence["review_packet_found"] is True

    def test_phase_propagates_simulation_metadata(self) -> None:
        """Phase writes simulation_used=True when simulation is used."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_SIMULATED,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock diagnosis loop returning simulation metadata
            sim_loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_SIMULATED,
                "simulation_used": True,
                "automatic_loop_enabled": False,
                "real_loop_invoked": False,
                "real_pass_artifacts_found": False,
                "pass_artifact_paths": [],
                "provider_invocation_attempted": False,
                "review_packet_found": True,
                "diagnosis_loop_module": None,
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["sim-1", "sim-2"],
                "requested_checks": [],
                "executed_checks": [],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
                "artifact_path": "/path",
                "review_packet_path": "/path/review.json",
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=sim_loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Read the evidence artifact
            evidence_path = (
                artifact_dir / "phase4-diagnosis" / "p4c-k8s-multipass-diagnosis" / "diagnosis-evidence.json"
            )
            evidence = json.loads(evidence_path.read_text())

            # Verify simulation metadata was propagated
            assert evidence["diagnosis_source"] == DIAGNOSIS_SOURCE_SIMULATED
            assert evidence["simulation_used"] is True
            assert evidence["real_loop_invoked"] is False
            assert evidence["real_pass_artifacts_found"] is False


class TestPhaseFailureCriteria:
    """Test phase failure criteria match verifier criteria."""

    def test_phase_fails_when_simulation_used(self) -> None:
        """Phase fails when simulation is used (not allowed in live-lab)."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_SIMULATED,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock simulation result
            # NOTE: real_loop_invoked=True is required to pass the early short-circuit check
            # in the phase function (automatic_diagnosis_loop_disabled gate).
            # Once past that gate, the phase tests the specific failure criteria.
            sim_loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_SIMULATED,
                "simulation_used": True,
                "automatic_loop_enabled": False,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": False,
                "pass_artifact_paths": [],
                "provider_invocation_attempted": False,
                "review_packet_found": False,
                "diagnosis_loop_module": None,
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["sim-1", "sim-2"],
                "requested_checks": [],
                "executed_checks": [],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=sim_loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                result = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Phase should fail
            assert result.success is False
            assert "simulation_used_but_not_allowed" in result.message

    def test_phase_fails_when_automatic_diagnosis_loop_disabled(self) -> None:
        """Phase fails when automatic diagnosis loop is disabled (real loop not invoked).

        The phase short-circuits with 'automatic_diagnosis_loop_disabled' when
        real_loop_invoked=False, before checking specific failure criteria.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_REAL,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock result where real loop was not invoked
            loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
                "simulation_used": False,
                "automatic_loop_enabled": True,
                "real_loop_invoked": False,  # Not invoked!
                "real_pass_artifacts_found": False,
                "pass_artifact_paths": [],
                "provider_invocation_attempted": False,
                "review_packet_found": False,
                "diagnosis_loop_module": "k8s_diag_agent.collect.incident_diagnosis_auto_loop",
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": [],
                "requested_checks": [],
                "executed_checks": [],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                result = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Phase should fail with automatic_diagnosis_loop_disabled message
            assert result.success is False
            assert "automatic_diagnosis_loop_disabled" in result.message

    def test_phase_fails_when_read_only_contract_violated(self) -> None:
        """Phase fails when mutating commands are detected."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_REAL,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock result with mutating command
            loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
                "simulation_used": False,
                "automatic_loop_enabled": True,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/path/pass1.json", "/path/pass2.json"],
                "provider_invocation_attempted": True,
                "review_packet_found": True,
                "diagnosis_loop_module": "k8s_diag_agent.collect.incident_diagnosis_auto_loop",
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
                "requested_checks": [],
                "executed_checks": ["kubectl apply -f deployment.yaml"],  # Mutating!
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing."
                ),
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                result = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Phase should fail due to read-only violation
            assert result.success is False
            assert "read_only_contract_violated" in result.message


class TestPhasePassesVerifier:
    """Test that phase artifacts pass the standalone verifier."""

    def test_phase_artifact_passes_verifier_with_real_loop(self) -> None:
        """Artifact produced by successful real-loop phase passes verifier."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_REAL,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_verify import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )
        from scripts.k9b_otel_demo_lab_types import LabConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create P3c evidence
            p3c_dir = artifact_dir / "phase3-discovery" / "p3c-k8s-discovery"
            p3c_dir.mkdir(parents=True)
            p3c_evidence = {
                "discovery_success": True,
                "validation_success": True,
                "incident_id": "inc-123",
                "candidate_class": "pending_pod",
            }
            (p3c_dir / "detection-evidence.json").write_text(json.dumps(p3c_evidence))

            # Mock successful real loop result
            real_loop_result = {
                "diagnosis_source": DIAGNOSIS_SOURCE_REAL,
                "simulation_used": False,
                "automatic_loop_enabled": True,
                "real_loop_invoked": True,
                "real_pass_artifacts_found": True,
                "pass_artifact_paths": ["/path/pass1.json", "/path/pass2.json"],
                "provider_invocation_attempted": True,
                "review_packet_found": True,
                "diagnosis_loop_module": "k8s_diag_agent.collect.incident_diagnosis_auto_loop",
                "status": "completed",
                "pass_count": 2,
                "pass_run_ids": ["run-1", "run-2"],
                "requested_checks": [],
                "executed_checks": ["kubectl_get_deployment", "kubectl_get_pods"],
                "root_cause_summary": (
                    "The shipping deployment has an impossible nodeSelector "
                    "k9b.dev/otel-lab-node=missing. No node in the cluster has "
                    "this label, so the shipping pod cannot be scheduled."
                ),
                "artifact_path": "/path",
                "review_packet_path": "/path/review.json",
            }

            with patch(
                "scripts.k9b_otel_demo_lab_k8s_diagnosis_phase.run_diagnosis_loop",
                return_value=real_loop_result,
            ):
                config = LabConfig(
                    kubeconfig="/tmp/kubeconfig",
                    artifact_dir=str(artifact_dir),
                    namespace="otel-demo",
                )
                phase_result = phase_p4c_verify_k8s_mult_pass_diagnosis(config, artifact_dir)

            # Phase should succeed
            assert phase_result.success is True

            # Verifier should also pass
            verify_result = verify_unschedulable_shipping_mult_pass_diagnosis(artifact_dir)
            assert verify_result["verified"] is True, verify_result
