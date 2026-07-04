"""Shared artifact sanitizer for live-lab artifact hygiene.

This module provides a recursive sanitizer that redacts sensitive values
from Kubernetes objects and lab artifacts before persisting them.

Design rationale:
- Run at WRITE time, not read time - artifacts are always sanitized on the way out.
- Recursive traversal handles nested Pod/Deployment specs, Secret refs, env vars.
- Preserve diagnostic shape but redact values.
- Structured markers indicate redaction so consumers understand the shape.

Usage:
    from scripts.lab_common.artifact_sanitizer import sanitize_artifact

    # Before writing any artifact that may contain K8s objects or secrets
    sanitized_data = sanitize_artifact(raw_k8s_data)
    write_json_artifact(output_dir, "pods.json", sanitized_data)

禁止 patterns that trigger redaction:
- password, passwd, secret, token, credential
- kubeconfig (file paths or content markers)
- client-certificate-data, client-key-data, certificate-authority-data
- access_token, refresh_token
- Bearer JWT patterns
"""

from __future__ import annotations

import json
import re
from typing import Any

# =============================================================================
# Forbidden pattern definitions
# =============================================================================

# Keys that are always redacted when found as dict keys
FORBIDDEN_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"passwd", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"kubeconfig", re.IGNORECASE),
    re.compile(r"client-certificate-data"),
    re.compile(r"client-key-data"),
    re.compile(r"certificate-authority-data"),
    re.compile(r"access_token"),
    re.compile(r"refresh_token"),
]

# Value patterns that trigger redaction
FORBIDDEN_VALUE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"--password(?:=|\s+)", re.IGNORECASE),
    re.compile(r"Bearer\s+eyJ", re.IGNORECASE),
    re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.IGNORECASE),
    re.compile(r"BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY", re.IGNORECASE),
]

# Specific kubeconfig path patterns
KUBECONFIG_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"kubeconfig[=:]\s*['\"]?/[\w./-]+"),
    re.compile(r"KUBECONFIG\s*=\s*['\"]?/[\w./-]+"),
    re.compile(r"--kubeconfig\s+['\"]?/[\w./-]+"),
]

# Redaction placeholder
REDACTED_VALUE = "[REDACTED:sensitive-value]"
REDACTED_KEY = "[REDACTED:sensitive-key]"

# Patterns that indicate a Secret reference (should be preserved but values redacted)
SECRET_REF_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"secretKeyRef", re.IGNORECASE),
    re.compile(r"secretRef", re.IGNORECASE),
]


# =============================================================================
# Core sanitization logic
# =============================================================================


def _is_forbidden_key(key: str) -> bool:
    """Check if a dict key matches forbidden patterns."""
    if not isinstance(key, str):
        return False
    for pattern in FORBIDDEN_KEY_PATTERNS:
        if pattern.search(key):
            return True
    return False


def _is_forbidden_value(value: Any) -> bool:
    """Check if a value matches forbidden value patterns."""
    if not isinstance(value, str):
        return False
    for pattern in FORBIDDEN_VALUE_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _is_kubeconfig_path(value: Any) -> bool:
    """Check if a value contains a kubeconfig path reference."""
    if not isinstance(value, str):
        return False
    for pattern in KUBECONFIG_PATH_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _is_secret_ref_dict(data: dict[str, Any]) -> bool:
    """Check if a dict represents a Secret reference (secretKeyRef, etc.)."""
    return any(
        pattern.search(json.dumps(data))
        for pattern in SECRET_REF_PATTERNS
    )


