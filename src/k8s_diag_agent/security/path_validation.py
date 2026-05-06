"""Security path validation helpers.

This module provides validation functions for user-controlled identifiers
that are used in file paths, globs, and artifact lookups.

See docs/security-standards.md for the full security policy.
"""

from __future__ import annotations

import re
from pathlib import Path

# Pattern for valid run IDs and similar safe path identifiers.
# Matches: alphanumeric, hyphens, underscores. Must start with alphanumeric.
# Examples: run-test-123, my_cluster, cluster-abc-def
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# Pattern for valid glob suffix (without the leading run_id)
_GLOB_SUFFIX_PATTERN = re.compile(r"^[a-zA-Z0-9_-]*$")

# Kubernetes DNS label pattern: lowercase alphanumeric, hyphens, max 63 chars.
# Must start with alphanumeric, can end with alphanumeric.
# Examples: default, my-namespace, app-v1-beta
_K8S_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")

# Kubernetes DNS name pattern (for resource names): lowercase alphanumeric, hyphens, dots, max 253 chars.
# Must start with alphanumeric, can end with alphanumeric.
# Examples: my-service, my.namespace.svc, configmap-name
_K8S_DNS_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$")

# Shell metacharacters that could be used for injection
_SHELL_METACHARACTERS = frozenset(
    ';&|><$`\\"\'{}[]!#*?%~ \t\n\r\x00'
)


class SecurityError(ValueError):
    """Raised when a security validation check fails.

    This indicates a potential path traversal or injection attempt.
    """

    pass


def validate_run_id(value: str) -> str:
    """Validate and return a run_id.

    Args:
        value: The run_id string to validate.

    Returns:
        The validated run_id if valid.

    Raises:
        SecurityError: If the run_id contains unsafe characters or patterns.

    Examples:
        >>> validate_run_id("run-test-123")
        'run-test-123'
        >>> validate_run_id("../etc")
        Traceback (most recent call last):
            ...
        k8s_diag_agent.security.path_validation.SecurityError: ...
    """
    if not value:
        raise SecurityError("run_id cannot be empty")

    # Check for null bytes
    if "\x00" in value:
        raise SecurityError("run_id contains null byte")

    # Check for path traversal patterns
    if ".." in value or "/" in value or "\\" in value:
        raise SecurityError("run_id contains path traversal pattern")

    # Check for glob metacharacters
    for char in "*?[]{}":
        if char in value:
            raise SecurityError(f"run_id contains glob metacharacter: {char}")

    # Validate against safe pattern
    if not _SAFE_ID_PATTERN.match(value):
        raise SecurityError(
            f"run_id contains unsafe characters: {value!r}"
        )

    return value


def validate_safe_path_id(value: str, field_name: str) -> str:
    """Validate a safe path identifier with a field name for error messages.

    Args:
        value: The value to validate.
        field_name: The name of the field for error messages.

    Returns:
        The validated value if valid.

    Raises:
        SecurityError: If the value contains unsafe characters or patterns.

    Examples:
        >>> validate_safe_path_id("my-cluster", "cluster_label")
        'my-cluster'
    """
    if not value:
        raise SecurityError(f"{field_name} cannot be empty")

    # Check for null bytes
    if "\x00" in value:
        raise SecurityError(f"{field_name} contains null byte")

    # Check for path traversal patterns
    if ".." in value or "/" in value or "\\" in value:
        raise SecurityError(f"{field_name} contains path traversal pattern")

    # Check for glob metacharacters
    for char in "*?[]{}":
        if char in value:
            raise SecurityError(f"{field_name} contains glob metacharacter: {char}")

    # Validate against safe pattern
    if not _SAFE_ID_PATTERN.match(value):
        raise SecurityError(
            f"{field_name} contains unsafe characters: {value!r}"
        )

    return value


