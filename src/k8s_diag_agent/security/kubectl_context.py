"""Kubernetes context helpers for safe kubectl command construction.

This module provides utilities to safely handle Kubernetes context values
in kubectl commands, distinguishing between:
- Real kubeconfig contexts (legitimate --context values)
- Internal execution mode markers like "in-cluster" (must NOT be passed to kubectl)
"""

from __future__ import annotations

from .path_validation import validate_kube_context_name

# Internal context markers that should NEVER be passed to kubectl
# These are internal execution/discovery modes, not real kubeconfig contexts
_INTERNAL_CONTEXT_MARKERS: frozenset[str] = frozenset({
    "in-cluster",
    "in_cluster",
})


def is_internal_kube_marker(value: str | None) -> bool:
    """Check if a value is an internal K9b execution marker.

    This is used to distinguish between:
    - Internal K9b execution markers like "in-cluster" / "in_cluster"
      (used to label the internal execution context, never a real namespace)
    - Real Kubernetes namespaces and contexts

    Args:
        value: The value to check, or None.

    Returns:
        True if the value is an internal marker that should be removed
        from operator-facing commands.

    Examples:
        >>> is_internal_kube_marker("in-cluster")
        True
        >>> is_internal_kube_marker("in_cluster")
        True
        >>> is_internal_kube_marker("kube-system")
        False
        >>> is_internal_kube_marker(None)
        False
    """
    if value is None:
        return False
    normalized = value.strip()
    return normalized in _INTERNAL_CONTEXT_MARKERS


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

    For real kubeconfig contexts, the context name is validated via validate_kube_context_name()
    to ensure shell metacharacters and other security-sensitive values are rejected.

    Args:
        context: The context value, or None for in-cluster mode.

    Returns:
        A list suitable for concatenating into kubectl command arguments.

    Raises:
        SecurityError: If a real kubeconfig context name contains invalid characters.

    Examples:
        >>> render_kubectl_context_args("my-prod-cluster")
        ['--context', 'my-prod-cluster']
        >>> render_kubectl_context_args("in-cluster")
        []
        >>> render_kubectl_context_args(None)
        []
    """
    if context is not None and is_real_kube_context(context):
        # Validate the context name to prevent shell injection
        validated_context = validate_kube_context_name(context.strip())
        return ["--context", validated_context]
    return []


def sanitize_kubectl_display_command(command: str | None) -> str | None:
    """Sanitize a kubectl command string intended for operator display.

    Removes internal context markers (--context in-cluster, --context=in-cluster,
    --context in_cluster, --context=in_cluster) and internal namespace markers
    (-n in-cluster, --namespace in-cluster, etc.) from the command string.

    In K9b-generated commands, 'in-cluster' as a namespace is an internal marker
    leak, not a real Kubernetes namespace. Both context and namespace internal
    markers are removed to prevent leaks into operator-facing UI fields.

    Preserves real --context values like --context prod-cluster.
    Preserves real namespaces like -n kube-system, -n monitoring.
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
        'kubectl get pods'
        >>> sanitize_kubectl_display_command("kubectl get pods --namespace in-cluster")
        'kubectl get pods'
        >>> sanitize_kubectl_display_command("kubectl get pods -n in-cluster --context in-cluster")
        'kubectl get pods'
        >>> sanitize_kubectl_display_command("kubectl get pods -n kube-system")
        'kubectl get pods -n kube-system'
        >>> sanitize_kubectl_display_command("kubectl get pods --context prod-cluster")
        'kubectl get pods --context prod-cluster'
        >>> sanitize_kubectl_display_command(None)

    Returns None for empty command strings (not empty string).
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
        # Handle --context and -c flags
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
        # Handle -n and --namespace flags
        # In K9b-generated commands, these internal markers as namespaces are leaks,
        # not real Kubernetes namespaces named "in-cluster"
        if token in ("-n", "--namespace"):
            next_token = next(iterator, None)
            # Skip namespace flag and value if the value is an internal marker
            if next_token is not None and is_internal_kube_marker(next_token):
                continue  # skip both the flag and the internal value
            # Otherwise, keep both the flag and the real namespace
            sanitized.append(token)
            if next_token is not None:
                sanitized.append(next_token)
            continue
        if token.startswith("-n="):
            # Extract namespace value from -n=value format
            namespace_value = token.split("=", 1)[1]
            if is_internal_kube_marker(namespace_value):
                continue  # skip this internal marker namespace
            sanitized.append(token)
            continue
        if token.startswith("--namespace="):
            # Extract namespace value from --namespace=value format
            namespace_value = token.split("=", 1)[1]
            if is_internal_kube_marker(namespace_value):
                continue  # skip this internal marker namespace
            sanitized.append(token)
            continue
        sanitized.append(token)
    return " ".join(sanitized)


def display_kube_cluster_label(cluster_name: str | None, context: str | None = None) -> str | None:
    """Get a display label for a cluster that is safe for user-facing text.

    This function ensures internal execution markers like "in-cluster" are not
    used as cluster names in operator-facing prose, LLM prompts, or UI text.

    When the cluster name is an internal marker (e.g., "in-cluster"), this
    function returns None to signal that no valid cluster identity is available.
    Callers should substitute "the cluster" or another neutral fallback.

    Args:
        cluster_name: The cluster name/label, or None.
        context: The Kubernetes execution context (optional). When cluster_name
            is an internal marker, context may be the real cluster identity.

    Returns:
        A safe cluster label for display, or None if the cluster name is
        an internal marker and no real cluster identity is available.

    Examples:
        >>> display_kube_cluster_label("rc-runity-test-msk1-c02", "in-cluster")
        'rc-runity-test-msk1-c02'
        >>> display_kube_cluster_label("in-cluster", "in-cluster")  # No real identity
        >>> display_kube_cluster_label("prod-cluster", "prod-cluster")
        'prod-cluster'
        >>> display_kube_cluster_label(None, None)
        >>> display_kube_cluster_label("in-cluster", "real-context")
        'real-context'
    """
    if cluster_name is None:
        return None

    # If cluster_name is NOT an internal marker, use it directly
    if not is_internal_kube_marker(cluster_name):
        return cluster_name

    # cluster_name IS an internal marker - try context as fallback
    if context is not None and not is_internal_kube_marker(context):
        return context

    # Neither cluster_name nor context provides a real cluster identity
    return None


def sanitize_cluster_prose(cluster_name: str | None, context: str | None = None) -> str:
    """Sanitize cluster references in prose text for user-facing display.

    Replaces internal execution markers like "in-cluster" with neutral
    fallback text ("the cluster") in prose contexts where cluster identity
    appears as a noun phrase.

    This is a defensive fallback for when cluster identity has already
    leaked into prose text that needs to be rendered safely.

    Args:
        cluster_name: The cluster name as it appears in prose, or None.
        context: The Kubernetes execution context (optional).

    Returns:
        A safe cluster reference for prose display.

    Examples:
        >>> sanitize_cluster_prose("rc-runity-test-msk1-c02", "in-cluster")
        'rc-runity-test-msk1-c02'
        >>> sanitize_cluster_prose("in-cluster", "in-cluster")
        'the cluster'
        >>> sanitize_cluster_prose("in-cluster", "real-context")
        'real-context'
        >>> sanitize_cluster_prose(None, None)
        'the cluster'
    """
    display_label = display_kube_cluster_label(cluster_name, context)
    if display_label is None:
        return "the cluster"
    return display_label
