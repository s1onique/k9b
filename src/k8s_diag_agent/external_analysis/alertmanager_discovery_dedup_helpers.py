"""Service heuristic deduplication helpers.

This module contains helper functions for deduplicating SERVICE_HEURISTIC sources
that point to the same endpoint. It handles the common Prometheus Operator pattern
where:
- alertmanager-operated (headless, clusterIP: None) - operator governing service
- kube-prometheus-stack-alertmanager (chart service) - user-facing service

Both point to the same Alertmanager pod but should be collapsed into one source.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k8s_diag_agent.external_analysis.alertmanager_discovery_models import (
        AlertmanagerSource,
    )


@dataclass(frozen=True)
class ServiceHeuristicDedupGroup:
    """A group of SERVICE_HEURISTIC sources that point to the same logical Alertmanager.
    
    Attributes:
        preferred: The preferred source (chart service > -operated > other)
        aliases: Other sources that are aliases of the preferred one
    """
    preferred: "AlertmanagerSource"
    aliases: tuple["AlertmanagerSource", ...]


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


def _get_preference_score(source: "AlertmanagerSource") -> int:
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


def deduplicate_service_heuristic_sources(
    sources: list["AlertmanagerSource"],
) -> tuple[ServiceHeuristicDedupGroup, ...]:
    """Deduplicate SERVICE_HEURISTIC sources by endpoint into groups.
    
    When multiple SERVICE_HEURISTIC sources point to the same endpoint,
    this function groups them and identifies a preferred source for each group.
    
    Priority for preferred source:
    1. Chart services (kube-prometheus-stack-alertmanager) - user-facing
    2. Non-operated services
    3. -operated services (operator-governed backing services)
    
    This handles the common Prometheus Operator pattern where:
    - alertmanager-operated (headless, clusterIP: None) - operator governing service
    - kube-prometheus-stack-alertmanager (chart service) - user-facing service
    
    Both point to the same Alertmanager pod but should be collapsed into one source.
    
    Importantly, this function handles MULTIPLE groups:
    - Group A: alertmanager-operated + kube-prometheus-stack-alertmanager (same endpoint)
    - Group B: another-standalone-alertmanager (different endpoint)
    
    Result: 2 groups, 2 logical Alertmanagers.
    
    Args:
        sources: List of AlertmanagerSource objects (all SERVICE_HEURISTIC)
        
    Returns:
        Tuple of ServiceHeuristicDedupGroup, one per unique endpoint
    """
    if not sources:
        return ()
    
    # Group by normalized endpoint
    by_endpoint: dict[str, list[AlertmanagerSource]] = {}
    for source in sources:
        norm_ep = _normalize_endpoint(source.endpoint)
        if norm_ep not in by_endpoint:
            by_endpoint[norm_ep] = []
        by_endpoint[norm_ep].append(source)
    
    # Create a dedup group for each endpoint
    groups: list[ServiceHeuristicDedupGroup] = []
    
    for endpoint_group in by_endpoint.values():
        if len(endpoint_group) == 1:
            # Only one source for this endpoint - it's its own group
            groups.append(ServiceHeuristicDedupGroup(
                preferred=endpoint_group[0],
                aliases=(),
            ))
            continue
        
        # Multiple sources for same endpoint - find the preferred one
        # Sort by preference score (lower is better)
        sorted_sources = sorted(endpoint_group, key=_get_preference_score)
        preferred = sorted_sources[0]
        alias_sources = tuple(sorted_sources[1:])
        
        groups.append(ServiceHeuristicDedupGroup(
            preferred=preferred,
            aliases=alias_sources,
        ))
    
    return tuple(groups)