def safe_child_path(root: Path, *parts: str) -> Path:
    """Construct a child path safely under a trusted root.

    This function validates each part of the path to prevent:
    - Path traversal (../)
    - Absolute paths
    - Glob metacharacters
    - Null bytes

    Uses Path.is_relative_to() (Python 3.9+) or Path.relative_to() for
    containment verification, which correctly handles sibling-prefix ambiguity
    (e.g., /tmp/root-evil is NOT under /tmp/root).

    Args:
        root: The trusted root directory.
        *parts: Path components to join under the root.

    Returns:
        The resolved child path.

    Raises:
        SecurityError: If any part is invalid or the result escapes the root.

    Examples:
        >>> from pathlib import Path
        >>> root = Path("/runs/health")
        >>> safe_child_path(root, "run-test", "external-analysis")
        PosixPath('/runs/health/run-test/external-analysis')
    """
    if not parts:
        return root.resolve()

    # Validate and join each part
    safe_parts = []
    for part in parts:
        # Check for null bytes
        if "\x00" in part:
            raise SecurityError(f"Path component contains null byte: {part!r}")

        # Check for path separators
        if "/" in part or "\\" in part:
            raise SecurityError(f"Path component contains separator: {part!r}")

        # Check for path traversal
        if ".." in part:
            raise SecurityError(f"Path component contains traversal: {part!r}")

        # Check for glob metacharacters
        for char in "*?[]{}":
            if char in part:
                raise SecurityError(
                    f"Path component contains glob metacharacter: {char!r}"
                )

        # Validate against safe pattern
        if part and not _GLOB_SUFFIX_PATTERN.match(part):
            raise SecurityError(f"Path component contains unsafe characters: {part!r}")

        safe_parts.append(part)

    # Construct the path
    result = root.joinpath(*safe_parts)

    # Resolve and verify containment using Path.relative_to()
    # This correctly rejects sibling prefixes like /tmp/root-evil under /tmp/root
    try:
        resolved = result.resolve()
        root_resolved = root.resolve()

        # Use is_relative_to() if available (Python 3.9+), otherwise use relative_to()
        if hasattr(resolved, "is_relative_to"):
            # Python 3.9+ - is_relative_to() is the preferred method
            if not resolved.is_relative_to(root_resolved):
                raise SecurityError(
                    f"Path escapes root: {resolved!r} not under {root_resolved!r}"
                )
        else:
            # Python 3.8 fallback - use relative_to() which raises on non-containment
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                raise SecurityError(
                    f"Path escapes root: {resolved!r} not under {root_resolved!r}"
                )

        return resolved
    except SecurityError:
        raise
    except Exception as exc:
        raise SecurityError(f"Failed to resolve path: {exc}") from exc


def safe_run_artifact_glob(run_id: str, suffix: str = "*.json") -> str:
    """Construct a safe glob pattern string for artifact lookups.

    This function validates the run_id and suffix, then returns the glob
    pattern string directly. Separates path construction from glob pattern.

    Args:
        run_id: The run_id to validate and use as the glob prefix.
        suffix: The glob suffix pattern (default: "*.json").

    Returns:
        A validated glob pattern string like "run-test-next-check-plan*.json".

    Raises:
        SecurityError: If the run_id or suffix is invalid.

    Examples:
        >>> safe_run_artifact_glob("run-test")
        'run-test*.json'
        >>> safe_run_artifact_glob("run-test", "-next-check-plan*.json")
        'run-test-next-check-plan*.json'
    """
    # Validate run_id internally - do not rely on caller prevalidation
    validate_run_id(run_id)

    # Validate suffix doesn't contain traversal
    if ".." in suffix or "/" in suffix or "\\" in suffix:
        raise SecurityError(f"Glob suffix contains path separators: {suffix!r}")

    if "\x00" in suffix:
        raise SecurityError("Glob suffix contains null byte")

    # Return the validated glob pattern string
    return f"{run_id}{suffix}"


def safe_glob_pattern(base_dir: Path, validated_prefix: str, suffix: str = "*.json") -> Path:
    """Construct a safe glob pattern for artifact lookups.

    DEPRECATED: Use safe_run_artifact_glob() instead for cleaner separation
    of concerns. This function is kept for backward compatibility.

    Args:
        base_dir: The base directory for the glob.
        validated_prefix: A validated run_id or similar identifier.
        suffix: The glob suffix pattern (default: "*.json").

    Returns:
        A Path object suitable for use with Path.glob().

    Raises:
        SecurityError: If the prefix or suffix is invalid.

    Examples:
        >>> from pathlib import Path
        >>> base = Path("/runs/health/external-analysis")
        >>> safe_glob_pattern(base, "run-test")
        PosixPath('/runs/health/external-analysis')
        # Use with: list(base.glob(safe_run_artifact_glob("run-test")))
    """
    # Validate the prefix
    validate_run_id(validated_prefix)

    # Validate suffix doesn't contain traversal
    if ".." in suffix or "/" in suffix or "\\" in suffix:
        raise SecurityError(f"Glob suffix contains path separators: {suffix!r}")

    if "\x00" in suffix:
        raise SecurityError("Glob suffix contains null byte")

    # For the glob operation, we return the base directory
    # The calling code should construct: base_dir.glob(safe_run_artifact_glob(prefix, suffix))
    # This function validates that the prefix is safe before any interpolation

    return base_dir


def validate_kube_context_name(value: str) -> str:
    """Validate a Kubernetes context name.

    Context names are user-defined in kubeconfig and follow DNS-like naming
    conventions. This validation ensures:
    - Non-empty
    - No shell metacharacters
    - No path separators or traversal patterns
    - Length is reasonable (1-500 chars)
    - No control characters

    Args:
        value: The kube context name to validate.

    Returns:
        The validated context name if valid.

    Raises:
        SecurityError: If the context name is invalid.

    Examples:
        >>> validate_kube_context_name("kind-cluster")
        'kind-cluster'
        >>> validate_kube_context_name("")
        Traceback (most recent call last):
            ...
        k8s_diag_agent.security.path_validation.SecurityError: ...
    """
    if not value:
        raise SecurityError("kube context name cannot be empty")

    # Reject whitespace-only values
    if value.strip() != value:
        raise SecurityError("kube context name contains leading/trailing whitespace")

    # Reject null bytes
    if "\x00" in value:
        raise SecurityError("kube context name contains null byte")

    # Reject path traversal and separator patterns
    if ".." in value or "/" in value or "\\" in value:
        raise SecurityError("kube context name contains path traversal pattern")

    # Reject shell metacharacters
    for char in _SHELL_METACHARACTERS:
        if char in value:
            raise SecurityError(f"kube context name contains shell metacharacter: {char!r}")

    # Length bounds check
    if len(value) > 500:
        raise SecurityError("kube context name exceeds maximum length (500)")

    return value


