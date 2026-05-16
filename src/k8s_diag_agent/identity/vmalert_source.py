"""Canonical identity helpers for vmalert sources.

This module provides deterministic identity construction for vmalert sources,
separating distinct identity layers similar to Alertmanager source identity.

Entity type identifier: vmalert-source

Import from this module for all vmalert canonical identity operations.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Entity type identifier for vmalert sources
_ENTITY_TYPE = "vmalert-source"


def extract_vmalert_source_facts(
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
    object_uid: str | None = None,
) -> dict[str, Any]:
    """Extract normalized defining facts for a vmalert source.

    Args:
        namespace: Kubernetes namespace (identity anchor when available)
        name: Kubernetes resource name (preferred identity anchor)
        origin: Origin family (vmalert-crd, service-heuristic)
        endpoint: Service endpoint (fallback when no namespace/name)
        cluster_uid: Cluster UID (optional identity anchor)
        object_uid: Native Kubernetes object UID (optional, highest confidence)

    Example:
        >>> facts = extract_vmalert_source_facts(
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ...     origin="service-heuristic",
        ... )
    """
    facts: dict[str, Any] = {}

    # Include object_uid when available (highest confidence anchor)
    if object_uid is not None:
        facts["object_uid"] = object_uid

    if name is not None:
        facts["name"] = name

    if namespace is not None:
        facts["namespace"] = namespace

    if origin is not None:
        facts["origin"] = origin

    if cluster_uid is not None:
        facts["cluster_uid"] = cluster_uid

    # Fallback: endpoint only when no namespace/name available
    if not facts.get("namespace") and not facts.get("name"):
        if endpoint is not None:
            # Normalize: strip scheme and trailing slash
            normalized = endpoint.rstrip('/')
            if normalized.startswith('http://'):
                normalized = normalized[7:]
            elif normalized.startswith('https://'):
                normalized = normalized[8:]
            facts["endpoint"] = normalized

    return facts


def build_vmalert_canonical_entity_id(
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
    object_uid: str | None = None,
) -> str:
    """Build canonical entity ID for a vmalert source.

    This is the single canonical ID builder - all canonical identity
    flows through extract_vmalert_source_facts() then here.

    Example:
        >>> id1 = build_vmalert_canonical_entity_id(
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ...     origin="service-heuristic",
        ... )
        >>> id2 = build_vmalert_canonical_entity_id(
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ...     origin="service-heuristic",
        ... )
        >>> assert id1 == id2  # Same facts => same ID
    """
    facts = extract_vmalert_source_facts(
        namespace=namespace,
        name=name,
        origin=origin,
        endpoint=endpoint,
        cluster_uid=cluster_uid,
        object_uid=object_uid,
    )

    # Build deterministic string from normalized facts
    parts = []
    for key in sorted(facts.keys()):
        parts.append(f"{key}={facts[key]}")
    identity_string = "|".join(parts)

    # Hash for deterministic ID
    digest = hashlib.sha256(identity_string.encode("utf-8")).hexdigest()[:16]
    return f"{_ENTITY_TYPE}:{digest}"


def build_vmalert_canonical_human_id(
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
) -> str:
    """Build canonical human-readable ID for a vmalert source.

    Unlike build_vmalert_canonical_entity_id(), this returns a
    human-readable string useful for debugging and logging.

    Args:
        Same as build_vmalert_canonical_entity_id()

    Returns:
        Human-readable ID string (e.g., "victoria-metrics-k8s-stack/vmalert-infra-...")

    Example:
        >>> build_vmalert_canonical_human_id(
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ... )
        'victoria-metrics-k8s-stack/vmalert-infra-victoria-metrics-k8s-stack'
    """
    facts = extract_vmalert_source_facts(
        namespace=namespace,
        name=name,
        origin=origin,
        endpoint=endpoint,
    )

    # Use namespace/name when available
    if facts.get("namespace") and facts.get("name"):
        return f"{facts['namespace']}/{facts['name']}"

    # Fallback to endpoint
    if facts.get("endpoint"):
        return str(facts["endpoint"])

    return "unknown"


def build_vmalert_operator_intent_key(
    cluster_label: str | None = None,
    cluster_context: str | None = None,
    namespace: str | None = None,
    name: str | None = None,
    endpoint: str | None = None,
) -> str:
    """Build operator-intent persistence key for durable actions.

    This key is used ONLY for durable operator actions (promote/disable)
    and override persistence. It is NOT the canonical historical identity.

    Design rationale:
    - cluster_label is preferred over cluster_context because it is
      operator-controlled and stable across kubeconfig edits/renames
    - cluster_context can change with kubeconfig edits, aliases, or renames

    Example:
        >>> key1 = build_vmalert_operator_intent_key(
        ...     cluster_label="prod-cluster",
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ... )
        >>> key2 = build_vmalert_operator_intent_key(
        ...     cluster_label="prod-cluster",
        ...     namespace="victoria-metrics-k8s-stack",
        ...     name="vmalert-infra-victoria-metrics-k8s-stack",
        ... )
        >>> assert key1 == key2  # Same source, same key
    """
    # Use cluster_label if available, otherwise cluster_context
    cluster_key = cluster_label if cluster_label else (cluster_context or "default")

    # Build source identity
    if namespace and name:
        source_identity = f"{namespace}/{name}"
    elif endpoint:
        normalized = endpoint.rstrip('/')
        if normalized.startswith('http://'):
            normalized = normalized[7:]
        elif normalized.startswith('https://'):
            normalized = normalized[8:]
        source_identity = normalized
    else:
        source_identity = "unknown"

    return f"{cluster_key}:{source_identity}"


def get_canonical_identity_summary(
    namespace: str | None,
    name: str | None,
    origin: str | None,
) -> str:
    """Build a compact summary of the source identity.

    Format: namespace/name (origin)

    Example:
        >>> get_canonical_identity_summary(
        ...     "victoria-metrics-k8s-stack",
        ...     "vmalert-infra-victoria-metrics-k8s-stack",
        ...     "service-heuristic",
        ... )
        'victoria-metrics-k8s-stack/vmalert-infra-victoria-metrics-k8s-stack (service-heuristic)'
    """
    parts = []
    if namespace and name:
        parts.append(f"{namespace}/{name}")
    if origin:
        parts.append(f"({origin})")
    return " ".join(parts) if parts else "unknown"