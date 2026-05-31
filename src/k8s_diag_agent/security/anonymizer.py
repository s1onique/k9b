"""Metadata anonymizer for cluster information in LLM prompts.

This module provides a centralized anonymization helper that replaces cluster
metadata (names, IDs, namespaces, workloads) with stable aliases before prompts
are sent to external LLM providers.

Design: docs/security/llm-anonymization-design.md
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# Re-export classification helpers for backward compatibility
from k8s_diag_agent.security.anonymizer_rules import (
    _CLUSTER_CONTEXT_FIELDS,
    _LABEL_NAME_PATTERNS,
    _METADATA_FIELD_NAMES,
    _PRESERVE_FIELDS,
    _detect_category,
    _looks_like_hostname,
    _looks_like_name,
)

# Backward-compatibility re-exports for tests and external consumers
# These were moved to anonymizer_rules but remain importable from here
LABEL_NAME_PATTERNS = _LABEL_NAME_PATTERNS
METADATA_FIELD_NAMES = _METADATA_FIELD_NAMES
CLUSTER_CONTEXT_FIELDS = _CLUSTER_CONTEXT_FIELDS
PRESERVE_FIELDS = _PRESERVE_FIELDS


class MetadataAnonymizer:
    """Anonymizes cluster metadata for safe LLM prompt construction.

    This class replaces cluster names, namespace names, workload names, and
    other infrastructure identifiers with stable, readable aliases.

    Alias rules:
    - Same real value + category maps to same alias within one instance
    - Different values in same category map to different aliases
    - Alias format: {category}-{letter} (e.g., cluster-a, namespace-b)
    - Fresh instance starts fresh mapping (no cross-instance correlation)
    - Anonymization is always enabled (no local-provider bypass in this slice)

    Preserved fields:
    - Numeric values (counts, replicas)
    - Boolean values
    - None values
    - Timestamps (ISO format strings matching date-time patterns)
    - Kubernetes kind values
    - Status/phase fields
    - Resource counts
    """

    def __init__(self) -> None:
        # Maps category -> {real_value -> alias}
        self._mappings: dict[str, dict[str, str]] = {}
        # Maps category -> next counter for alias generation
        self._counters: dict[str, int] = {}

    def anonymize(self, data: Any) -> Any:
        """Recursively anonymize data, preserving structure.

        Args:
            data: Any JSON-serializable value (dict, list, string, number, etc.)

        Returns:
            The anonymized data with the same structure as input.
            The input object is not mutated.

        Note:
            Numeric, boolean, None, timestamps, and status fields are preserved.
            Only name-like string values in known categories are anonymized.
        """
        return self._anonymize_impl(data, parent_key=None, parent_kind=None)

    def _anonymize_impl(
        self,
        data: Any,
        *,
        parent_key: str | None,
        parent_kind: str | None,
    ) -> Any:
        """Internal recursive implementation."""
        # Handle None
        if data is None:
            return None

        # Handle boolean
        if isinstance(data, bool):
            return data

        # Handle numeric
        if isinstance(data, (int, float)):
            return data

        # Handle string
        if isinstance(data, str):
            return self._anonymize_string(data, parent_key=parent_key, parent_kind=parent_kind)

        # Handle list - preserve parent_key context for string items that need anonymization
        if isinstance(data, list):
            result: list[Any] = []
            for item in data:
                # For string items in lists, use the parent_key from context
                if isinstance(item, str):
                    processed = self._anonymize_string(item, parent_key=parent_key, parent_kind=parent_kind)
                    result.append(processed)
                else:
                    result.append(self._anonymize_impl(item, parent_key=None, parent_kind=parent_kind))
            return result

        # Handle tuple - preserve tuple type and parent_key context
        if isinstance(data, tuple):
            tuple_result: list[Any] = []
            for item in data:
                if isinstance(item, str):
                    processed = self._anonymize_string(item, parent_key=parent_key, parent_kind=parent_kind)
                    tuple_result.append(processed)
                else:
                    tuple_result.append(self._anonymize_impl(item, parent_key=None, parent_kind=parent_kind))
            return tuple(tuple_result)

        # Handle dict/mapping
        if isinstance(data, Mapping):
            return self._anonymize_mapping(data, parent_key=parent_key)

        # Handle set - convert to list (JSON doesn't support sets)
        if isinstance(data, set):
            return [self._anonymize_impl(item, parent_key=None, parent_kind=parent_kind) for item in data]

        # Handle other types (bytes, objects) - return as-is
        return data

    def _anonymize_mapping(
        self,
        data: Mapping[str, Any],
        *,
        parent_key: str | None,
    ) -> dict[str, Any]:
        """Anonymize a mapping (dict-like object)."""
        # Extract kind from this mapping for child processing
        current_kind: str | None = None
        kind_value = data.get("kind")
        if isinstance(kind_value, str):
            current_kind = kind_value

        # Check if this is a metadata block
        is_metadata = "metadata" in data and isinstance(data.get("metadata"), Mapping)

        result: dict[str, Any] = {}

        # First, handle special metadata.name case
        metadata = data.get("metadata")
        if (
            is_metadata
            and isinstance(metadata, Mapping)
            and "name" in metadata
            and isinstance(metadata["name"], str)
        ):
            # Get category based on kind (current or inherited)
            category = _detect_category("name", metadata["name"], parent_kind=current_kind)
            if category and category != "name":
                # Get or create alias for this name
                alias = self._get_or_create_alias(metadata["name"], category)
                result["metadata"] = {"name": alias}
                # Copy other metadata fields that should be preserved
                for k, v in metadata.items():
                    if k != "name":
                        result["metadata"][k] = self._anonymize_impl(
                            v,
                            parent_key=k,
                            parent_kind=current_kind,
                        )
            else:
                result["metadata"] = self._anonymize_impl(
                    metadata,
                    parent_key="metadata",
                    parent_kind=current_kind,
                )
        else:
            # Only emit metadata key if input had one
            if metadata is not None:
                result["metadata"] = self._anonymize_impl(
                    metadata,
                    parent_key="metadata",
                    parent_kind=current_kind,
                )

        # Process all fields except metadata (handled above)
        for key, value in data.items():
            if key == "metadata":
                continue
            # Check if this key should be anonymized
            category = _detect_category(key, value, parent_kind=current_kind)

            if category and isinstance(value, str) and self._is_anonymizable_string(value):
                alias = self._get_or_create_alias(value, category)
                result[key] = alias
            else:
                result[key] = self._anonymize_impl(
                    value,
                    parent_key=key,
                    parent_kind=current_kind,
                )

        return result

    def _anonymize_string(
        self,
        value: str,
        *,
        parent_key: str | None,
        parent_kind: str | None,
    ) -> str:
        """Anonymize a string value based on context."""
        if not self._is_anonymizable_string(value):
            return value

        # Try to detect category from parent key
        category = _detect_category(parent_key or "", value, parent_kind=parent_kind)

        if category and category != "name":
            return self._get_or_create_alias(value, category)

        # Check if value looks like a hostname
        if _looks_like_hostname(value):
            return self._get_or_create_alias(value, "host")

        return value

    def _is_anonymizable_string(self, value: str) -> bool:
        """Check if a string value should be anonymized."""
        if not isinstance(value, str):
            return False

        # Empty strings are not anonymized
        if not value:
            return False

        # Timestamps are not anonymized
        if self._looks_like_timestamp(value):
            return False

        # Too short
        if len(value) < 2:
            return False

        # Looks like a hash
        if re.match(r"^[a-f0-9]{32,}$", value, re.IGNORECASE):
            return False

        return True

    def _looks_like_timestamp(self, value: str) -> bool:
        """Check if a string looks like a timestamp."""
        if not isinstance(value, str):
            return False

        # ISO 8601 datetime pattern
        if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value):
            return True

        # RFC 2822 date pattern
        if re.match(r"\w{3},?\s+\d{1,2}\s+\w{3}\s+\d{4}", value):
            return True

        return False

    def _get_or_create_alias(self, value: str, category: str) -> str:
        """Get existing alias or create a new one for this value in category."""
        if category not in self._mappings:
            self._mappings[category] = {}
            self._counters[category] = 0

        if value in self._mappings[category]:
            return self._mappings[category][value]

        # Generate new alias
        counter = self._counters[category]
        alias = f"{category}-{chr(ord('a') + counter)}"

        # Handle overflow beyond 'z'
        if counter >= 26:
            # aa, ab, ac, ...
            first = chr(ord('a') + (counter // 26) - 1)
            second = chr(ord('a') + (counter % 26))
            alias = f"{category}-{first}{second}"

        self._mappings[category][value] = alias
        self._counters[category] = counter + 1

        return alias

    def anonymize_labels_annotations(self, data: dict[str, Any]) -> dict[str, Any]:
        """Anonymize label and annotation values that contain name-like data.

        This is a specialized method that processes labels/annotations dicts
        to anonymize values where the key suggests name-like content.

        Args:
            data: A dict that may contain 'labels' and/or 'annotations' keys

        Returns:
            The data with anonymized label/annotation values.
        """
        result = dict(data)

        for key in ("labels", "annotations", "annotations_map"):
            if key in result and isinstance(result[key], Mapping):
                labels_or_annotations = result[key]
                anonymized: dict[str, Any] = {}
                for label_key, label_value in labels_or_annotations.items():
                    if isinstance(label_value, str) and self._is_anonymizable_string(label_value):
                        # Check if the key suggests name-like content
                        safe_key = label_key.lower().replace("-", "_").replace(".", "_")
                        if _LABEL_NAME_PATTERNS.match(safe_key):
                            # Check if value looks like a name
                            if _looks_like_name(label_value):
                                anonymized[label_key] = self._get_or_create_alias(label_value, "label")
                            elif _looks_like_hostname(label_value):
                                anonymized[label_key] = self._get_or_create_alias(label_value, "host")
                            else:
                                anonymized[label_key] = label_value
                        else:
                            anonymized[label_key] = label_value
                    else:
                        anonymized[label_key] = label_value
                result[key] = anonymized

        return result

    def get_alias_mapping(self, category: str = "cluster") -> dict[str, str]:
        """Get the alias-to-real-value mapping for a category.

        This exposes the internal mapping so de-anonymization can reverse
        the aliases after provider response processing.

        Args:
            category: The category to get mappings for (default: "cluster")

        Returns:
            Dict mapping alias -> real value (e.g., {"cluster-a": "prod-cluster"})

        Example:
            >>> anon = MetadataAnonymizer()
            >>> anon.anonymize({"cluster": "prod-cluster"})
            {'cluster': 'cluster-a'}
            >>> anon.get_alias_mapping("cluster")
            {'cluster-a': 'prod-cluster'}
        """
        if category not in self._mappings:
            return {}
        # Invert the mapping: alias -> real value
        return {alias: real for real, alias in self._mappings[category].items()}

    def get_all_alias_mappings(self) -> dict[str, dict[str, str]]:
        """Get all alias mappings across all categories.

        Returns:
            Dict mapping category -> {alias -> real_value}
        """
        return {
            category: {alias: real for real, alias in mappings.items()}
            for category, mappings in self._mappings.items()
        }


def anonymize_metadata(data: Any) -> Any:
    """Convenience function to create an anonymizer and process data.

    Args:
        data: Any JSON-serializable value to anonymize

    Returns:
        The anonymized data. A fresh MetadataAnonymizer is used.
    """
    anonymizer = MetadataAnonymizer()
    return anonymizer.anonymize(data)


__all__ = [
    "MetadataAnonymizer",
    "anonymize_metadata",
]