def validate_kubernetes_namespace(value: str) -> str:
    """Validate a Kubernetes namespace name.

    Kubernetes namespaces must conform to DNS label naming conventions per
    the Kubernetes API spec. This validation ensures:
    - Non-empty
    - Matches DNS label pattern (lowercase alphanumerics and hyphens)
    - Length is valid (1-63 chars)
    - No shell metacharacters or control characters

    Per Kubernetes spec:
    - Must be lowercase alphanumeric or hyphens
    - Must start and end with alphanumeric
    - Maximum 63 characters

    Args:
        value: The namespace name to validate.

    Returns:
        The validated namespace name if valid.

    Raises:
        SecurityError: If the namespace name is invalid.

    Examples:
        >>> validate_kubernetes_namespace("default")
        'default'
        >>> validate_kubernetes_namespace("my-app-v1")
        'my-app-v1'
        >>> validate_kubernetes_namespace("UPPER")
        Traceback (most recent call last):
            ...
        k8s_diag_agent.security.path_validation.SecurityError: ...
    """
    if not value:
        raise SecurityError("kubernetes namespace cannot be empty")

    # Reject whitespace-only values
    if value.strip() != value:
        raise SecurityError("kubernetes namespace contains leading/trailing whitespace")

    # Reject null bytes
    if "\x00" in value:
        raise SecurityError("kubernetes namespace contains null byte")

    # Reject path traversal patterns (shouldn't apply to namespaces but defensive)
    if ".." in value or "/" in value or "\\" in value:
        raise SecurityError("kubernetes namespace contains path traversal pattern")

    # Reject shell metacharacters
    for char in _SHELL_METACHARACTERS:
        if char in value:
            raise SecurityError(f"kubernetes namespace contains shell metacharacter: {char!r}")

    # Validate against Kubernetes DNS label pattern
    if not _K8S_DNS_LABEL_PATTERN.match(value):
        raise SecurityError(
            f"kubernetes namespace does not match DNS label pattern: {value!r}"
        )

    # Length bounds check per Kubernetes spec (max 63 chars)
    if len(value) > 63:
        raise SecurityError("kubernetes namespace exceeds maximum length (63)")

    return value


def validate_kubernetes_resource_name(value: str) -> str:
    """Validate a Kubernetes resource name.

    Kubernetes resource names (pods, services, deployments, etc.) must conform
    to DNS subdomain naming conventions. This validation ensures:
    - Non-empty
    - Matches DNS name pattern (lowercase alphanumerics, hyphens, dots)
    - Length is valid (1-253 chars)
    - No shell metacharacters or control characters
    - No path traversal patterns

    Per Kubernetes spec:
    - Must be lowercase alphanumeric or hyphens or dots
    - Must start and end with alphanumeric
    - Maximum 253 characters

    Args:
        value: The resource name to validate.

    Returns:
        The validated resource name if valid.

    Raises:
        SecurityError: If the resource name is invalid.

    Examples:
        >>> validate_kubernetes_resource_name("nginx-deployment")
        'nginx-deployment'
        >>> validate_kubernetes_resource_name("my-service.default.svc")
        'my-service.default.svc'
        >>> validate_kubernetes_resource_name("Pod_Name")
        Traceback (most recent call last):
            ...
        k8s_diag_agent.security.path_validation.SecurityError: ...
    """
    if not value:
        raise SecurityError("kubernetes resource name cannot be empty")

    # Reject whitespace-only values
    if value.strip() != value:
        raise SecurityError("kubernetes resource name contains leading/trailing whitespace")

    # Reject null bytes
    if "\x00" in value:
        raise SecurityError("kubernetes resource name contains null byte")

    # Reject path traversal patterns
    if ".." in value or "/" in value or "\\" in value:
        raise SecurityError("kubernetes resource name contains path traversal pattern")

    # Reject shell metacharacters
    for char in _SHELL_METACHARACTERS:
        if char in value:
            raise SecurityError(f"kubernetes resource name contains shell metacharacter: {char!r}")

    # Validate against Kubernetes DNS name pattern
    if not _K8S_DNS_NAME_PATTERN.match(value):
        raise SecurityError(
            f"kubernetes resource name does not match DNS name pattern: {value!r}"
        )

    # Length bounds check per Kubernetes spec (max 253 chars for DNS names)
    if len(value) > 253:
        raise SecurityError("kubernetes resource name exceeds maximum length (253)")

    return value
