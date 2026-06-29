#!/usr/bin/env python3
"""Cleanup and rollback functions for K8s incident injection.

This module handles cleanup of the unschedulable shipping rollout injection,
including nodeSelector restoration and deployment rollback.
"""

from __future__ import annotations

import time

from scripts.k9b_lab_common_helpers import kubectl_patch, log
from scripts.k9b_otel_demo_lab_constants import SHIPPING_DEPLOYMENT

from .k9b_otel_demo_lab_k8s_injection_helpers import _kubectl_scale


def cleanup_unschedulable_shipping_rollout(
    kubeconfig: str,
    namespace: str,
    previous_node_selector: dict[str, str] | None,
    original_replicas: int,
) -> bool:
    """Cleanup the unschedulable shipping rollout injection.
    
    Restores the deployment nodeSelector to its previous state and scales to original replicas.
    Uses JSON Patch to precisely restore or remove the nodeSelector.
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where deployment exists
        previous_node_selector: The previous nodeSelector value (None if no previous selector)
        original_replicas: The original replica count
        
    Returns:
        True if cleanup succeeded, False otherwise
    """
    log("Cleaning up unschedulable shipping rollout injection...")
    
    # Scale to 0 first to stop scheduling attempts
    log("Step 1: Scaling deployment to 0...")
    scale_result = _kubectl_scale(kubeconfig, namespace, SHIPPING_DEPLOYMENT, 0)
    if not scale_result.success:
        log(f"Cleanup warning: Failed to scale to 0: {scale_result.stderr}")
        return False
    
    time.sleep(5)
    
    # Step 2: Restore nodeSelector using JSON Patch
    log("Step 2: Restoring nodeSelector...")
    patch_success = _restore_node_selector(kubeconfig, namespace, previous_node_selector)
    if not patch_success:
        log("Cleanup failed: Could not restore nodeSelector")
        log(f"Manual recovery: kubectl rollout undo deployment/{SHIPPING_DEPLOYMENT} -n {namespace}")
        return False
    
    time.sleep(5)
    
    # Step 3: Scale back to original replicas
    log(f"Step 3: Scaling deployment to {original_replicas}...")
    scale_result = _kubectl_scale(kubeconfig, namespace, SHIPPING_DEPLOYMENT, original_replicas)
    if not scale_result.success:
        log(f"Cleanup warning: Failed to scale to {original_replicas}: {scale_result.stderr}")
        return False
    
    log("Cleanup complete: deployment restored")
    return True


def _restore_node_selector(
    kubeconfig: str,
    namespace: str,
    previous_node_selector: dict[str, str] | None,
) -> bool:
    """Restore the nodeSelector using JSON Patch.
    
    Uses JSON Patch operations to precisely add/remove/replace nodeSelector:
    - If previous was None: remove /spec/template/spec/nodeSelector
    - If previous was present: replace /spec/template/spec/nodeSelector
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace
        previous_node_selector: Previous nodeSelector or None to remove
        
    Returns:
        True if patch succeeded
    """
    if previous_node_selector is None:
        # No previous selector - remove it
        patch: list[dict[str, str | dict[str, str]]] = [
            {"op": "remove", "path": "/spec/template/spec/nodeSelector"}
        ]
    else:
        # Restore previous selector - value must remain a dict
        patch = [
            {"op": "replace", "path": "/spec/template/spec/nodeSelector", "value": previous_node_selector}
        ]
    
    result = kubectl_patch(
        kubeconfig,
        "deployment",
        SHIPPING_DEPLOYMENT,  # name
        namespace,  # namespace
        patch,  # JSON Patch must be a list of operations
        patch_type="json",  # Use JSON Patch mode
    )
    
    if not result.success:
        # JSON Patch remove can fail if path already absent - treat as success if selector was already gone
        if previous_node_selector is None and "not found" in result.stderr.lower():
            log("NodeSelector already absent - cleanup considered successful")
            return True
        log(f"Failed to restore nodeSelector: {result.stderr}")
        return False
    
    log("NodeSelector restored successfully")
    return True


def _rollback_deployment(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    previous_node_selector: dict[str, str] | None,
    replicas: int,
) -> None:
    """Attempt to rollback a deployment to previous state."""
    log("Attempting rollback...")
    success = cleanup_unschedulable_shipping_rollout(
        kubeconfig,
        namespace,
        previous_node_selector,
        replicas,
    )
    if not success:
        log("Rollback failed - manual intervention may be required")
        log(f"Run: kubectl rollout undo deployment/{deployment} -n {namespace}")
