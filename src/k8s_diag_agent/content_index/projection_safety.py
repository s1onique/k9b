"""Content projection safety utilities.

This module provides forbidden content detection, field stripping, and validation.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

import json
import re
from typing import Any

from .schema import check_forbidden_fields


def contains_forbidden_content(data: dict[str, Any]) -> list[str]:
    """Check if data contains forbidden content patterns.

    Args:
        data: Dictionary to check.

    Returns:
        List of forbidden patterns found.
    """
    forbidden = check_forbidden_fields(data)

    # Check for additional patterns in string values
    for key, value in data.items():
        if isinstance(value, str):
            # Check for absolute paths
            if value.startswith("/") or "~/" in value:
                forbidden.append(f"{key}: absolute_path")

            # Check for token-like strings
            if re.search(r"[A-Za-z0-9]{20,}--[A-Za-z0-9]", value):
                forbidden.append(f"{key}: token_pattern")

    return list(set(forbidden))  # Deduplicate


def strip_forbidden_fields(
    data: dict[str, Any],
    allowed_fields: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Strip forbidden fields from data while preserving non-forbidden nested content.

    This function:
    1. Removes keys that match FORBIDDEN_FIELD_PATTERNS (case-insensitive)
    2. Keeps keys that are in allowed_fields
    3. For nested dicts, recursively strips forbidden fields but preserves non-forbidden content

    Args:
        data: Input dictionary.
        allowed_fields: Top-level fields to keep (defaults to ALLOWED_PROJECTION_FIELDS).

    Returns:
        Dictionary with forbidden fields stripped.
    """
    from .schema import FORBIDDEN_FIELD_PATTERNS

    if allowed_fields is None:
        from .projection_contract import ALLOWED_PROJECTION_FIELDS as _allowed
        allowed_fields = _allowed

    result = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Skip keys matching forbidden patterns
        is_forbidden = any(pattern in key_lower for pattern in FORBIDDEN_FIELD_PATTERNS)
        if is_forbidden:
            continue

        # Recursively clean nested dicts
        if isinstance(value, dict):
            # Recursively strip forbidden fields from nested dicts
            nested = strip_forbidden_fields(value, None)
            # Preserve nested dict if it has content after stripping
            if nested:
                result[key] = nested
        elif isinstance(value, list):
            result[key] = [
                strip_forbidden_fields(item, None)
                if isinstance(item, dict)
                else item
                for item in value
            ]  # type: ignore[assignment]
        else:
            result[key] = value

    return result


def truncate_string(s: str, max_length: int) -> str:
    """Truncate a string to max length.

    Args:
        s: String to truncate.
        max_length: Maximum length.

    Returns:
        Truncated string with ellipsis if needed.
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - 3] + "..."


def validate_projection_safety(
    projection_json: str,
) -> tuple[bool, list[str]]:
    """Validate that a projection is safe.

    Args:
        projection_json: JSON string of the projection.

    Returns:
        Tuple of (is_safe, list of issues).
    """
    from .projection_contract import PROJECTION_API_DETAIL

    issues: list[str] = []

    try:
        data = json.loads(projection_json)
    except json.JSONDecodeError:
        issues.append("Invalid JSON")
        return False, issues

    # Check for forbidden fields
    forbidden = contains_forbidden_content(data)
    if forbidden:
        issues.extend([f"forbidden: {f}" for f in forbidden])

    # Check for absolute paths in string values
    for key, value in data.items():
        if isinstance(value, str):
            if value.startswith("/"):
                issues.append(f"absolute_path: {key}")
            if "~/" in value:
                issues.append(f"home_path: {key}")

    # Check for API detail projection containing raw K8s objects
    projection_kind = data.get("projection_kind", "")
    if projection_kind == PROJECTION_API_DETAIL:
        # Check for raw K8s object patterns
        raw_patterns = ["kind", "apiVersion", "metadata", "spec", "status"]
        nested = [k for k in data.keys() if k in raw_patterns]
        if nested:
            issues.extend([f"potential_k8s_object: {k}" for k in nested])

    return len(issues) == 0, issues
