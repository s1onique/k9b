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


def _is_json_patch_path_absent_error(stderr: str) -> bool:
    """Check if stderr indicates a JSON Patch path is already absent.
    
    This function distinguishes between:
    - JSON Patch "remove" path already absent (idempotent success case)
    - Missing Kubernetes resource (real failure that should not be swallowed)
    
    Acceptable patterns for path-absent:
    - Path references to nodeSelector path
    - "missing path" or "doc is missing path" wording
    - "remove operation does not apply" wording
    
    NOT acceptable (would hide real failures):
    - Generic "not found" without path context
    - Resource names like "shipping" or "deployment"
    
    Args:
        stderr: The stderr output from kubectl patch
        
    Returns:
        True if stderr indicates path-absent, False otherwise
    """
    if not stderr:
        return False
    
    stderr_lower = stderr.lower()
    
    # Path-specific patterns that indicate the JSON Patch path is absent
    path_indicators = [
        "/spec/template/spec/nodeselector",  # The exact path we're removing
        "spec.template.spec.nodeselector",  # Path without slashes
        "missing path",  # JSON Patch standard message
        "doc is missing path",  # Another form of missing path
        "remove operation does not apply",  # JSON Patch spec message
    ]
    
    for indicator in path_indicators:
        if indicator in stderr_lower:
            return True
    
    # Check for "doesn't exist" or "does not exist" ONLY when paired with path context
    if "doesn't exist" in stderr_lower or "does not exist" in stderr_lower:
        # Must have path context, not just resource name
        # e.g., "/spec/template/spec/nodeSelector doesn't exist" - good
        # e.g., "deployments.apps \"shipping\" not found" - bad
        if any(p in stderr_lower for p in path_indicators):
            return True
        # Also accept "path doesn't exist" pattern
        if "path" in stderr_lower and ("doesn't exist" in stderr_lower or "does not exist" in stderr_lower):
            return True
    
    return False


def _restore_node_selector(
    kubeconfig: str,
    namespace: str,
    previous_node_selector: dict[str, str] | None,
) -> bool:
    """Restore the nodeSelector using JSON Patch.
    
    Uses JSON Patch operations to precisely add/remove/replace nodeSelector:
    - If previous was None: remove /spec/template/spec/nodeSelector
    - If previous was present: replace /spec/template/spec/nodeSelector
    
    This function is idempotent: if the nodeSelector path is already absent
    (e.g., from a previous cleanup run), the operation succeeds.
    
    Fail-closed for:
    - Missing deployment resource
    - Missing namespace
    - Network/auth errors
    - Other kubectl failures
    
    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace
        previous_node_selector: Previous nodeSelector or None to remove
        
    Returns:
        True if patch succeeded (including idempotent success when path already absent)
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
        # JSON Patch remove can fail when path is already absent
        # This is expected when cleanup runs multiple times
        # Treat as success (idempotent behavior) only for path-absent errors
        if previous_node_selector is None and _is_json_patch_path_absent_error(result.stderr or ""):
            log("NodeSelector path already absent - cleanup idempotent, considered successful")
            return True
        # For replace operations or other errors, fail closed
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
