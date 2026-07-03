#!/usr/bin/env python3
"""Cleanup and rollback functions for K8s incident injection.

This module handles cleanup of the unschedulable shipping rollout injection,
including nodeSelector restoration and deployment rollback.
"""

from __future__ import annotations

import time

from scripts.k9b_lab_common_helpers import kubectl_json, kubectl_patch, log
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


def reset_shipping_node_selector(
    kubeconfig: str,
    namespace: str,
) -> bool:
    """Reset shipping deployment nodeSelector to clean schedulable state (lab-start preflight).

    This is an idempotent preflight reset that clears any leftover nodeSelector from
    previous lab runs before the scenario injection phase. It ensures every run starts
    from a clean schedulable state.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace where shipping deployment exists (default: otel-demo)

    Returns:
        True if reset succeeded or deployment doesn't exist yet (skip).
        False if reset failed for a real error (fail-closed for contamination scenarios).

    Behavior:
        - If shipping deployment does NOT exist: returns True (skip - not an error)
        - If nodeSelector is already absent: returns True (idempotent success)
        - If nodeSelector is present: patches to null, waits for rollout, returns True
        - If patch fails for a real error: returns False (fail-closed)
    """
    # Check if deployment exists first
    deploy_result = kubectl_json(
        kubeconfig,
        "deployment",
        namespace,
        extra_args=[SHIPPING_DEPLOYMENT, "-o", "json"],
    )

    if not deploy_result.success:
        # Deployment doesn't exist yet - this is OK for early preflight
        log(f"shipping deployment not present yet ({namespace}/{SHIPPING_DEPLOYMENT}); skipping nodeSelector reset")
        return True

    log(f"Resetting {namespace}/{SHIPPING_DEPLOYMENT} nodeSelector to clean schedulable state")

    # Use merge patch to set nodeSelector to null (clears it)
    patch_result = kubectl_patch(
        kubeconfig,
        "deployment",
        SHIPPING_DEPLOYMENT,
        namespace,
        patch={"spec": {"template": {"spec": {"nodeSelector": None}}}},
        patch_type="merge",
    )

    if not patch_result.success:
        # Check if the error indicates nodeSelector is already absent (idempotent case)
        if _is_json_patch_path_absent_error(patch_result.stderr or ""):
            log("nodeSelector already absent - reset idempotent, considered successful")
            return True
        log(f"Failed to reset nodeSelector: {patch_result.stderr}")
        return False

    # Wait for rollout to complete
    log("Waiting for rollout to complete...")
    rollout_result = _wait_for_rollout(kubeconfig, namespace, SHIPPING_DEPLOYMENT, timeout=120)
    if not rollout_result:
        log("WARNING: Rollout status check failed, but nodeSelector was patched successfully")
        # Don't fail closed here - the patch succeeded, just rollout status timed out
        return True

    log("nodeSelector reset completed successfully")
    return True


def _wait_for_rollout(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    timeout: int = 120,
) -> bool:
    """Wait for deployment rollout to complete.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: Namespace
        deployment: Deployment name
        timeout: Timeout in seconds

    Returns:
        True if rollout completed within timeout, False otherwise
    """
    import subprocess

    cmd = [
        "kubectl",
        "--kubeconfig", kubeconfig,
        "rollout", "status",
        f"deployment/{deployment}",
        "--namespace", namespace,
        f"--timeout={timeout}s",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0
