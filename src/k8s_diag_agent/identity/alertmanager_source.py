"""Canonical identity helpers for Alertmanager sources.

This module provides deterministic identity construction for Alertmanager sources,
separating three distinct identity layers:

1. Canonical historical identity (canonical_entity_id)
   - Built deterministically from normalized defining facts
   - Same source facts across runs => same canonical_entity_id
   - Different source facts => different canonical_entity_id

2. Operator-intent persistence key (operator_intent_key)
   - Used only for durable operator actions / overrides / promote-disable persistence
   - May prefer cluster_label over cluster_context for pragmatic operator stability
   - MUST NOT be presented as canonical historical identity

3. Display identity
   - Human-readable fields only (cluster_label, cluster_context, endpoint, etc.)
   - Never sole identity anchor for matching historical truth

Design invariants:
- One normalization function, one canonical ID builder - no duplication
- canonical_entity_id is NEVER derived from display-only fields
- operator_intent_key is pragmatic but explicitly named, not implicit
"""

from __future__ import annotations

from typing import Any

from .entity import build_deterministic_entity_id, build_deterministic_human_id


# Entity type identifier for Alertmanager sources
_ENTITY_TYPE = "alertmanager-source"


def extract_alertmanager_source_facts(
    namespace: str | None,
    name: str | None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
    object_uid: str | None = None,
) -> dict[str, Any]:
    """Extract normalized defining facts for an Alertmanager source.

    This is the SINGLE canonical facts extractor - all canonical ID construction
    flows through here.

    Rules for fact selection:
    - Prefer Kubernetes-native anchors when available (namespace/name)
    - Prefer namespace/name over ephemeral endpoint text when object-backed
    - Include origin family when it affects identity (CRD vs heuristic)
    - Include cluster_uid when available for cross-cluster disambiguation
    - Include object_uid when available (native K8s UID)
    - Exclude purely display-only formatting (cluster_label, cluster_context)

    Args:
        namespace: Kubernetes namespace (preferred identity anchor)
        name: Kubernetes resource name (preferred identity anchor)
        origin: Origin family (alertmanager-crd, prometheus-crd-config, service-heuristic)
        endpoint: Service endpoint (fallback when no namespace/name)
        cluster_uid: Cluster UID from kube-system namespace (for cross-cluster disambiguation)
        object_uid: Native Kubernetes object UID (highest confidence anchor)

    Returns:
        Normalized facts dict for canonical ID construction.
        Keys are sorted for deterministic ordering.

    Example:
        >>> facts = extract_alertmanager_source_facts(
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ...     origin="alertmanager-crd",
        ... )
        >>> # facts = {"name": "alertmanager-main", "namespace": "monitoring", "origin": "alertmanager-crd"}
    """
    facts: dict[str, Any] = {}

    # Kubernetes-native anchors (preferred)
    if namespace is not None:
        facts["namespace"] = namespace
    if name is not None:
        facts["name"] = name

    # Origin family affects identity (CRD vs heuristic may have different endpoints)
    if origin is not None:
        facts["origin"] = origin

    # Include cluster_uid for cross-cluster disambiguation when available
    # This ensures same namespace/name in different clusters => different IDs
    if cluster_uid is not None:
        facts["cluster_uid"] = cluster_uid

    # Include native object UID when available (highest confidence anchor)
    # This is particularly useful for CRD-backed Alertmanagers
    if object_uid is not None:
        facts["object_uid"] = object_uid

    # Fallback: endpoint only when no namespace/name available
    # This handles edge cases like manually configured external Alertmanagers
    if not facts.get("namespace") and not facts.get("name"):
        if endpoint is not None:
            # Normalize endpoint for consistent identity
            normalized_endpoint = _normalize_endpoint_for_facts(endpoint)
            facts["endpoint"] = normalized_endpoint

    return facts


def _normalize_endpoint_for_facts(endpoint: str) -> str:
    """Normalize endpoint for use in canonical facts.

    Strip scheme and trailing slash for consistent identity:
    'http://alertmanager-main.monitoring:9093/' -> 'alertmanager-main.monitoring:9093'
    """
    normalized = endpoint.rstrip("/")
    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]
    return normalized


def build_alertmanager_canonical_entity_id(
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
    object_uid: str | None = None,
) -> str:
    """Build canonical entity ID for an Alertmanager source.

    This generates a deterministic, opaque ID (hex-encoded SHA-256 hash)
    from normalized defining facts. The same source facts always produce
    the same ID.

    This is the SINGLE canonical ID builder - all canonical identity
    flows through extract_alertmanager_source_facts() then here.

    IMPORTANT: This is the canonical historical identity, NOT the operator-intent
    key. Use build_alertmanager_operator_intent_key() for durable persistence.

    Invariants:
        - Same source rediscovered => same canonical_entity_id
        - Different source facts => different canonical_entity_id
        - Display changes (cluster_label, cluster_context) do NOT change this ID

    Args:
        namespace: Kubernetes namespace
        name: Kubernetes resource name
        origin: Origin family
        endpoint: Service endpoint (fallback when no namespace/name)
        cluster_uid: Cluster UID for cross-cluster disambiguation
        object_uid: Native Kubernetes object UID

    Returns:
        32-character hex string (128-bit deterministic ID)

    Example:
        >>> id1 = build_alertmanager_canonical_entity_id(
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ...     origin="alertmanager-crd",
        ... )
        >>> id2 = build_alertmanager_canonical_entity_id(
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ...     origin="alertmanager-crd",
        ... )
        >>> id1 == id2
        True
    """
    facts = extract_alertmanager_source_facts(
        namespace=namespace,
        name=name,
        origin=origin,
        endpoint=endpoint,
        cluster_uid=cluster_uid,
        object_uid=object_uid,
    )
    return build_deterministic_entity_id(_ENTITY_TYPE, facts)


