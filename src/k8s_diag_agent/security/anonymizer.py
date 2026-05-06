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

# Label/annotation keys that suggest name-like values requiring anonymization
_LABEL_NAME_PATTERNS = re.compile(
    r"^(app|application|name|instance|component|version|environment|"
    r"part-of|managed-by|owner|team|department|project|tier)$",
    re.IGNORECASE,
)

# Known field names for cluster metadata
_METADATA_FIELD_NAMES = frozenset((
    "cluster_id",
    "cluster_name",
    "namespace",
    "node_name",
    "node",
    "pod_name",
    "pod",
    "service_name",
    "service",
    "hostname",
    "host",
    "release_name",
    "release",
    "name",
    "crd_name",
))

# Fields that contain cluster identifiers that should be anonymized
_CLUSTER_CONTEXT_FIELDS = frozenset((
    "context",
    "cluster_context",
    "user_context",
))

# Fields that should be preserved as-is (not name-like)
_PRESERVE_FIELDS = frozenset((
    "kind",
    "api_version",
    "status",
    "phase",
    "conditions",
    "state",
    "reason",
    "type",
    "message",
    "count",
    "node_count",
    "pod_count",
    "replicas",
    "desired_replicas",
    "available_replicas",
    "unavailable_replicas",
    "timestamp",
    "creation_timestamp",
    "last_transition_time",
    "last_update_time",
    "generation",
    "resource_version",
    "uid",
    "labels",
    "annotations",
    "annotations_map",
    "metadata",
))


def _to_safe_string(value: Any) -> str:
    """Convert value to string for comparison."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return repr(value)


def _looks_like_hostname(value: str) -> bool:
    """Check if a string looks like a hostname or domain."""
    if not isinstance(value, str):
        return False
    # Contains dots and doesn't look like a random hash
    if "." in value and len(value) > 4:
        return True
    # Contains common TLD patterns
    if re.search(r"\.(com|org|net|io|app|dev|internal|local)$", value, re.IGNORECASE):
        return True
    return False


def _looks_like_name(value: str) -> bool:
    """Check if a string looks like a name rather than an identifier/hash."""
    if not isinstance(value, str):
        return False
    # Too short to be meaningful
    if len(value) < 2:
        return False
    # Looks like a random hash (hex + separator pattern)
    if re.match(r"^[a-f0-9]{8,}-[a-f0-9]{4,}$", value, re.IGNORECASE):
        return False
    # Contains spaces or mixed case words (names often do)
    if re.search(r"[A-Z][a-z]|[a-z][A-Z]", value):
        return True
    return True


def _detect_category(key: str, value: Any, parent_kind: str | None = None) -> str | None:
    """Detect the category/alias type for a given key-value pair.

    Returns the category string for alias generation, or None if not applicable.
    """
    key_lower = key.lower().replace("-", "_")

    # Direct field matches
    if key_lower == "cluster_id":
        return "cluster"
    if key_lower == "cluster_name":
        return "cluster"
    if key_lower == "cluster":
        return "cluster"
    if key_lower == "cluster_label":
        return "cluster"
    if key_lower == "label" and parent_kind is None:
        # Top-level label fields often contain cluster/workload identifiers
        return "label"

    if key_lower == "namespace":
        return "namespace"
    if key_lower in ("node_name", "node"):
        return "node"
    if key_lower in ("pod_name", "pod"):
        return "pod"
    if key_lower in ("service_name", "service"):
        return "service"
    if key_lower in ("hostname", "host"):
        return "host"
    if key_lower in ("release_name", "release"):
        return "release"

    # CRD name detection
    if key_lower in ("crd_name", "crd"):
        return "crd"

    # ingress/host detection
    if key_lower == "ingress":
        return "host"

    # Context fields that may contain cluster identifiers
    if key_lower in ("context", "cluster_context", "user_context"):
        return "cluster"

    # metadata.name with kind context
    if key_lower == "name" and parent_kind:
        kind_lower = parent_kind.lower()
        if "deployment" in kind_lower:
            return "deployment"
        if "statefulset" in kind_lower:
            return "statefulset"
        if "daemonset" in kind_lower:
            return "daemonset"
        if "pod" in kind_lower:
            return "pod"
        if "service" in kind_lower:
            return "service"
        if "ingress" in kind_lower:
            return "host"
        if "job" in kind_lower:
            return "job"
        if "cronjob" in kind_lower:
            return "cronjob"
        return "workload"

    # metadata.name without kind context - use generic "name"
    if key_lower == "name":
        return "name"

    return None


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