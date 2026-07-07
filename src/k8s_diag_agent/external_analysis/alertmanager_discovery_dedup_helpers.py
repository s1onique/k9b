"""Service heuristic deduplication helpers.

This module contains helper functions for deduplicating SERVICE_HEURISTIC sources
that point to the same Alertmanager backing pods. It handles the common
Prometheus Operator pattern where:
- alertmanager-operated (headless, clusterIP: None) - operator governing service
- kube-prometheus-stack-alertmanager (chart service) - user-facing service

Both point to the same Alertmanager pod but should be collapsed into one source.

Deduplication is done by comparing backing pod IPs from Kubernetes endpoint slices.
This ensures services with different DNS names but same backing pods are correctly
identified as aliases.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
        AlertmanagerSource,
    )

# Module logger
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceHeuristicDedupGroup:
    """A group of SERVICE_HEURISTIC sources that point to the same logical Alertmanager.
    
    Attributes:
        preferred: The preferred source (chart service > -operated > other)
        aliases: Other sources that are aliases of the preferred one
    """
    preferred: AlertmanagerSource
    aliases: tuple[AlertmanagerSource, ...]


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


def _get_service_backing_pods(
    namespace: str,
    service_name: str,
    context: str | None = None,
) -> frozenset[str] | None:
    """Get the pod IPs backing a service via endpoint slices.
    
    This uses kubectl to query endpoint slices for the service and extracts
    all pod IPs. Returns None on error (non-fatal).
    
    Args:
        namespace: Kubernetes namespace
        service_name: Name of the service
        context: Kubernetes context (optional)
        
    Returns:
        Frozen set of pod IP strings, or None if query failed
    """
    context_args = []
    if context:
        context_args = ["--context", context]
    
    try:
        # Get endpoint slices for this service
        cmd = [
            "kubectl", "get", "endpointslices",
            "-n", namespace,
            "-l", f"kubernetes.io/service-name={service_name}",
            "-o", "json",
        ] + context_args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            _logger.debug(
                "Failed to get endpoint slices for %s/%s: %s",
                namespace, service_name, result.stderr[:200],
            )
            return None
        
        data = json.loads(result.stdout)
        pod_ips: set[str] = set()
        
        for item in data.get("items", []):
            for endpoint in item.get("endpoints", []):
                for address in endpoint.get("addresses", []):
                    if address:
                        pod_ips.add(address)
        
        if pod_ips:
            return frozenset(pod_ips)
        return None
        
    except subprocess.TimeoutExpired:
        _logger.debug("Endpoint slice query timed out for %s/%s", namespace, service_name)
        return None
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Error querying endpoint slices for %s/%s: %s", namespace, service_name, exc)
        return None


def _build_backing_pod_cache(
    sources: list[AlertmanagerSource],
    context: str | None = None,
) -> dict[str, frozenset[str] | None]:
    """Build a cache of service backing pod IPs.
    
    Args:
        sources: List of AlertmanagerSource objects
        context: Kubernetes context for kubectl
        
    Returns:
        Dict mapping "namespace/name" to frozenset of pod IPs (or None if unavailable)
    """
    cache: dict[str, frozenset[str] | None] = {}
    
    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            if key not in cache:
                cache[key] = _get_service_backing_pods(
                    source.namespace,
                    source.name,
                    context=context,
                )
    
    return cache


# Type alias for deduplication grouping key
# Uses namespaced tuple to prevent collisions between pod-backed and endpoint fallback keys
DedupKey = tuple[str, str | tuple[str, ...]]


def _group_by_backing_pods(
    sources: list[AlertmanagerSource],
    backing_pod_cache: dict[str, frozenset[str] | None],
) -> dict[DedupKey, list[AlertmanagerSource]]:
    """Group sources by their backing pod IPs.
    
    Sources that share the same backing pod IPs (even with different service names)
    are grouped together as aliases.
    
    Sources with unavailable backing pod info (None) are grouped by endpoint URL.
    
    Key model (prevents collisions between pod-backed and endpoint fallback):
    - Pod-backed identity: ("pods", tuple(sorted(pod_ips)))
    - Endpoint fallback: ("endpoint", normalized_endpoint)
    
    Args:
        sources: List of AlertmanagerSource objects
        backing_pod_cache: Cache of service backing pods
        
    Returns:
        Dict mapping dedup key to list of sources in that group
    """
    # Group by backing pods where available
    by_pods: dict[DedupKey, list[AlertmanagerSource]] = {}
    no_pod_info: list[AlertmanagerSource] = []
    
    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            pods = backing_pod_cache.get(key)
        else:
            pods = None
        
        if pods is not None:
            # Use namespaced key: ("pods", tuple of sorted IPs)
            pod_key: DedupKey = ("pods", tuple(sorted(pods)))
            if pod_key not in by_pods:
                by_pods[pod_key] = []
            by_pods[pod_key].append(source)
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
            # This prevents collision with pod-backed keys
            endpoint_key: DedupKey = ("endpoint", norm_ep)
            if endpoint_key not in by_pods:
                by_pods[endpoint_key] = []
            by_pods[endpoint_key].extend(sources_list)
    
    return by_pods


def deduplicate_service_heuristic_sources(
    sources: list[AlertmanagerSource],
    kube_context: str | None = None,
) -> tuple[ServiceHeuristicDedupGroup, ...]:
    """Deduplicate SERVICE_HEURISTIC sources by backing pod identity.
    
    When multiple SERVICE_HEURISTIC sources point to the same backing pods,
    this function groups them and identifies a preferred source for each group.
    
    Priority for preferred source:
    1. Chart services (kube-prometheus-stack-alertmanager) - user-facing
    2. Non-operated services
    3. -operated services (operator-governed backing services)
    
    This handles the common Prometheus Operator pattern where:
    - alertmanager-operated (headless, clusterIP: None) - operator governing service
    - kube-prometheus-stack-alertmanager (chart service) - user-facing service
    
    Both point to the same Alertmanager pod but should be collapsed into one source.
    
    Deduplication is done by comparing backing pod IPs from Kubernetes endpoint slices.
    This ensures services with different DNS names but same backing pods are correctly
    identified as aliases.
    
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
    
    # Build cache of backing pod IPs for each service
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
            pods = backing_pod_cache.get(key)
            _logger.debug(
                "Service %s/%s backs pods: %s",
                source.namespace,
                source.name,
                pods if pods else "unavailable",
            )
    
    # Group sources by backing pods
    by_pods = _group_by_backing_pods(sources, backing_pod_cache)
    
    # Create dedup groups
    groups: list[ServiceHeuristicDedupGroup] = []
    
    for pod_set, pod_sources in by_pods.items():
        if len(pod_sources) == 1:
            # Only one source for this pod set - it's its own group
            groups.append(ServiceHeuristicDedupGroup(
                preferred=pod_sources[0],
                aliases=(),
            ))
            continue
        
        # Multiple sources for same pod set - find the preferred one
        # Sort by preference score (lower is better)
        sorted_sources = sorted(pod_sources, key=_get_preference_score)
        preferred = sorted_sources[0]
        alias_sources = tuple(sorted_sources[1:])
        
        _logger.debug(
            "Deduplicated %d sources to preferred=%s, aliases=%s (backing pods: %s)",
            len(pod_sources),
            f"{preferred.namespace}/{preferred.name}",
            [f"{s.namespace}/{s.name}" for s in alias_sources],
            pod_set if pod_set else "endpoint-based",
        )
        
        groups.append(ServiceHeuristicDedupGroup(
            preferred=preferred,
            aliases=alias_sources,
        ))
    
    return tuple(groups)
