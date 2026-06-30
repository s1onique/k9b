"""Tests for workflow wiring and CLI integration."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestWorkflowWiring:
    """Tests for workflow wiring and CLI integration."""

    def test_cli_module_entry_point_works(self) -> None:
        """CLI module entry point works via python -m."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Create valid lab result
            (artifact_dir / "lab-result.json").write_text(json.dumps({"success": True, "status": "passed"}))

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

            # Run CLI via python -m
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.k9b_otel_demo_lab_contract_verify",
                    "--artifact-dir",
                    str(artifact_dir),
                    "--scenario",
                    "unschedulable-shipping",
                    "--require-lab-passed",
                    "--otel-traces",
                    "auto",
                    "--json",
                ],
                capture_output=True,
                text=True,
            )

            # Should succeed (exit code 0)
            assert result.returncode == 0, f"CLI failed: {result.stderr}"

            # Should output valid JSON
            output = json.loads(result.stdout)
            assert output["passed"] is True

    def test_workflow_invokes_correct_commands(self) -> None:
        """Verify the workflow file contains correct command invocations."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")

        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()

        # Verify verifier invocation is present
        assert "scripts.k9b_otel_demo_lab_contract_verify" in content, "Workflow should invoke the contract verifier module"

        # Verify --scenario is used with input
        assert '"${{ inputs.incident_scenario }}"' in content, "Workflow should pass incident_scenario input to verifier"

        # Verify unschedulable-shipping gating condition
        assert "inputs.incident_scenario == 'unschedulable-shipping'" in content, "Workflow should gate verifier on unschedulable-shipping"

        # Verify --otel-traces auto is used
        assert "--otel-traces auto" in content or '"auto"' in content, "Workflow should use --otel-traces auto"

        # Verify artifacts upload uses always() condition
        assert "Upload Live Lab Artifacts" in content, "Workflow should have artifact upload step"
        assert "if: always()" in content or "if: ${{ always() }}" in content, "Artifact upload should use if: always() to run even on failure"
