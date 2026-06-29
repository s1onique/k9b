#!/usr/bin/env python3
"""Main injection phase for K8s incident injection.

This module contains the main phase function that orchestrates
the P2b injection workflow.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from scripts.k9b_lab_common_helpers import (
    kubectl_json,
    kubectl_patch,
    log,
    write_json_artifact,
)
from scripts.k9b_otel_demo_lab_constants import (
    K8S_INJECTION_NODE_SELECTOR_KEY,
    K8S_INJECTION_NODE_SELECTOR_VALUE,
    PHASE_INJECTED,
    SHIPPING_DEPLOYMENT,
)
from scripts.k9b_otel_demo_lab_k8s_injection_cleanup import _rollback_deployment
from scripts.k9b_otel_demo_lab_k8s_injection_helpers import (
    _extract_node_selector,
    _extract_pod_template,
    _fail_phase,
    _kubectl_scale,
    _write_injection_artifacts,
)
from scripts.k9b_otel_demo_lab_k8s_injection_polling import _poll_for_symptoms
from scripts.k9b_otel_demo_lab_k8s_injection_types import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from scripts.k9b_otel_demo_lab_types import LabConfig, LabPhaseResult


def phase_p2b_inject_unschedulable_shipping_rollout(
    config: LabConfig, artifact_dir: Path
) -> LabPhaseResult:
    """Phase P2b: Inject unschedulable shipping rollout incident.
    
    This phase:
    1. Captures the current shipping deployment pod template
    2. Scales shipping deployment to 0 to remove existing pods
    3. Patches the deployment with an impossible nodeSelector
    4. Scales back to 1 to trigger a new rollout
    5. Polls for evidence of Pending/FailedScheduling symptoms
    6. Writes artifacts for later verification
    
    Args:
        config: Lab configuration
        artifact_dir: Directory for phase artifacts
        
    Returns:
        LabPhaseResult with injection outcome and artifacts
    """
    start = time.time()
    phase_dir = artifact_dir / PHASE_INJECTED
    phase_dir.mkdir(parents=True, exist_ok=True)
    
    injection_dir = phase_dir / "p2b-k8s-injection"
    injection_dir.mkdir(parents=True, exist_ok=True)
    
    log("=" * 60)
    log("PHASE P2b: Inject unschedulable shipping rollout")
    log("=" * 60)
    log(f"Target: deployment/{SHIPPING_DEPLOYMENT} in {config.namespace}")
    log(f"Method: impossible nodeSelector ({K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE})")
    
    evidence: dict[str, Any] = {
        "scenario": "unschedulable-shipping-rollout",
        "method": "nodeSelector_patch",
        "deployment": SHIPPING_DEPLOYMENT,
        "namespace": config.namespace,
        "node_selector": {
            K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
        },
        "timestamp": time.time(),
    }
    
    # Step 1: Capture current deployment state
    log("Step 1: Capturing current deployment state...")
    deployment_result = kubectl_json(
        config.kubeconfig,
        "deployment",
        config.namespace,
        extra_args=[SHIPPING_DEPLOYMENT, "-o", "json"],
    )
    
    if not deployment_result.success or not deployment_result.data:
        error_msg = f"Failed to get deployment {SHIPPING_DEPLOYMENT}: {deployment_result.stderr}"
        log(error_msg)
        evidence["error"] = error_msg
        _write_injection_artifacts(injection_dir, evidence, None)
        return _fail_phase(phase_dir, start, error_msg, evidence)
    
    current_deployment = deployment_result.data
    previous_template = _extract_pod_template(current_deployment)
    previous_node_selector = _extract_node_selector(previous_template)
    evidence["previous_replicas"] = current_deployment.get("spec", {}).get("replicas", 1)
    evidence["previous_template_path"] = str(injection_dir / "previous-pod-template.json")
    evidence["previous_node_selector"] = previous_node_selector
    write_json_artifact(injection_dir, "previous-pod-template.json", previous_template)
    write_json_artifact(injection_dir, "previous-node-selector.json", {"node_selector": previous_node_selector})
    
    log(f"Captured deployment with {evidence['previous_replicas']} replicas")
    log(f"Previous nodeSelector: {previous_node_selector}")
    
    # Step 2: Scale to 0 to remove existing pods
    log("Step 2: Scaling deployment to 0...")
    scale_result = _kubectl_scale(config.kubeconfig, config.namespace, SHIPPING_DEPLOYMENT, 0)
    if not scale_result.success:
        error_msg = f"Failed to scale deployment to 0: {scale_result.stderr}"
        log(error_msg)
        evidence["error"] = error_msg
        _write_injection_artifacts(injection_dir, evidence, previous_template)
        return _fail_phase(phase_dir, start, error_msg, evidence)
    
    log("Waiting for pods to terminate...")
    time.sleep(10)
    
    # Step 3: Patch deployment with impossible nodeSelector
    log("Step 3: Patching deployment with impossible nodeSelector...")
    patch_manifest = {
        "spec": {
            "template": {
                "spec": {
                    "nodeSelector": {
                        K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
                    }
                }
            }
        }
    }
    patch_result = kubectl_patch(
        config.kubeconfig,
        "deployment",
        SHIPPING_DEPLOYMENT,
        config.namespace,
        patch_manifest,
    )
    
    if not patch_result.success:
        error_msg = f"Failed to patch deployment: {patch_result.stderr}"
        log(error_msg)
        evidence["error"] = error_msg
        _write_injection_artifacts(injection_dir, evidence, previous_template)
        # Attempt rollback
        _rollback_deployment(config.kubeconfig, config.namespace, SHIPPING_DEPLOYMENT, previous_node_selector, evidence["previous_replicas"])
        return _fail_phase(phase_dir, start, error_msg, evidence)
    
    evidence["patch_applied"] = True
    evidence["patch_path"] = str(injection_dir / "injection-patch.json")
    write_json_artifact(injection_dir, "injection-patch.json", patch_manifest)
    
    log(f"Patch applied: {K8S_INJECTION_NODE_SELECTOR_KEY}={K8S_INJECTION_NODE_SELECTOR_VALUE}")
    
    # Step 4: Scale back to 1 to trigger rollout
    log("Step 4: Scaling deployment to 1...")
    scale_result = _kubectl_scale(config.kubeconfig, config.namespace, SHIPPING_DEPLOYMENT, 1)
    if not scale_result.success:
        error_msg = f"Failed to scale deployment to 1: {scale_result.stderr}"
        log(error_msg)
        evidence["error"] = error_msg
        _write_injection_artifacts(injection_dir, evidence, previous_template)
        _rollback_deployment(config.kubeconfig, config.namespace, SHIPPING_DEPLOYMENT, previous_node_selector, 1)
        return _fail_phase(phase_dir, start, error_msg, evidence)
    
    log("Deployment scaled to 1, waiting for pod scheduling...")
    
    # Step 5: Poll for symptom evidence
    log("Step 5: Polling for symptom evidence...")
    poll_result = _poll_for_symptoms(
        config.kubeconfig,
        config.namespace,
        SHIPPING_DEPLOYMENT,
        injection_dir,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        poll_interval=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    
    evidence["poll_result"] = poll_result
    
    if poll_result["symptom_found"]:
        log(f"Symptom detected: {poll_result['symptom_type']}")
        evidence["symptom_found"] = True
        evidence["symptom_type"] = poll_result["symptom_type"]
    else:
        log("ERROR: No symptom detected within timeout - fail-closed")
        evidence["symptom_found"] = False
        evidence["failure_reason"] = "k8s_injection_no_symptom"
        evidence["warning"] = "No Pending/FailedScheduling evidence found within timeout"
        
        # Write failure evidence
        write_json_artifact(injection_dir, "failure-evidence.json", {
            "failure": "k8s_injection_no_symptom",
            "reason": "No symptom observed within timeout",
            "poll_result": poll_result,
        })
        
        # Phase fails closed - return failure result
        duration = time.time() - start
        _write_injection_artifacts(injection_dir, evidence, previous_template)
        
        return LabPhaseResult(
            phase="p2b-k8s-injection",
            success=False,
            message="Injection failed: no symptom observed (fail-closed)",
            artifacts={
                "injection_dir": str(injection_dir),
                "previous_template": str(injection_dir / "previous-pod-template.json"),
                "symptom_evidence": str(injection_dir / "symptom-evidence.json"),
                "symptom_found": False,
                "failure": "k8s_injection_no_symptom",
            },
            duration_seconds=duration,
        )
    
    # Step 6: Write final evidence
    evidence["symptom_evidence_path"] = str(injection_dir / "symptom-evidence.json")
    write_json_artifact(injection_dir, "symptom-evidence.json", poll_result)
    
    # Write injection command artifact for verification
    injection_cmd = {
        "command": "Inject unschedulable shipping rollout",
        "method": "nodeSelector_patch",
        "deployment": SHIPPING_DEPLOYMENT,
        "namespace": config.namespace,
        "nodeSelector": {
            K8S_INJECTION_NODE_SELECTOR_KEY: K8S_INJECTION_NODE_SELECTOR_VALUE,
        },
    }
    evidence["injection_command_path"] = str(injection_dir / "injection-command.json")
    write_json_artifact(injection_dir, "injection-command.json", injection_cmd)
    
    # Write cleanup command artifact
    cleanup_cmd = {
        "command": "Cleanup unschedulable shipping rollout",
        "method": "restore_previous_template",
        "deployment": SHIPPING_DEPLOYMENT,
        "namespace": config.namespace,
        "previous_template_path": str(injection_dir / "previous-pod-template.json"),
    }
    evidence["cleanup_command_path"] = str(injection_dir / "cleanup-command.json")
    write_json_artifact(injection_dir, "cleanup-command.json", cleanup_cmd)
    
    duration = time.time() - start
    
    log("=" * 60)
    log("PHASE P2b: Injection complete")
    log(f"  Success: {poll_result['symptom_found']}")
    log(f"  Symptom: {poll_result.get('symptom_type', 'none')}")
    log(f"  Duration: {duration:.1f}s")
    log("=" * 60)
    
    return LabPhaseResult(
        phase="p2b-k8s-injection",
        success=True,
        message=f"K8s-native incident injected: {poll_result.get('symptom_type', 'symptoms pending')}",
        artifacts={
            "injection_dir": str(injection_dir),
            "previous_template": str(injection_dir / "previous-pod-template.json"),
            "symptom_evidence": str(injection_dir / "symptom-evidence.json"),
            "symptom_found": poll_result["symptom_found"],
            "symptom_type": poll_result.get("symptom_type"),
        },
        duration_seconds=duration,
    )
