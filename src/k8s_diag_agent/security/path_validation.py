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
