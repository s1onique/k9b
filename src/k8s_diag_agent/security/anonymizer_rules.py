"""Classification rules and pattern helpers for metadata anonymization.

This module contains the constants and helper functions used by MetadataAnonymizer
to classify fields, detect patterns, and determine anonymization strategy.

Extracted from: k8s_diag_agent/security/anonymizer.py
"""

from __future__ import annotations

import re
from typing import Any

# Label/annotation keys that suggest name-like values requiring anonymization
_LABEL_NAME_PATTERNS = re.compile(
    r"^(app|application|name|instance|component|version|environment|"
    r"part-of|managed-by|owner|team|department|project|tier|"
    r"contact|docs|runbook|description|image|artifact|container_image|"
    r"backup_source|documentation|support-url)$",
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


# Patterns for sensitive content in values
_URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
)

_REGISTRY_PATH_PATTERN = re.compile(
    r"(?:docker\.io|ghcr\.io|registry\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9-]+\.azurecr\.io|[a-zA-Z0-9-]+\.gcr\.io|[a-zA-Z0-9-]+\.ecr\.[a-zA-Z0-9-]+\.amazonaws\.com|s3://[a-zA-Z0-9-]+)",
    re.IGNORECASE,
)


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


def _contains_sensitive_pattern(value: str) -> bool:
    """Check if a string contains sensitive patterns requiring anonymization."""
    if not isinstance(value, str):
        return False
    # Check for URLs
    if _URL_PATTERN.search(value):
        return True
    # Check for email addresses
    if _EMAIL_PATTERN.search(value):
        return True
    # Check for registry paths
    if _REGISTRY_PATH_PATTERN.search(value):
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


__all__ = [
    "_LABEL_NAME_PATTERNS",
    "_METADATA_FIELD_NAMES",
    "_CLUSTER_CONTEXT_FIELDS",
    "_PRESERVE_FIELDS",
    "_looks_like_hostname",
    "_looks_like_name",
    "_detect_category",
]
