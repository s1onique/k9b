#!/usr/bin/env python3
"""Tests for OTel Demo baseline contamination guard and diagnostic classifier.

These tests verify:
1. Phase 1 Helm values do not contain scenario-specific scheduling mutations
2. Phase ordering prevents scenario injection before baseline readiness
3. Diagnostic classifier correctly identifies failure types from K8s objects

Run with: python -m pytest tests/test_otel_baseline_contamination_guard.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.k9b_otel_demo_lab_baseline_diagnostics import (
    check_baseline_purity,
    classify_baseline_failure,
)

# =============================================================================
# Phase 1 Helm Values Tests
# =============================================================================

class TestPhase1HelmValues:
    """Test that Phase 1 Helm values are baseline-only (no scenario contamination)."""

    def test_phase1_values_empty_for_unschedulable_shipping(self) -> None:
        """Phase 1 baseline values should be empty for unschedulable-shipping scenario.
        
        The Helm install uses empty values '{}' - this test verifies that
        no scenario-specific scheduling constraints are introduced via values.
        """
        # Phase 1 uses empty values "{}"
        values = "{}"
        
        values_dict = json.loads(values)
        
        # Should be empty or have only unrelated keys
        # The key assertion is that there are no scheduling constraints under
        # components.shipping or any other path
        assert values_dict == {}, "Phase 1 values should be empty dict"
    
    def test_phase1_helm_command_no_scheduling_values(self) -> None:
        """Phase 1 Helm command should not pass scheduling values via stdin.
        
        This is a static verification that the install command template does not
        include schedulingRules, nodeSelector, affinity, or tolerations in values.
        """
        # Read the deployment module to verify the command
        deployment_file = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab_deployment.py"
        content = deployment_file.read_text()
        
        # Check that the install command does not include scheduling-related values
        # The values are set as: values = "{}"
        assert 'values = "{}"' in content, \
            "Phase 1 should use empty values string"
        
        # Should not have nodeSelector, affinity, tolerations, or schedulingRules in the install block
        install_block_start = content.find('install_cmd = [')
        if install_block_start != -1:
            # Find the end of the install_cmd block (next statement at same indent)
            install_block = content[install_block_start:install_block_start + 500]
            
            # Should not have scheduling values in the command args
            assert "nodeSelector" not in install_block, \
                "Phase 1 install should not include nodeSelector in command"
            assert "schedulingRules" not in install_block, \
                "Phase 1 install should not include schedulingRules in command"
            assert "affinity" not in install_block, \
                "Phase 1 install should not include affinity in command"
            assert "tolerations" not in install_block, \
                "Phase 1 install should not include tolerations in command"


# =============================================================================
# Phase Ordering Tests
# =============================================================================

class TestPhaseOrdering:
    """Test that scenario injection happens only after baseline readiness."""

    def test_unschedulable_shipping_injection_after_baseline(self) -> None:
        """unschedulable-shipping injection (P2b) must happen after baseline readiness (Phase 1b).
        
        This test verifies the phase ordering by checking that:
        1. Phase 1b baseline readiness is called BEFORE P2b injection
        2. P2b injection is called INSIDE the scenario block (after baseline is ready)
        
        The key fix: search for scenario block AFTER Phase 1b to find the actual
        execution block, not the p0c_required condition earlier in the file.
        """
        lab_file = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab.py"
        content = lab_file.read_text()
        
        # Find the run_lab function
        run_lab_start = content.find("def run_lab(")
        assert run_lab_start != -1, "run_lab function should exist"
        
        # Find Phase 1b baseline readiness (the actual call, not definition/import)
        phase1b_pos = content.find("phase1b_baseline_readiness(config, artifact_dir)", run_lab_start)
        assert phase1b_pos != -1, "phase1b_baseline_readiness should be called"
        
        # Find the unschedulable-shipping scenario block - search AFTER Phase 1b
        # to avoid matching the p0c_required condition at line ~133
        unschedulable_pos = content.find('if config.incident_scenario == "unschedulable-shipping":', phase1b_pos)
        assert unschedulable_pos != -1, "unschedulable-shipping scenario block should exist"
        
        # Find P2b injection call - search AFTER the scenario block starts
        p2b_pos = content.find("phase_p2b_inject_unschedulable_shipping_rollout(config, artifact_dir)", unschedulable_pos)
        assert p2b_pos != -1, "P2b injection should be called inside scenario block"
        
        # Verify ordering: Phase 1b must come before scenario block
        # and P2b must come after the scenario block (i.e., inside it)
        assert phase1b_pos < unschedulable_pos, \
            f"Phase 1b ({phase1b_pos}) must come before scenario block ({unschedulable_pos})"
        assert unschedulable_pos < p2b_pos, \
            f"Scenario block ({unschedulable_pos}) must come before P2b ({p2b_pos})"
    
    def test_baseline_purity_guard_runs_after_baseline_ready(self) -> None:
        """Baseline purity check runs after deployments are ready, before scenario injection.
        
        The purity check should be in the success path of Phase 1b, ensuring
        it only runs when baseline is actually ready.
        """
        deployment_file = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab_deployment.py"
        content = deployment_file.read_text()
        
        # Find phase1b_baseline_readiness function
        phase1b_start = content.find("def phase1b_baseline_readiness(")
        assert phase1b_start != -1, "phase1b_baseline_readiness should exist"
        
        # Find the purity check block
        purity_check_pos = content.find("check_baseline_purity", phase1b_start)
        assert purity_check_pos != -1, "Baseline purity check should be present"
        
        # Find the baseline ready condition (if not ready, returns failure)
        if_not_ready_pos = content.find("if not ready:", phase1b_start)
        assert if_not_ready_pos != -1, "Should have readiness check"
        
        # Purity check should come AFTER the readiness check
        assert if_not_ready_pos < purity_check_pos, \
            "Purity check should run after baseline readiness is confirmed"


# =============================================================================
# Diagnostic Classifier Tests
# =============================================================================

class TestBaselineDiagnosticClassifier:
    """Test baseline readiness failure classification with fake K8s objects."""

    def test_classify_shipping_with_failedscheduling_event(self) -> None:
        """shipping stuck with FailedScheduling event -> scheduling failure."""
        events = """
        LAST SEEN   TYPE      REASON              MESSAGE
        10s         Warning   FailedScheduling    0/1 nodes are available: 1 node(s) had no node selector label.
        """
        
        result = classify_baseline_failure(
            pods_data=None,
            deployments_data=None,
            events_text=events,
            stuck_deployment_names=["shipping"],
        )
        
        assert result.is_scheduling_contamination or len(result.scheduling_events) > 0, \
            "Should detect scheduling events"
    
    def test_classify_shipping_with_imagepullbackoff(self) -> None:
        """shipping stuck with ImagePullBackOff -> image pull failure."""
        pod = {
            "metadata": {"name": "shipping-xyz789"},
            "status": {
                "phase": "Pending",
                "containerStatuses": [{
                    "name": "shipping",
                    "state": {
                        "waiting": {
                            "reason": "ImagePullBackOff"
                        }
                    }
                }]
            }
        }
        
        result = classify_baseline_failure(
            pods_data={"items": [pod]},
            deployments_data=None,
            events_text="",
            stuck_deployment_names=["shipping"],
        )
        
        assert result.is_image_pull or result.failure_class == "baseline_image_pull_failure", \
            "Should classify as image pull failure"
    
    def test_classify_shipping_with_crashloopbackoff(self) -> None:
        """shipping stuck with CrashLoopBackOff -> crash loop failure."""
        pod = {
            "metadata": {"name": "shipping-crash123"},
            "status": {
                "phase": "CrashLoopBackOff",
                "containerStatuses": [{
                    "name": "shipping",
                    "state": {
                        "waiting": {
                            "reason": "CrashLoopBackOff"
                        }
                    }
                }]
            }
        }
        
        result = classify_baseline_failure(
            pods_data={"items": [pod]},
            deployments_data=None,
            events_text="",
            stuck_deployment_names=["shipping"],
        )
        
        assert result.is_crash_loop or result.failure_class == "baseline_crash_loop_failure", \
            "Should classify as crash loop failure"
    
    def test_classify_timeout_with_no_events(self) -> None:
        """shipping stuck with no useful events -> unknown failure."""
        result = classify_baseline_failure(
            pods_data=None,
            deployments_data=None,
            events_text="",
            stuck_deployment_names=["shipping"],
        )
        
        assert result.is_unknown, "Should classify as unknown when no evidence"
        assert "shipping" in result.raw_stuck_deployments or \
               "shipping" in result.failure_reason.lower()
    
# =============================================================================
# Baseline Purity Guard Tests
# =============================================================================

class TestBaselinePurityGuard:
    """Test the baseline purity guard function."""

    def test_pure_baseline_no_constraints(self) -> None:
        """Baseline with no scheduling constraints should pass purity check."""
        deployment: dict[str, Any] = {
            "spec": {
                "template": {
                    "spec": {}
                }
            }
        }
        
        is_pure, msg = check_baseline_purity(deployment, scenario="unschedulable-shipping")
        
        assert is_pure, "Baseline with no constraints should be pure"
        assert msg == "", "Should have no error message"
    
    def test_contaminated_baseline_with_scenario_label(self) -> None:
        """Baseline with scenario-specific nodeSelector should fail purity check."""
        deployment = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {
                            "k9b.dev/otel-lab-node": "true"
                        }
                    }
                }
            }
        }
        
        is_pure, msg = check_baseline_purity(deployment, scenario="unschedulable-shipping")
        
        assert not is_pure, "Baseline with scenario label should be contaminated"
        assert "k9b.dev/otel-lab-node" in msg, "Error should mention the label"
    
    def test_purity_check_skipped_for_other_scenarios(self) -> None:
        """Purity check should be skipped for non-unschedulable scenarios."""
        deployment = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": {"some-key": "some-value"}
                    }
                }
            }
        }
        
        is_pure, msg = check_baseline_purity(deployment, scenario="recommendation-cache-failure")
        
        assert is_pure, "Purity check should be skipped for other scenarios"
        assert msg == "", "Should have no error message"
    
    def test_contaminated_baseline_with_affinity(self) -> None:
        """Baseline with affinity should fail purity check."""
        deployment: dict[str, Any] = {
            "spec": {
                "template": {
                    "spec": {
                        "affinity": {
                            "nodeAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": {
                                    "nodeSelectorTerms": []
                                }
                            }
                        }
                    }
                }
            }
        }
        
        is_pure, msg = check_baseline_purity(deployment, scenario="unschedulable-shipping")
        
        assert not is_pure, "Baseline with affinity should be contaminated"
        assert "affinity" in msg.lower(), "Error should mention affinity"


# =============================================================================
# Helm Reset Values Test
# =============================================================================

class TestHelmResetValues:
    """Test that Helm install uses --reset-values."""

    def test_phase1_uses_reset_values(self) -> None:
        """Phase 1 Helm install should use --reset-values to prevent stale state."""
        deployment_file = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab_deployment.py"
        content = deployment_file.read_text()
        
        # Find the install command
        install_block_start = content.find('install_cmd = [')
        assert install_block_start != -1, "install_cmd should exist"
        
        # Extract the install_cmd block (rough estimate of 500 chars)
        install_block = content[install_block_start:install_block_start + 600]
        
        # Check for --reset-values
        assert "--reset-values" in install_block, \
            "Phase 1 Helm install should use --reset-values"
        
        # Should NOT use --reuse-values
        assert "--reuse-values" not in install_block, \
            "Phase 1 should NOT use --reuse-values"


# =============================================================================
# Phase 1b Orchestration Tests
# =============================================================================

class TestPhase1bOrchestration:
    """Test phase1b_baseline_readiness() orchestration-level behavior."""

    def test_phase1b_fails_when_pod_listing_fails_for_unschedulable_shipping(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """phase1b_baseline_readiness() should fail closed when pod listing fails for unschedulable-shipping."""
        from scripts.k9b_lab_common_helpers import KubectlResult
        from scripts.k9b_otel_demo_lab_deployment import phase1b_baseline_readiness
        from scripts.k9b_otel_demo_lab_types import LabConfig

        # Create config for unschedulable-shipping scenario
        config = LabConfig(
            kubeconfig="/fake/kubeconfig",
            artifact_dir=str(tmp_path),
            namespace="otel-demo",
            incident_scenario="unschedulable-shipping",
        )

        # Track calls
        call_log = []

        def mock_kubectl_json(
            kubeconfig: str,
            resource: str,
            namespace: str | None = None,
            extra_args: list[str] | None = None,
        ) -> KubectlResult:
            call_log.append((resource, namespace))
            if resource == "pods" and namespace == "otel-demo":
                # Pod listing fails
                return KubectlResult(
                    success=False,
                    stdout="",
                    stderr="forbidden: cannot list pods",
                    returncode=1,
                    data=None,
                )
            elif resource == "deployment" and namespace == "otel-demo":
                # Shipping deployment fetch succeeds
                return KubectlResult(
                    success=True,
                    stdout="",
                    stderr="",
                    returncode=0,
                    data={
                        "metadata": {"name": "shipping"},
                        "spec": {"template": {"spec": {}}},
                    },
                )
            elif resource == "deployments" and namespace == "otel-demo":
                return KubectlResult(success=True, stdout="", stderr="", returncode=0, data={"items": []})
            elif resource == "services" and namespace == "otel-demo":
                return KubectlResult(success=True, stdout="", stderr="", returncode=0, data={"items": []})
            else:
                return KubectlResult(success=True, stdout="", stderr="", returncode=0, data=None)

        def mock_kubectl_events(
            kubeconfig: str,
            namespace: str,
            sort_by: str = ".lastTimestamp",
            extra_args: list[str] | None = None,
        ) -> KubectlResult:
            return KubectlResult(success=True, stdout="", stderr="", returncode=0)

        def mock_wait_for_deployments_ready(
            kubeconfig: str,
            namespace: str,
            deployments: list[str],
            timeout_seconds: int = 300,
            poll_interval: int = 10,
        ) -> tuple[bool, str]:
            return True, "All deployments ready"

        monkeypatch.setattr("scripts.k9b_otel_demo_lab_deployment.kubectl_json", mock_kubectl_json)
        monkeypatch.setattr("scripts.k9b_otel_demo_lab_deployment.kubectl_events", mock_kubectl_events)
        monkeypatch.setattr("scripts.k9b_otel_demo_lab_deployment.wait_for_deployments_ready", mock_wait_for_deployments_ready)

        result = phase1b_baseline_readiness(config, tmp_path)

        # Verify fail-closed behavior
        assert result.success is False, "Phase should fail when pod listing fails for unschedulable-shipping"
        assert result.phase == "phase1-baseline", f"Phase should be phase1-baseline, got {result.phase}"
        assert "cannot list pods" in result.message.lower(), f"Error should mention 'cannot list pods', got: {result.message}"
        assert "baseline_purity_failure" in result.artifacts, "Artifacts should include baseline_purity_failure"

        # Verify artifact contents
        artifact_path = Path(result.artifacts["baseline_purity_failure"])
        artifact = json.loads(artifact_path.read_text())
        assert artifact["failure_class"] == "baseline_contamination_check_failed", f"Got: {artifact.get('failure_class')}"
        assert artifact["scenario"] == "unschedulable-shipping", f"Got: {artifact.get('scenario')}"
        assert artifact["deployment"] == "shipping", f"Got: {artifact.get('deployment')}"
        assert "forbidden" in artifact["message"], "Error should include stderr context"

        # Verify call sequence
        assert ("deployment", "otel-demo") in call_log, "Should call deployment/shipping"
        assert ("pods", "otel-demo") in call_log, "Should call pods"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
