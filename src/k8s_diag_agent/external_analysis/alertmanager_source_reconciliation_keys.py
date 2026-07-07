"""Alertmanager source reconciliation key types and utilities.

This module provides the core identity types for reconciliation:
- LogicalSourceKey: frozen identity for comparing sources
- normalize_endpoint(): endpoint normalization for fallback matching
"""

from __future__ import annotations

from dataclasses import dataclass

from .alertmanager_discovery_backing_identity import BackingPodIdentity
from .alertmanager_discovery_models import AlertmanagerSource


@dataclass(frozen=True)
class LogicalSourceKey:
    """A logical identity key for Alertmanager source reconciliation.

    This combines cluster context, namespace, and backing pod identity
    to determine if two sources point to the same logical Alertmanager.
    """
    cluster_context: str
    namespace: str
    # Either pod UIDs (preferred) or normalized endpoint (fallback)
    identity_kind: str  # "backing_pods" or "endpoint"
    identity_value: tuple[str, ...]  # sorted pod UIDs or (normalized_endpoint,)


def _normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint for comparison.

    Strips protocol prefix and trailing slashes for consistent comparison.
    """
    ep = endpoint.rstrip("/")
    if ep.startswith("http://"):
        ep = ep[7:]
    elif ep.startswith("https://"):
        ep = ep[8:]
    return ep


def normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint for fallback identity matching.

    Alias for _normalize_endpoint exposed for external use.
    """
    return _normalize_endpoint(endpoint)


def compute_logical_source_key(
    source: AlertmanagerSource,
    backing_identity: BackingPodIdentity | None,
    kube_context: str | None = None,
) -> LogicalSourceKey:
    """Compute the logical identity key for a source.

    Uses backing pod UIDs when available (most accurate), falls back
    to normalized endpoint when backing identity is unavailable.

    Args:
        source: The Alertmanager source
        backing_identity: Backing pod identity from EndpointSlices (may be None)
        kube_context: Kubernetes context for cluster identification

    Returns:
        LogicalSourceKey for comparing sources
    """
    cluster = kube_context or source.cluster_context or source.cluster_label or "unknown"
    namespace = source.namespace or "default"

    if backing_identity is not None and backing_identity.uid_set:
        return LogicalSourceKey(
            cluster_context=cluster,
            namespace=namespace,
            identity_kind="backing_pods",
            identity_value=tuple(sorted(backing_identity.uid_set)),
        )

    # Fallback to endpoint-based identity
    return LogicalSourceKey(
        cluster_context=cluster,
        namespace=namespace,
        identity_kind="endpoint",
        identity_value=(normalize_endpoint(source.endpoint),),
    )


__all__ = [
    "LogicalSourceKey",
    "compute_logical_source_key",
    "normalize_endpoint",
]
