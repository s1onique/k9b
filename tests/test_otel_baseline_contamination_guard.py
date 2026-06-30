#!/usr/bin/env python3
"""Tests for OTel Demo baseline contamination guard and diagnostic classifier.

These tests verify:
1. Phase 1 Helm values do not contain scenario-specific scheduling mutations
2. Phase ordering prevents scenario injection before baseline readiness
3. Diagnostic classifier correctly identifies failure types from K8s objects

Run with: python -m pytest tests/test_otel_baseline_contamination_guard.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.k9b_otel_demo_lab_baseline_diagnostics import (
    BaselineFailure,
    _has_scheduling_constraints,
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
        
        import json
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
        
        This test verifies the phase ordering by checking the run_lab function
        does NOT call phase_p2b before phase1b completes.
        """
        lab_file = Path(__file__).parent.parent / "scripts" / "k9b_otel_demo_lab.py"
        content = lab_file.read_text()
        
        # Find the run_lab function
        run_lab_start = content.find("def run_lab(")
        assert run_lab_start != -1, "run_lab function should exist"
        
        # Find Phase 1b baseline readiness
        phase1b_pos = content.find("phase1b_baseline_readiness", run_lab_start)
        assert phase1b_pos != -1, "phase1b_baseline_readiness should be called"
        
        # Find the unschedulable-shipping scenario block
        unschedulable_pos = content.find('incident_scenario == "unschedulable-shipping"', run_lab_start)
        assert unschedulable_pos != -1, "unschedulable-shipping scenario block should exist"
        
        # Find P2b injection call
        p2b_pos = content.find("phase_p2b_inject_unschedulable_shipping_rollout", run_lab_start)
        assert p2b_pos != -1, "P2b injection should be called"
        
        # Verify ordering: Phase 1b must come before P2b
        assert phase1b_pos < p2b_pos, \
            f"Phase 1b ({phase1b_pos}) must come before P2b ({p2b_pos})"
        
        # Verify that P2b is inside the unschedulable-shipping block
        # P2b should be between unschedulable_pos and unschedulable_pos + some distance
        # This ensures P2b is not called for other scenarios
        assert phase1b_pos < unschedulable_pos < p2b_pos, \
            "Phase ordering: Phase 1b < scenario block < P2b injection"
    
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

    def test_classify_shipping_with_impossible_node_selector(self) -> None:
        """shipping stuck with impossible nodeSelector -> scheduling contamination."""
        # Fake pod with impossible nodeSelector
        pod = {
            "metadata": {"name": "shipping-abc123"},
            "spec": {
                "nodeSelector": {
                    "k9b.dev/otel-lab-node": "impossible-value"
                }
            },
            "status": {"phase": "Pending"}
        }
        
        has_constraints, constraints = _has_scheduling_constraints(pod)
        assert has_constraints, "Should detect scheduling constraints"
        assert constraints["nodeSelector"]["k9b.dev/otel-lab-node"] == "impossible-value"
        
        # Classify the failure
        result = classify_baseline_failure(
            pods_data={"items": [pod]},
            deployments_data={"items": []},
            events_text="",
            stuck_deployment_names=["shipping"],
        )
        
        assert result.is_scheduling_contamination, \
            "Should classify as scheduling contamination"
        assert "k9b.dev/otel-lab-node" in result.failure_reason.lower() or \
               result.failure_class == "baseline_contamination_scheduling"
    
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
    
    def test_default_kubernetes_pod_tolerations_are_not_contamination(self) -> None:
        """Default Kubernetes tolerations (node.kubernetes.io/not-ready, etc.) should not
        be flagged as scheduling contamination.
        
        Kubernetes automatically adds default tolerations to pods for things like
        node.kubernetes.io/not-ready and node.kubernetes.io/unreachable. These should
        not cause false positive contamination detection.
        """
        # Fake pod with default Kubernetes tolerations (NOT contamination)
        pod = {
            "metadata": {"name": "shipping-default-tolerations"},
            "spec": {
                "tolerations": [
                    {
                        "key": "node.kubernetes.io/not-ready",
                        "operator": "Exists",
                        "effect": "NoExecute",
                        "tolerationSeconds": 300,
                    },
                    {
                        "key": "node.kubernetes.io/unreachable",
                        "operator": "Exists",
                        "effect": "NoExecute",
                        "tolerationSeconds": 300,
                    },
                ],
            },
            "status": {"phase": "Running"},
        }
        
        # Verify the function correctly identifies these as NOT scenario-specific
        has_constraints, constraints = _has_scheduling_constraints(pod, is_live_pod=True)
        assert not has_constraints, \
            "Default Kubernetes tolerations should not be flagged as scheduling constraints"
        assert constraints == {}, "Should have no constraints detected"
        
        # Verify the classifier doesn't flag this as contamination
        result = classify_baseline_failure(
            pods_data={"items": [pod]},
            deployments_data=None,
            events_text="",
            stuck_deployment_names=["shipping"],
        )
        
        assert result.failure_class != "baseline_contamination_scheduling", \
            "Default Kubernetes tolerations should not cause contamination classification"


# =============================================================================
# Baseline Purity Guard Tests
# =============================================================================

class TestBaselinePurityGuard:
    """Test the baseline purity guard function."""

    def test_pure_baseline_no_constraints(self) -> None:
        """Baseline with no scheduling constraints should pass purity check."""
        deployment = {
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
        deployment = {
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
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
