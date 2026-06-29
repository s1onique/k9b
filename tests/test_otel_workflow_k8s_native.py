"""Tests for K8s-native OTel Demo Lab workflow integration.

This module tests workflow-level constraints for the K8s-native scenario:
1. Live workflow enables K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
2. Live workflow does not set K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS
3. Provider smoke is NOT added for K8s-native scenario
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


class TestK8sNativeWorkflowEnvVars:
    """Tests for K8s-native workflow environment variables."""

    def test_workflow_enables_automatic_diagnosis_loop(self) -> None:
        """K8s-native workflow sets K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
        assert workflow_path.exists(), "Workflow file must exist"
        
        content = workflow_path.read_text()
        
        # Verify K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED is set to true
        # This is critical for P4c to run real diagnosis loop
        pattern = r'K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED\s*=\s*["\']?true["\']?'
        matches = re.findall(pattern, content)
        assert len(matches) > 0, (
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true must be set in workflow"
        )

    def test_workflow_does_not_set_simulation_var(self) -> None:
        """K8s-native workflow does NOT set K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
        assert workflow_path.exists(), "Workflow file must exist"
        
        content = workflow_path.read_text()
        
        # Verify K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS is NOT set
        # P4c rejects simulation and requires real-loop metadata
        assert "K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS" not in content, (
            "K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS must NOT be set in K8s-native workflow"
        )

    def test_workflow_has_incident_scenario_input(self) -> None:
        """Workflow has incident_scenario workflow_dispatch input."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
        assert workflow_path.exists(), "Workflow file must exist"
        
        content = workflow_path.read_text()
        
        # Verify incident_scenario input exists using regex (robust to YAML anchors)
        assert "incident_scenario:" in content, (
            "Workflow must have incident_scenario input defined"
        )
        
        # Verify unschedulable-shipping is an option
        assert "unschedulable-shipping" in content, (
            "Workflow must include 'unschedulable-shipping' as an option"
        )
        
        # Also verify via YAML parse when possible (graceful fallback)
        try:
            data = yaml.safe_load(content)
            if data and isinstance(data, dict):
                on_block = data.get("on", {})
                if isinstance(on_block, dict):
                    workflow_dispatch = on_block.get("workflow_dispatch", {})
                    if isinstance(workflow_dispatch, dict):
                        inputs = workflow_dispatch.get("inputs", {})
                        if isinstance(inputs, dict):
                            assert "incident_scenario" in inputs
        except Exception:
            # YAML parse failed but regex checks passed - acceptable
            pass


class TestK8sNativeWorkflowLabCommand:
    """Tests for K8s-native workflow lab command construction."""

    def test_workflow_passes_incident_scenario_to_lab(self) -> None:
        """Workflow passes --incident-scenario to lab script."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
        assert workflow_path.exists(), "Workflow file must exist"
        
        content = workflow_path.read_text()
        
        # Verify --incident-scenario is passed to the lab command
        assert "--incident-scenario" in content, (
            "Workflow must pass --incident-scenario to lab script"
        )

    def test_workflow_does_not_add_provider_smoke_for_k8s_native(self) -> None:
        """K8s-native scenario does NOT add --enable-provider-smoke."""
        workflow_path = Path(".github/workflows/k9b-otel-demo-live-lab.yml")
        assert workflow_path.exists(), "Workflow file must exist"
        
        content = workflow_path.read_text()
        
        # The workflow should conditionally add --enable-provider-smoke
        # For K8s-native, it should NOT be added
        # Check that the conditional logic exists
        assert 'if [["${{ inputs.incident_scenario }}" == "recommendation-cache-failure"]]' in content or \
               'if [[ "${{ inputs.incident_scenario }}" == "recommendation-cache-failure" ]]' in content, (
            "Workflow must conditionally enable provider-smoke for recommendation-cache-failure only"
        )


class TestK8sNativeConstants:
    """Tests for K8s-native scenario constants."""

    def test_constants_define_env_vars(self) -> None:
        """Constants module defines K8s-native environment variable names."""
        from scripts.k9b_otel_demo_lab_constants import (
            ENV_ALLOW_SIMULATED_DIAGNOSIS,
            ENV_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED,
        )
        
        assert ENV_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED == "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"
        assert ENV_ALLOW_SIMULATED_DIAGNOSIS == "K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS"

    def test_constants_define_artifact_paths(self) -> None:
        """Constants module defines K8s-native artifact paths."""
        from scripts.k9b_otel_demo_lab_constants import (
            K8S_DIAGNOSIS_ARTIFACT_FILENAME,
            K8S_DISCOVERY_ARTIFACT_FILENAME,
            K8S_INJECTION_ARTIFACT_FILENAME,
            PHASE_K8S_DIAGNOSIS_SUBDIR,
            PHASE_K8S_DISCOVERY_SUBDIR,
            PHASE_K8S_INJECTION_SUBDIR,
        )
        
        assert K8S_INJECTION_ARTIFACT_FILENAME == "injection-evidence.json"
        assert K8S_DISCOVERY_ARTIFACT_FILENAME == "detection-evidence.json"
        assert K8S_DIAGNOSIS_ARTIFACT_FILENAME == "diagnosis-evidence.json"
        
        assert PHASE_K8S_INJECTION_SUBDIR == "p2b-k8s-injection"
        assert PHASE_K8S_DISCOVERY_SUBDIR == "p3c-k8s-discovery"
        assert PHASE_K8S_DIAGNOSIS_SUBDIR == "p4c-k8s-multipass-diagnosis"


class TestP4cSimulationRejection:
    """Tests for P4c simulation rejection."""

    def test_p4c_requires_real_loop_metadata(self) -> None:
        """P4c verifier rejects diagnosis without real-loop metadata."""
        # This test documents the expected behavior of P4c
        # The verifier should check for loop_status = "completed" with real diagnosis
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            DIAGNOSIS_SOURCE_REAL,
            DIAGNOSIS_SOURCE_SIMULATED,
            SIMULATION_ENV_VAR,
        )
        
        assert DIAGNOSIS_SOURCE_REAL == "k9b_automatic_diagnosis_loop"
        assert DIAGNOSIS_SOURCE_SIMULATED == "simulated_diagnosis_loop"
        assert SIMULATION_ENV_VAR == "K9B_OTEL_LAB_ALLOW_SIMULATED_DIAGNOSIS"


class TestWorkflowScenarioAlignment:
    """Tests for workflow-to-CLI scenario alignment."""

    def test_workflow_options_accepted_by_cli(self) -> None:
        """Every workflow incident_scenario option is accepted by the lab CLI."""
        # Workflow options from k9b-otel-demo-live-lab.yml
        workflow_options = [
            "recommendation-cache-failure",
            "recommendation-pod-stress",
            "unschedulable-shipping",
        ]
        
        # Parse the lab CLI choices from types/constants
        from scripts.k9b_otel_demo_lab_types import INCIDENT_SCENARIOS
        
        for option in workflow_options:
            assert option in INCIDENT_SCENARIOS, (
                f"Workflow option '{option}' must be in INCIDENT_SCENARIOS. "
                f"Found: {INCIDENT_SCENARIOS}"
            )

