"""Alertmanager source construction helpers.

This module provides the source construction logic for Alertmanager discovery:
- Source construction helpers for manual endpoints
- Prometheus Operator alias resolution
- Endpoint/source-id construction helpers

The module answers: "Given config/manual endpoint data, construct AlertmanagerSource objects."

It does NOT include:
- HTTP verification of Alertmanager endpoints
- High-level orchestration of discovery runs
- Inventory persistence/loading/writing
- Discovery strategies (see alertmanager_discovery_strategies)
"""

from __future__ import annotations

import logging
from dataclasses import replace as _replace

from .alertmanager_discovery_crd_strategy import (
    _IN_CLUSTER_CONTEXT,
    _kubectl_context_args,
    _should_add_context_flag,
)
from .alertmanager_discovery_models import (
    AlertmanagerSource,
    AlertmanagerSourceAlias,
    AlertmanagerSourceMode,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)

# Module logger for debug output
_logger = logging.getLogger(__name__)


# --- Manual Source Construction ---


def build_endpoint_for_manual(
    endpoint: str,
    namespace: str | None = None,
    name: str | None = None,
) -> AlertmanagerSource:
    """Build a manual Alertmanager source from user-provided endpoint.
    
    The source is marked as operator-configured to distinguish it from
    promoted sources (which preserve their discovery origin).
    """
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"

    source_id = f"manual:{endpoint}"
    if namespace and name:
        source_id = f"manual:{namespace}/{name}"

    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        origin=AlertmanagerSourceOrigin.MANUAL,
        state=AlertmanagerSourceState.MANUAL,
        manual_source_mode=AlertmanagerSourceMode.OPERATOR_CONFIGURED,
    )


# --- Prometheus Operator Alias Resolution ---


def _infer_management_type(name: str, endpoint: str) -> str:
    """Infer the management type of a service alias.
    
    Returns:
        - "operator-managed": service ends with '-operated' (Prometheus Operator pattern)
        - "chart-managed": service name matches a known Helm chart pattern
        - "unknown": cannot determine management type
    """
    name_lower = name.lower()
    
    # Operator-managed services follow Prometheus Operator naming convention
    if name_lower.endswith('-operated'):
        return "operator-managed"
    
    # Chart-managed: service name matches common Alertmanager Helm chart patterns
    # Examples: alertmanager, kube-prometheus-stack-alertmanager, prometheus-operator-alertmanager
    chart_patterns = [
        'alertmanager',
        'prometheus-operator-alertmanager',
        'kube-prometheus-stack-alertmanager',
        'grafana-alertmanager',
    ]
    for pattern in chart_patterns:
        if pattern in name_lower:
            return "chart-managed"
    
    return "unknown"


def _resolve_prometheus_operator_alias(
    source: AlertmanagerSource,
    all_sources: dict[str, AlertmanagerSource],
) -> AlertmanagerSource:
    """Resolve Prometheus Operator aliases for service heuristic sources.
    
    In Prometheus Operator deployments:
    - The CRD is named 'alertmanager-main' (or similar)
    - The operator creates a headless service 'alertmanager-operated' (conventional suffix)
    - The Helm chart may create a user-facing service 'alertmanager-main' or similar
    
    When service heuristics find services like 'alertmanager-operated' in the same 
    namespace as a CRD Alertmanager, they should share the same canonical identity 
    as the CRD Alertmanager if there's an unambiguous mapping (only one CRD 
    Alertmanager in that namespace).
    
    If there are multiple CRDs in the namespace, the service is NOT aliased to 
    prevent ambiguous mappings. The service keeps its own canonical identity.
    
    This function:
    1. Identifies if the source is an alias candidate (-operated suffix)
    2. Finds the CRD Alertmanager in the same namespace
    3. Only aliases if there's exactly one CRD in the namespace
    4. Returns the aliased source with CRD's namespace/name, or unchanged source
    """
    # Only apply alias resolution for service heuristic sources
    if source.origin != AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
        return source
    
    name = source.name or ''
    
    # Only alias -operated services (operator-governing services)
    # These are headless services created by Prometheus Operator
    if not name.endswith('-operated'):
        return source
    
    # Find CRD sources in the same namespace
    crd_in_namespace = [
        s for s in all_sources.values()
        if s.namespace == source.namespace
        and s.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    ]
    
    # CRITICAL: Only alias when there's exactly one CRD Alertmanager
    # When multiple CRDs exist, we cannot determine which one the service belongs to
    if len(crd_in_namespace) != 1:
        return source
    
    crd_source = crd_in_namespace[0]
    
    # Infer management type
    management_type = _infer_management_type(name, source.endpoint)
    
    # Create alias record
    alias = AlertmanagerSourceAlias(
        alias_name=name,
        alias_namespace=source.namespace or '',
        alias_endpoint=source.endpoint,
        discovery_method=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        management_type=management_type,
    )
    
    # Check if this alias is already recorded in the CRD source
    existing_aliases = list(crd_source.aliases)
    # Avoid duplicate aliases with same name/endpoint
    if not any(a.alias_name == alias.alias_name and a.alias_endpoint == alias.alias_endpoint 
               for a in existing_aliases):
        existing_aliases.append(alias)
    
    # Create aliased source with CRD's namespace/name but keep service's endpoint
    # (since they both point to the same endpoint: alertmanager-operated.svc:9093)
    # Preserve identity anchors from the source (cluster_uid/object_uid)
    aliased_source = _replace(
        source,
        source_id=f'service:{source.namespace}/{crd_source.name}',  # Use CRD name
        endpoint=source.endpoint,  # Keep the actual endpoint
        namespace=source.namespace,
        name=crd_source.name,  # Use CRD name for canonical identity
        confidence_hints=source.confidence_hints + ('prometheus-operator-alias',),
        # Add the alias to the CRD source's aliases
        aliases=tuple(existing_aliases),
    )
    
    _logger.debug(
        'Resolved Prometheus Operator alias: %s/%s -> %s/%s (endpoint %s, management: %s)',
        source.namespace,
        name,
        source.namespace,
        crd_source.name,
        source.endpoint,
        management_type,
    )
    
    return aliased_source


# --- Re-exports for backward compatibility ---

__all__ = [
    # Sentinel constant
    "_IN_CLUSTER_CONTEXT",
    # Context helpers
    "_should_add_context_flag",
    "_kubectl_context_args",
    # Source construction
    "build_endpoint_for_manual",
    "_resolve_prometheus_operator_alias",
]
