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


def sanitize_kubectl_display_command(command: str | None) -> str | None:
    """Sanitize a kubectl command string intended for operator display.

    Removes internal context markers (--context in-cluster, --context=in-cluster,
    --context in_cluster, --context=in_cluster) from the command string.
    This prevents internal execution mode markers from leaking into operator-facing
    UI fields like worklist titles.

    Preserves real --context values like --context prod-cluster.
    Uses is_real_kube_context() for consistent handling of padded/whitespace values.

    Args:
        command: The kubectl command string to sanitize, or None.

    Returns:
        The sanitized command string, or None if input is None/empty.

    Examples:
        >>> sanitize_kubectl_display_command("kubectl get pods --context in-cluster")
        'kubectl get pods'
        >>> sanitize_kubectl_display_command("kubectl get pods --context=in-cluster")
        'kubectl get pods'
        >>> sanitize_kubectl_display_command("kubectl get pods -n in-cluster")
        'kubectl get pods -n in-cluster'
        >>> sanitize_kubectl_display_command("kubectl get pods --context prod-cluster")
        'kubectl get pods --context prod-cluster'
        >>> sanitize_kubectl_display_command(None)
    """
    if command is None:
        return None
    if not isinstance(command, str) or not command.strip():
        return None
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.strip().split()
    if not tokens:
        return None
    # Pre-check: if no kubectl at start, it's not a kubectl command we manage
    if tokens[0] != "kubectl":
        return command.strip()
    # Strip only INTERNAL context markers (--context in-cluster, etc.)
    # Preserve real --context values like --context prod-cluster
    # Use is_real_kube_context() for consistent handling of padded/whitespace values
    sanitized: list[str] = []
    iterator = iter(tokens)
    for token in iterator:
        if token in ("--context", "-c"):
            next_token = next(iterator, None)
            # Only skip if the next token is NOT a real kube context
            if next_token is not None and not is_real_kube_context(next_token):
                continue  # skip both the flag and the internal value
            # Otherwise, keep both the flag and the real context value
            sanitized.append(token)
            if next_token is not None:
                sanitized.append(next_token)
            continue
        if token.startswith("--context="):
            # Extract context value from --context=value format
            context_value = token.split("=", 1)[1]
            if not is_real_kube_context(context_value):
                continue  # skip this internal context
            sanitized.append(token)
            continue
        if token.startswith("-c="):
            # Extract context value from -c=value format
            context_value = token.split("=", 1)[1]
            if not is_real_kube_context(context_value):
                continue  # skip this internal context
            sanitized.append(token)
            continue
        sanitized.append(token)
    return " ".join(sanitized)
