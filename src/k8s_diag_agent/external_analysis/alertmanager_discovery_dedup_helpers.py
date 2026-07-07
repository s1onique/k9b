"""Service heuristic deduplication helpers.

This module contains helper functions for deduplicating SERVICE_HEURISTIC sources
that point to the same Alertmanager backing pods. It handles the common
Prometheus Operator pattern where:
- alertmanager-operated (headless, clusterIP: None) - operator governing service
- kube-prometheus-stack-alertmanager (chart service) - user-facing service

Both point to the same Alertmanager pod but should be collapsed into one source.

Deduplication is done by comparing backing pod UIDs from Kubernetes EndpointSlices.
Pod UIDs are preferred over pod IPs because IPs can change when pods restart,
while UIDs are stable identifiers for the pod's logical identity.

The backing pod identity extraction is handled by alertmanager_discovery_backing_identity.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
        BackingPodIdentity,
    )
    from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
        AlertmanagerSource,
    )

# Import the backing identity module for the main entry point
from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    BackingPodIdentity as _BackingPodIdentity,
)
from k8s_diag_agent.external_analysis.alertmanager_discovery_backing_identity import (
    get_service_backing_identity as _get_service_backing_identity,
)

# Module logger
_logger = logging.getLogger(__name__)


# Re-export for backwards compatibility with existing imports
# TODO: Update imports to use alertmanager_discovery_backing_identity directly
BackingPodIdentity = _BackingPodIdentity
_get_service_backing_pods = _get_service_backing_identity  # Alias for backwards compat


@dataclass(frozen=True)
class ServiceHeuristicDedupGroup:
    """A group of SERVICE_HEURISTIC sources that point to the same logical Alertmanager.
    
    Attributes:
        preferred: The preferred source (chart service > -operated > other)
        aliases: Other sources that are aliases of the preferred one
        raw_candidate_count: Number of raw candidates that collapsed into this group
        deduplicated_service_names: All service names in this dedup group
    """
    preferred: AlertmanagerSource
    aliases: tuple[AlertmanagerSource, ...]
    raw_candidate_count: int = 1
    deduplicated_service_names: tuple[str, ...] = field(default_factory=tuple)


def _is_headless_operated_service(name: str) -> bool:
    """Check if a service name follows the Prometheus Operator '-operated' pattern.
    
    The Prometheus Operator creates a headless governing Service named 'alertmanager-operated'
    by default when serviceName is not set on the Alertmanager resource.
    """
    if not name:
        return False
    return name.lower().endswith('-operated')


def _is_chart_alertmanager_service(name: str) -> bool:
    """Check if a service name looks like a Helm chart Alertmanager service.
    
    Chart services typically have names like:
    - alertmanager (bare)
    - kube-prometheus-stack-alertmanager
    - prometheus-operator-alertmanager
    - grafana-alertmanager
    
    These are user-facing services that should be preferred over -operated services.
    """
    if not name:
        return False
    name_lower = name.lower()
    # Must contain "alertmanager"
    if 'alertmanager' not in name_lower:
        return False
    # Must NOT be an -operated service (those are operator-managed)
    if name_lower.endswith('-operated'):
        return False
    return True


def _normalize_endpoint(ep: str) -> str:
    """Normalize endpoint for comparison.
    
    Strips protocol prefix and trailing slashes for consistent comparison.
    """
    ep = ep.rstrip('/')
    if ep.startswith('http://'):
        ep = ep[7:]
    elif ep.startswith('https://'):
        ep = ep[8:]
    return ep


def _get_preference_score(source: AlertmanagerSource) -> int:
    """Get preference score for a source (lower is better).
    
    Priority:
    1. Chart services (user-facing, preferred)
    2. Non-operated services
    3. -operated services (operator-governed backing services)
    """
    name = source.name or ''
    if _is_chart_alertmanager_service(name):
        return 0
    if _is_headless_operated_service(name):
        return 2
    return 1


def _build_backing_pod_cache(
    sources: list[AlertmanagerSource],
    context: str | None = None,
) -> dict[str, BackingPodIdentity | None]:
    """Build a cache of service backing pod identities.
    
    Args:
        sources: List of AlertmanagerSource objects
        context: Kubernetes context for kubectl
        
    Returns:
        Dict mapping "namespace/name" to BackingPodIdentity (or None if unavailable)
    """
    cache: dict[str, BackingPodIdentity | None] = {}
    
    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            if key not in cache:
                cache[key] = _get_service_backing_identity(
                    source.namespace,
                    source.name,
                    context=context,
                )
    
    return cache


# Type alias for deduplication grouping key
# Uses namespaced tuple to prevent collisions between pod-backed and endpoint fallback keys
DedupKey = tuple[str, str | tuple[str, ...]]


def _get_identity_key(identity: BackingPodIdentity | None) -> DedupKey:
    """Build a dedup key from a BackingPodIdentity.
    
    Priority:
    1. Pod UIDs (most stable)
    2. Pod namespace/name (fallback)
    3. Service endpoint (last resort)
    """
    if identity is not None and identity.uid_set:
        # Use pod UIDs for identity
        return ("pods", tuple(sorted(identity.uid_set)))
    elif identity is not None and identity.name_set:
        # Use pod namespace/name as fallback
        return ("pods", tuple(sorted(identity.name_set)))
    else:
        # Service endpoint fallback
        return ("endpoint", "")


def _group_by_backing_pods(
    sources: list[AlertmanagerSource],
    backing_pod_cache: dict[str, BackingPodIdentity | None],
) -> dict[DedupKey, tuple[BackingPodIdentity | None, list[AlertmanagerSource]]]:
    """Group sources by their backing pod identities.
    
    Sources that share the same backing pod UIDs (even with different service names)
    are grouped together as aliases.
    
    Sources with unavailable backing pod info (None) are grouped by endpoint URL.
    
    Args:
        sources: List of AlertmanagerSource objects
        backing_pod_cache: Cache of service backing pod identities
        
    Returns:
        Dict mapping dedup key to (BackingPodIdentity, list of sources) tuples
    """
    # Group by backing pods where available
    by_pods: dict[DedupKey, tuple[BackingPodIdentity | None, list[AlertmanagerSource]]] = {}
    no_pod_info: list[AlertmanagerSource] = []
    
    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            identity = backing_pod_cache.get(key)
        else:
            identity = None
        
        if identity is not None and (identity.uid_set or identity.name_set):
            # Use pod UID-based key
            dedup_key = _get_identity_key(identity)
            if dedup_key not in by_pods:
                by_pods[dedup_key] = (identity, [])
            by_pods[dedup_key][1].append(source)
        else:
            no_pod_info.append(source)
    
    # For sources without pod info, fall back to endpoint grouping
    if no_pod_info:
        by_endpoint: dict[str, list[AlertmanagerSource]] = {}
        for source in no_pod_info:
            norm_ep = _normalize_endpoint(source.endpoint)
            if norm_ep not in by_endpoint:
                by_endpoint[norm_ep] = []
            by_endpoint[norm_ep].append(source)
        
        # Add endpoint fallback groups with namespaced key
        for norm_ep, sources_list in by_endpoint.items():
            # Use namespaced key: ("endpoint", normalized_endpoint)
            endpoint_key: DedupKey = ("endpoint", norm_ep)
            if endpoint_key not in by_pods:
                by_pods[endpoint_key] = (None, [])
            by_pods[endpoint_key][1].extend(sources_list)
    
    return by_pods


def deduplicate_service_heuristic_sources(
    sources: list[AlertmanagerSource],
    kube_context: str | None = None,
) -> tuple[ServiceHeuristicDedupGroup, ...]:
    """Deduplicate SERVICE_HEURISTIC sources by backing pod identity.
    
    When multiple SERVICE_HEURISTIC sources point to the same backing pods,
    this function groups them and identifies a preferred source for each group.
    
    Priority for preferred source (lower score = preferred):
    1. Non-headless ClusterIP (vs clusterIP: None)
    2. Non-*-operated service (vs alertmanager-operated)
    3. HTTP data-plane port (http-web/9093 wins over mesh/reloader ports)
    4. More specific selector (e.g., alertmanager=kube-prometheus-stack-alertmanager)
    5. Chart-facing labels (vs operator-internal labels)
    
    This handles the common Prometheus Operator pattern where:
    - alertmanager-operated (headless, clusterIP: None) - operator governing service
    - kube-prometheus-stack-alertmanager (chart service) - user-facing service
    
    Both point to the same Alertmanager pod but should be collapsed into one source.
    
    Importantly, this function handles MULTIPLE groups:
    - Group A: alertmanager-operated + kube-prometheus-stack-alertmanager (same pods)
    - Group B: another-standalone-alertmanager (different pods)
    
    Result: 2 groups, 2 logical Alertmanagers.
    
    Args:
        sources: List of AlertmanagerSource objects (all SERVICE_HEURISTIC)
        kube_context: Kubernetes context for endpoint slice queries
        
    Returns:
        Tuple of ServiceHeuristicDedupGroup, one per unique backing pod set
    """
    if not sources:
        return ()
    
    # Build cache of backing pod identities for each service
    backing_pod_cache = _build_backing_pod_cache(sources, context=kube_context)
    
    _logger.debug(
        "Built backing pod cache for %d sources, %d entries",
        len(sources),
        len(backing_pod_cache),
    )
    
    # Log what we found
    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            identity = backing_pod_cache.get(key)
            if identity:
                _logger.debug(
                    "Service %s/%s backs pods: uids=%s, names=%s",
                    source.namespace,
                    source.name,
                    identity.uid_set if identity.uid_set else "none",
                    identity.name_set if identity.name_set else "none",
                )
            else:
                _logger.debug(
                    "Service %s/%s backing pod identity: unavailable",
                    source.namespace,
                    source.name,
                )
    
    # Group sources by backing pod identity
    by_pods = _group_by_backing_pods(sources, backing_pod_cache)
    
    # Create dedup groups
    groups: list[ServiceHeuristicDedupGroup] = []
    
    for dedup_key, (identity, pod_sources) in by_pods.items():
        # Collect all service names in this group
        all_service_names: list[str] = []
        for source in pod_sources:
            if source.name:
                all_service_names.append(source.name)
        
        if len(pod_sources) == 1:
            # Only one source for this pod set - it's its own group
            groups.append(ServiceHeuristicDedupGroup(
                preferred=pod_sources[0],
                aliases=(),
                raw_candidate_count=1,
                deduplicated_service_names=tuple(all_service_names),
            ))
            continue
        
        # Multiple sources for same pod set - find the preferred one
        # Sort by preference score (lower is better)
        sorted_sources = sorted(pod_sources, key=_get_preference_score)
        preferred = sorted_sources[0]
        alias_sources = tuple(sorted_sources[1:])
        
        identity_desc = "unknown"
        if identity and identity.uid_set:
            identity_desc = f"uids={len(identity.uid_set)}"
        elif identity and identity.name_set:
            identity_desc = f"names={len(identity.name_set)}"
        else:
            identity_desc = "endpoint-based"
        
        _logger.debug(
            "Deduplicated %d sources to preferred=%s, aliases=%s (backing: %s)",
            len(pod_sources),
            f"{preferred.namespace}/{preferred.name}",
            [f"{s.namespace}/{s.name}" for s in alias_sources],
            identity_desc,
        )
        
        groups.append(ServiceHeuristicDedupGroup(
            preferred=preferred,
            aliases=alias_sources,
            raw_candidate_count=len(pod_sources),
            deduplicated_service_names=tuple(all_service_names),
        ))
    
    return tuple(groups)
