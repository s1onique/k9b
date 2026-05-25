"""Command validation and construction helpers for manual next-check execution."""

from __future__ import annotations

import shlex
from collections.abc import Sequence

from ..security.kubectl_context import (
    is_internal_kube_marker,
    render_kubectl_context_args,
)
from ..security.path_validation import (
    SecurityError,
    validate_kube_context_name,
    validate_kubernetes_namespace,
    validate_kubernetes_resource_name,
)
from .next_check_planner import MUTATION_KEYWORDS, BlockingReason, CommandFamily

_DANGEROUS_CHARS = frozenset({";", "&&", "||", "|", "<", ">", "$", "`"})


class ManualNextCheckError(RuntimeError):
    """Raised when a manual next-check execution is not allowed."""

    def __init__(self, message: str, *, blocking_reason: BlockingReason | None = None) -> None:
        super().__init__(message)
        self.blocking_reason = blocking_reason


def _strip_context_arguments(tokens: Sequence[str]) -> tuple[str, ...]:
    """Strip context and internal namespace markers from tokens.

    This function removes:
    - --context and -c flags with their values (when internal marker)
    - -n and --namespace flags with internal marker values (like "in-cluster")
    """
    sanitized: list[str] = []
    iterator = iter(tokens)
    for token in iterator:
        # Handle --context and -c flags
        if token in ("--context", "-c"):
            next(iterator, None)
            continue
        if token.startswith("--context=") or token.startswith("-c="):
            continue
        # Handle -n and --namespace flags with internal marker values
        if token in ("-n", "--namespace"):
            next_token = next(iterator, None)
            # Skip namespace flag and value if it's an internal marker
            if next_token is not None and is_internal_kube_marker(next_token):
                continue
            # Keep both flag and namespace for real namespaces
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
    return tuple(sanitized)


def _validate_command_tokens(family: CommandFamily, tokens: Sequence[str]) -> None:
    """Validate command tokens for security and correctness."""
    if not tokens:
        raise ManualNextCheckError("Command text must include a kubectl subcommand.")
    subcommand = tokens[0]
    if family == CommandFamily.KUBECTL_LOGS and subcommand != "logs":
        raise ManualNextCheckError("Logs candidate must use `kubectl logs`.")
    if family == CommandFamily.KUBECTL_DESCRIBE and subcommand != "describe":
        raise ManualNextCheckError("Describe candidate must use `kubectl describe`.")
    if family == CommandFamily.KUBECTL_GET and subcommand != "get":
        raise ManualNextCheckError("Get candidate must use `kubectl get`.")
    if family == CommandFamily.KUBECTL_GET_CRD:
        if subcommand != "get":
            raise ManualNextCheckError("CRD candidate must use `kubectl get`.")
        tokens_lower = " ".join(tokens).lower()
        if "crd" not in tokens_lower and "customresourcedefinition" not in tokens_lower:
            raise ManualNextCheckError("CRD candidate must reference CRDs.")
    for token in tokens:
        lowered = token.lower()
        if any(keyword in lowered for keyword in MUTATION_KEYWORDS):
            raise ManualNextCheckError("Command references a potentially mutating keyword.")
        if any(danger in token for danger in _DANGEROUS_CHARS):
            raise ManualNextCheckError("Command contains unsupported punctuation for manual execution.")


def _validate_llm_namespace(namespace: str) -> str:
    """Validate a namespace name from LLM output.

    This is a defense-in-depth check for LLM-derived namespace names.
    The namespace must conform to Kubernetes DNS label conventions.

    Args:
        namespace: The namespace name to validate.

    Returns:
        The validated namespace name.

    Raises:
        ManualNextCheckError: If the namespace name is invalid.
    """
    try:
        return validate_kubernetes_namespace(namespace)
    except SecurityError as exc:
        raise ManualNextCheckError(
            f"LLM suggested invalid namespace name: {exc}"
        ) from exc


def _validate_llm_resource_name(resource: str) -> str:
    """Validate a resource name from LLM output.

    This is a defense-in-depth check for LLM-derived resource names.
    The resource name must conform to Kubernetes DNS name conventions.

    Args:
        resource: The resource name to validate.

    Returns:
        The validated resource name.

    Raises:
        ManualNextCheckError: If the resource name is invalid.
    """
    try:
        return validate_kubernetes_resource_name(resource)
    except SecurityError as exc:
        raise ManualNextCheckError(
            f"LLM suggested invalid resource name: {exc}"
        ) from exc


def _build_command(description: str, target_context: str, family: CommandFamily) -> list[str]:
    """Build a kubectl command from LLM description with validation.

    This function parses the LLM description, validates all identifiers,
    and constructs a safe kubectl command.

    Args:
        description: LLM-generated command description
        target_context: Validated kube context
        family: Command family

    Returns:
        Validated kubectl command list

    Raises:
        ManualNextCheckError: If parsing or validation fails
    """
    try:
        tokens = shlex.split(description)
    except ValueError as exc:
        raise ManualNextCheckError(f"Unable to parse candidate command: {exc}") from exc
    if not tokens or tokens[0] != "kubectl":
        raise ManualNextCheckError("Candidate command must begin with `kubectl`.")
    remainder = _strip_context_arguments(tokens[1:])
    _validate_command_tokens(family, remainder)
    if not remainder:
        raise ManualNextCheckError("Candidate command does not include a subcommand.")

    # Validate target context (defense-in-depth)
    try:
        validated_context = validate_kube_context_name(target_context)
    except SecurityError as exc:
        raise ManualNextCheckError(
            f"Invalid kubectl context: {exc}"
        ) from exc

    # Validate namespace and resource names in the command (defense-in-depth for LLM input)
    validated_remainder: list[str] = []
    i = 0
    while i < len(remainder):
        token = remainder[i]
        # Check for -n or --namespace flag followed by namespace value
        if token in ("-n", "--namespace"):
            if i + 1 < len(remainder):
                namespace = remainder[i + 1]
                try:
                    validated_namespace = _validate_llm_namespace(namespace)
                    validated_remainder.append(token)
                    validated_remainder.append(validated_namespace)
                    i += 2
                    continue
                except ManualNextCheckError:
                    raise
        # Check for resource name after common resource-type tokens
        elif token in ("pod", "pods", "deployment", "deployments", "service", "services",
                      "secret", "secrets", "configmap", "configmaps", "ingress", "ingresses",
                      "pvc", "pvcs", "hpa", "statefulset", "statefulsets", "daemonset",
                      "daemonsets", "job", "jobs", "cronjob", "cronjobs", "node", "nodes"):
            # This token is a resource type, the next token (if any) is likely the resource name
            validated_remainder.append(token)
            i += 1
            # Check if next token looks like a resource name (not a flag)
            if i < len(remainder) and not remainder[i].startswith("-"):
                resource = remainder[i]
                try:
                    validated_resource = _validate_llm_resource_name(resource)
                    validated_remainder.append(validated_resource)
                    i += 1
                    continue
                except ManualNextCheckError:
                    raise
            continue
        else:
            validated_remainder.append(token)
        i += 1

    context_args = render_kubectl_context_args(validated_context)
    return ["kubectl", *validated_remainder, *context_args]
