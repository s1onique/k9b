"""Kubernetes context helpers for safe kubectl command construction.

This module provides utilities to safely handle Kubernetes context values
in kubectl commands, distinguishing between:
- Real kubeconfig contexts (legitimate --context values)
- Internal execution mode markers like "in-cluster" (must NOT be passed to kubectl)
"""

from __future__ import annotations

# Internal context markers that should NEVER be passed to kubectl
# These are internal execution/discovery modes, not real kubeconfig contexts
_INTERNAL_CONTEXT_MARKERS: frozenset[str] = frozenset({
    "in-cluster",
    "in_cluster",
})


def is_real_kube_context(context: str | None) -> bool:
    """Check if a context value is a real kubeconfig context.

    Args:
        context: The context value to check, or None.

    Returns:
        True if the context is a real kubeconfig context that can be
        safely passed to kubectl --context flag.

    Examples:
        >>> is_real_kube_context("my-prod-cluster")
        True
        >>> is_real_kube_context("admin@prod")
        True
        >>> is_real_kube_context("in-cluster")
        False
        >>> is_real_kube_context(None)
        False
    """
    if context is None:
        return False
    normalized = context.strip()
    if not normalized:
        return False
    return normalized not in _INTERNAL_CONTEXT_MARKERS


def render_kubectl_context_args(context: str | None) -> list[str]:
    """Return kubectl --context arguments based on context value.

    This function safely handles the difference between:
    - In-cluster mode: returns [] (no --context flag needed, kubectl uses service account)
    - Real kubeconfig context: returns ["--context", "<name>"]

    Args:
        context: The context value, or None for in-cluster mode.

    Returns:
        A list suitable for concatenating into kubectl command arguments.

    Examples:
        >>> render_kubectl_context_args("my-prod-cluster")
        ['--context', 'my-prod-cluster']
        >>> render_kubectl_context_args("in-cluster")
        []
        >>> render_kubectl_context_args(None)
        []
    """
    if context is not None and is_real_kube_context(context):
        return ["--context", context]
    return []
