"""Deterministic entity identity for inferred entities."""

from __future__ import annotations

import hashlib
from typing import Any


def build_deterministic_entity_id(
    entity_type: str,
    defining_facts: dict[str, Any],
) -> str:
    """Build a deterministic canonical ID from normalized defining facts.

    This generates a stable ID for entities that don't have native UIDs
    (e.g., discovered Alertmanager sources, inferred services). The ID is
    deterministic: same facts always produce the same ID.

    Args:
        entity_type: Type identifier (e.g., "alertmanager-source", "ingress").
        defining_facts: Normalized facts that define the entity's identity.
                       These should be the minimal set of facts that uniquely
                       identify the entity across discoveries.

    Returns:
        A deterministic ID string (hex-encoded SHA-256 hash).

    Invariants:
        - Same entity rediscovered → same canonical_entity_id
        - Entity with different facts → different canonical_entity_id

    Example:
        >>> id1 = build_deterministic_entity_id(
        ...     "alertmanager-source",
        ...     {"namespace": "monitoring", "name": "alertmanager-main"}
        ... )
        >>> id2 = build_deterministic_entity_id(
        ...     "alertmanager-source",
        ...     {"namespace": "monitoring", "name": "alertmanager-main"}
        ... )
        >>> id1 == id2
        True
    """
    # Normalize facts into a canonical key-value string
    normalized_parts: list[str] = [entity_type]

    # Sort keys for deterministic ordering
    for key in sorted(defining_facts.keys()):
        value = defining_facts[key]
        if value is not None:
            normalized_parts.append(f"{key}={value}")

    # Join with separator and encode
    canonical_string = "|".join(normalized_parts)

    # Generate deterministic hash
    hash_hex = hashlib.sha256(canonical_string.encode("utf-8")).hexdigest()

    # Return first 32 characters of hex (128 bits, plenty for uniqueness)
    return hash_hex[:32]


def build_deterministic_human_id(
    entity_type: str,
    defining_facts: dict[str, Any],
    separator: str = "/",
) -> str:
    """Build a human-readable deterministic ID from defining facts.

    Unlike build_deterministic_entity_id(), this returns a human-readable
    string that can be useful for debugging and logging.

    Args:
        entity_type: Type identifier (e.g., "alertmanager-source").
        defining_facts: Normalized facts defining the entity.
        separator: Separator between fact values (default: "/").

    Returns:
        A human-readable ID string.

    Example:
        >>> build_deterministic_human_id(
        ...     "alertmanager-source",
        ...     {"namespace": "monitoring", "name": "alertmanager-main"}
        ... )
        'monitoring/alertmanager-main'
    """
    # Extract commonly human-readable identifiers
    primary_keys = ["namespace", "name", "service", "endpoint"]

    parts: list[str] = []
    for key in primary_keys:
        if key in defining_facts:
            value = defining_facts[key]
            if value is not None:
                parts.append(str(value))

    # Fallback to hashed ID if no primary keys found
    if not parts:
        return build_deterministic_entity_id(entity_type, defining_facts)

    return separator.join(parts)


def extract_entity_facts(
    data: dict[str, Any],
    fact_mappings: dict[str, str],
) -> dict[str, Any]:
    """Extract and normalize entity facts from raw data.

    This helps normalize facts from different sources into a consistent
    format for ID generation.

    Args:
        data: Raw data containing entity information.
        fact_mappings: Mapping from output key to input key(s).
                     Values can be a single key or comma-separated alternatives.

    Returns:
        Normalized facts dict.

    Example:
        >>> extract_entity_facts(
        ...     {"ns": "monitoring", "resource_name": "alertmanager-main"},
        ...     {"namespace": "ns", "name": "resource_name,name"}
        ... )
        {'namespace': 'monitoring', 'name': 'alertmanager-main'}
    """
    result: dict[str, Any] = {}

    for output_key, input_keys in fact_mappings.items():
        # Support comma-separated alternatives
        for input_key in input_keys.split(","):
            if input_key in data and data[input_key] is not None:
                result[output_key] = data[input_key]
                break

    return result