def _sanitize_secret_ref(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a Secret reference while preserving diagnostic shape.

    For secretKeyRef:
    {
      "name": "my-secret",
      "key": "password"
    }
    becomes:
    {
      "name": "[REDACTED:secret-name]",
      "key": "[REDACTED:secret-key]"
    }
    """
    result = {}
    for key, value in data.items():
        if key in ("name", "key", "optional"):
            if key == "optional":
                # Preserve optional flag
                result[key] = value
            else:
                result[key] = f"[REDACTED:{key}]"
        else:
            result[key] = sanitize_value(value)
    return result


def sanitize_value(value: Any, max_depth: int = 20, _depth: int = 0) -> Any:
    """Sanitize a single value recursively.

    Args:
        value: The value to sanitize
        max_depth: Maximum recursion depth
        _depth: Current depth (internal)

    Returns:
        Sanitized value
    """
    if _depth >= max_depth:
        return value

    # Handle None
    if value is None:
        return None

    # Handle strings
    if isinstance(value, str):
        if _is_forbidden_value(value):
            return REDACTED_VALUE
        if _is_kubeconfig_path(value):
            return REDACTED_VALUE
        return value

    # Handle lists
    if isinstance(value, list):
        return [sanitize_value(item, max_depth, _depth + 1) for item in value]

    # Handle dicts
    if isinstance(value, dict):
        # Check if this is a Secret reference
        if _is_secret_ref_dict(value):
            return _sanitize_secret_ref(value)

        # Check for forbidden keys
        result = {}
        for k, v in value.items():
            if _is_forbidden_key(k):
                # Redact the value but keep the key structure
                result[k] = REDACTED_VALUE
            else:
                result[k] = sanitize_value(v, max_depth, _depth + 1)
        return result

    # Handle other types (int, float, bool, etc.)
    return value


def sanitize_artifact(data: Any, max_depth: int = 20) -> Any:
    """Sanitize a complete artifact dict or list for safe persistence.

    This is the main entry point for artifact sanitization.

    Args:
        data: The artifact data to sanitize (dict, list, or primitive)
        max_depth: Maximum recursion depth

    Returns:
        Sanitized copy of the artifact
    """
    return sanitize_value(data, max_depth, _depth=0)


def sanitize_json_string(json_str: str) -> str:
    """Sanitize a JSON string by parsing, sanitizing, and re-serializing.

    This is useful when you have a raw JSON string that needs sanitization.

    Args:
        json_str: Raw JSON string

    Returns:
        Sanitized JSON string

    Raises:
        json.JSONDecodeError: If the input is not valid JSON
    """
    data = json.loads(json_str)
    sanitized = sanitize_artifact(data)
    return json.dumps(sanitized, indent=2, default=str)


# =============================================================================
# Specialized sanitizers for specific artifact types
# =============================================================================


def sanitize_pods_artifact(pods_data: Any) -> Any:
    """Sanitize a Kubernetes pods collection artifact.

    This is a specialized wrapper for pods.json artifacts.
    It handles common Pod spec patterns including:
    - env vars and envFrom (which can reference Secrets)
    - volume mounts (which can reference Secret volumes)
    - container args/commands

    Args:
        pods_data: Raw pods data from kubectl get pods -o json

    Returns:
        Sanitized pods data
    """
    return sanitize_artifact(pods_data)


def sanitize_deployments_artifact(deployments_data: Any) -> Any:
    """Sanitize a Kubernetes deployments collection artifact.

    This is a specialized wrapper for deployments.json artifacts.
    It handles common Deployment spec patterns including:
    - env vars and envFrom (which can reference Secrets)
    - volume mounts (which can reference Secret volumes)
    - container args/commands

    Args:
        deployments_data: Raw deployments data from kubectl get deployments -o json

    Returns:
        Sanitized deployments data
    """
    return sanitize_artifact(deployments_data)


def sanitize_review_artifact(artifact_data: Any) -> Any:
    """Sanitize a review artifact file.

    Review artifacts may contain references to external resources
    or diagnostic data that needs sanitization.

    Args:
        artifact_data: Raw review artifact data

    Returns:
        Sanitized artifact data
    """
    return sanitize_artifact(artifact_data)


def sanitize_provenance_artifact(artifact_data: Any) -> Any:
    """Sanitize a provenance/diagnostic artifact.

    Provenance artifacts capture system state for debugging.
    They may contain file paths, command references, or other
    sensitive context that needs sanitization.

    Args:
        artifact_data: Raw provenance artifact data

    Returns:
        Sanitized provenance data
    """
    return sanitize_artifact(artifact_data)


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == "__main__":

    # Test sanitizer with sample inputs
    test_cases = [
        # Secret reference
        {
            "name": "my-container",
            "env": [
                {"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "db-creds", "key": "password"}}},
                {"name": "SIMPLE_VAR", "value": "not-secret"},
            ],
        },
        # Forbidden key
        {"password": "hunter2", "username": "admin"},
        # Kubeconfig path in string
        "kubectl --kubeconfig=/tmp/my-cluster.conf get pods",
        # Clean data
        {"name": "nginx", "image": "nginx:latest"},
    ]

    print("Testing artifact sanitizer...")
    print("=" * 60)

    for i, test_input in enumerate(test_cases):
        print(f"\nTest case {i + 1}:")
        print(f"  Input:  {json.dumps(test_input)[:100]}...")
        result = sanitize_artifact(test_input)
        print(f"  Output: {json.dumps(result)[:100]}...")
        print(f"  Status: {'PASS' if test_input != result else 'UNCHANGED'}")

    print("\n" + "=" * 60)
    print("Sanitizer test complete")