def build_alertmanager_canonical_human_id(
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
    object_uid: str | None = None,
) -> str:
    """Build human-readable deterministic identity for debugging/logging.

    Unlike build_alertmanager_canonical_entity_id(), this returns a
    human-readable string useful for debugging and logging.

    This is NOT the canonical entity ID - it's for human comprehension only.

    Args:
        Same as build_alertmanager_canonical_entity_id()

    Returns:
        Human-readable ID string (e.g., "monitoring/alertmanager-main")

    Example:
        >>> build_alertmanager_canonical_human_id(
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ... )
        'monitoring/alertmanager-main'
    """
    facts = extract_alertmanager_source_facts(
        namespace=namespace,
        name=name,
        origin=origin,
        endpoint=endpoint,
        cluster_uid=cluster_uid,
        object_uid=object_uid,
    )
    return build_deterministic_human_id(_ENTITY_TYPE, facts)


def build_alertmanager_operator_intent_key(
    cluster_label: str | None = None,
    cluster_context: str | None = None,
    namespace: str | None = None,
    name: str | None = None,
    origin: str | None = None,
    endpoint: str | None = None,
    cluster_uid: str | None = None,
) -> str:
    """Build operator-intent persistence key for durable actions.

    This key is used ONLY for durable operator actions (promote/disable)
    and override persistence. It is NOT the canonical historical identity.

    Design rationale:
    - cluster_label is preferred over cluster_context because it is
      operator-controlled and stable across kubeconfig edits/renames
    - cluster_context can change with kubeconfig edits, aliases, or renames
    - For the same source facts, operator_intent_key should remain stable
      across context renames when cluster_label is used

    CRITICAL: This is NOT canonical_entity_id. Do not present this as
    canonical historical identity. Document clearly at call sites.

    Args:
        cluster_label: Operator-facing cluster label (PREFERRED for stability)
        cluster_context: Kubernetes context (may change with kubeconfig)
        namespace: Kubernetes namespace for source
        name: Kubernetes resource name
        origin: Origin family
        endpoint: Service endpoint (fallback)
        cluster_uid: Cluster UID (available when derived)

    Returns:
        Operator-intent key string (format: "cluster_key:source_identity")

    Example:
        >>> # Same source, cluster_context renamed
        >>> key1 = build_alertmanager_operator_intent_key(
        ...     cluster_label="prod-cluster",
        ...     cluster_context="admin@old-context",
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ... )
        >>> key2 = build_alertmanager_operator_intent_key(
        ...     cluster_label="prod-cluster",  # Stable!
        ...     cluster_context="admin@new-context",  # Changed
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ... )
        >>> key1 == key2
        True  # cluster_label preserved across context rename
    """
    # Prefer cluster_label (operator-controlled, stable)
    # Fall back to cluster_context when cluster_label unavailable
    if cluster_label:
        cluster_key = cluster_label
    elif cluster_context:
        cluster_key = cluster_context
    else:
        cluster_key = "unknown"

    # Build source identity - prefer namespace/name when available
    # This matches the canonical identity construction pattern
    if namespace and name:
        source_identity = f"{namespace}/{name}"
    elif endpoint:
        source_identity = _normalize_endpoint_for_facts(endpoint)
    else:
        # Fallback to just the cluster portion if no source identity
        source_identity = "unknown"

    return f"{cluster_key}:{source_identity}"


def get_canonical_identity_summary(
    namespace: str | None = None,
    name: str | None = None,
    endpoint: str | None = None,
) -> str:
    """Get human-readable canonical identity summary.

    This is the namespace/name format used for display and registry matching.
    It's not the canonical_entity_id (opaque hash), but the stable string
    representation that humans and registry keys use.

    Args:
        namespace: Kubernetes namespace
        name: Kubernetes resource name
        endpoint: Service endpoint (fallback)

    Returns:
        Canonical identity string (e.g., "monitoring/alertmanager-main")

    Example:
        >>> get_canonical_identity_summary(
        ...     namespace="monitoring",
        ...     name="alertmanager-main",
        ... )
        'monitoring/alertmanager-main'
    """
    if namespace and name:
        return f"{namespace}/{name}"
    elif endpoint:
        return _normalize_endpoint_for_facts(endpoint)
    return "unknown"
