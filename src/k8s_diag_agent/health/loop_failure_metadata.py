"""Failure metadata helpers for health loop diagnostics."""
from __future__ import annotations


def extract_failure_metadata_field(
    metadata: dict[str, object] | None,
    key: str,
) -> str | bool | None:
    """Extract a field from failure metadata, checking top-level and nested prompt_diagnostics.

    This helper enables result logs to extract failure details from either:
    1. metadata[key] - top-level failure class or exception type
    2. metadata["prompt_diagnostics"][key] - nested in prompt diagnostics

    Args:
        metadata: The failure_metadata dict from ExternalAnalysisArtifact
        key: The field name to extract (e.g., "failure_class", "exception_type")

    Returns:
        The field value (str for text fields, bool for boolean fields), or None if not found
    """
    if not metadata:
        return None
    value = metadata.get(key)
    if value is not None:
        # Preserve boolean values as-is; convert other truthy values to string
        if isinstance(value, bool):
            return value
        return str(value)
    prompt_diags = metadata.get("prompt_diagnostics")
    if isinstance(prompt_diags, dict):
        value = prompt_diags.get(key)
        if value is not None:
            if isinstance(value, bool):
                return value
            return str(value)
    return None
