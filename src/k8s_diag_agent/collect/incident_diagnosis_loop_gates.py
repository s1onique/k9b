"""Read-only check gate for the diagnosis loop.

This module provides deterministic check classification:
- Read-only checks: kubectl get, describe, logs, top (allowed by default)
- Mutating checks: kubectl apply, delete, patch, scale, exec (rejected by default)
- Sensitive read checks: kubectl get/describe secret (denied by default)
"""

from __future__ import annotations

# =============================================================================
# Mutating Action Patterns
# =============================================================================

# Patterns that indicate mutating Kubernetes actions
MUTATING_ACTION_PATTERNS: tuple[str, ...] = (
    "kubectl delete",
    "kubectl patch",
    "kubectl apply",
    "kubectl scale",
    "kubectl rollout",
    "kubectl edit",
    "kubectl replace",
    "kubectl create",
    "kubectl label",
    "kubectl annotate",
    "helm install",
    "helm upgrade",
    "helm uninstall",
    "kubectl exec",
    "kubectl port-forward",
    "kubectl debug",
    "kubectl cp",
    "kubectl logs_exec",  # exec into container
    "restart",
    "scale",
    "scale_deployment",
    "restart_deployment",
    "delete_resource",
    "patch_resource",
    "apply_manifest",
)

# Read-only action patterns (allowed by default)
READ_ONLY_ACTION_PATTERNS: tuple[str, ...] = (
    "kubectl get",
    "kubectl describe",
    "kubectl logs",
    "kubectl top",
    "kubectl api-resources",
    "kubectl api-versions",
    "kubectl cluster-info",
    "kubectl version",
    "kubectl config view",
    "kubectl get events",
    "kubectl get pods",
    "kubectl get deployments",
    "kubectl get replicasets",
    "kubectl get services",
    "kubectl get nodes",
    "kubectl get configmaps",
    "kubectl get namespaces",
    "kubectl get pvc",
    "kubectl get pv",
    "kubectl get ingress",
    "kubectl get hpa",
    "kubectl get endpoints",
    "kubectl get statefulset",
    "kubectl get daemonset",
)

# Sensitive read patterns (kubectl get/describe secret)
# These are read-only but potentially expose sensitive data
SENSITIVE_READ_PATTERNS: tuple[str, ...] = (
    "kubectl get secret",
    "kubectl describe secret",
)


def is_mutating_check(check_text: str) -> bool:
    """Check if a check describes a mutating action.

    Args:
        check_text: Check description or command string

    Returns:
        True if the check appears to be mutating
    """
    normalized = check_text.lower()
    for pattern in MUTATING_ACTION_PATTERNS:
        if pattern.lower() in normalized:
            return True
    return False


def is_sensitive_read_check(check_text: str) -> bool:
    """Check if a check describes a sensitive read action.

    Sensitive reads are read-only but may expose secrets or sensitive data.
    Examples: kubectl get secret, kubectl describe secret

    Args:
        check_text: Check description or command string

    Returns:
        True if the check appears to be a sensitive read
    """
    normalized = check_text.lower()
    for pattern in SENSITIVE_READ_PATTERNS:
        if pattern.lower() in normalized:
            return True
    return False


def is_read_only_check(
    check_text: str,
    allow_sensitive_reads: bool = False,
) -> bool:
    """Check if a check describes a read-only action.

    Args:
        check_text: Check description or command string
        allow_sensitive_reads: If True, allow sensitive reads (kubectl get/describe secret)

    Returns:
        True if the check appears to be read-only
    """
    if is_mutating_check(check_text):
        return False

    normalized = check_text.lower()
    
    # Check if it's a sensitive read
    if is_sensitive_read_check(check_text):
        # Only allow if allow_sensitive_reads is True
        return allow_sensitive_reads

    for pattern in READ_ONLY_ACTION_PATTERNS:
        if pattern.lower() in normalized:
            return True

    # Also check for explicitly safe patterns
    safe_patterns = (
        "describe",
        "get ",
        "list ",
        "logs",
        "events",
        "status",
    )
    return any(p in normalized for p in safe_patterns)


__all__ = [
    "MUTATING_ACTION_PATTERNS",
    "READ_ONLY_ACTION_PATTERNS",
    "SENSITIVE_READ_PATTERNS",
    "is_mutating_check",
    "is_sensitive_read_check",
    "is_read_only_check",
]
