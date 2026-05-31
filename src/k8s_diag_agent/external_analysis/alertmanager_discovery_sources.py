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

from .alertmanager_discovery_crd_strategy import (
    _IN_CLUSTER_CONTEXT,
    _kubectl_context_args,
    _should_add_context_flag,
)
from .alertmanager_discovery_models import (
    AlertmanagerSource,
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


def _resolve_prometheus_operator_alias(
    source: AlertmanagerSource,
    all_sources: dict[str, AlertmanagerSource],
) -> AlertmanagerSource:
    """Resolve Prometheus Operator alias: alertmanager-operated -> CRD-backed AM.
    
    In Prometheus Operator deployments:
    - CRD is named 'alertmanager-main' (or similar)
    - The actual service is 'alertmanager-operated' (conventional suffix)
    
    When a service heuristic finds 'alertmanager-operated', it should share the
    same canonical identity as the CRD-backed Alertmanager in the same namespace
    IF there's an unambiguous mapping (only one CRD Alertmanager in that namespace).
    
    This ensures that:
    - CRD source: monitoring/alertmanager-main (points to alertmanager-operated.monitoring:9093)
    - Service source: monitoring/alertmanager-operated (same endpoint)
    
    Both resolve to canonical identity 'monitoring/alertmanager-main' (the CRD's name).
    """
    # Only apply alias resolution for service heuristic sources
    if source.origin != AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
        return source
    
    # Check if this is the alertmanager-operated pattern
    name = source.name or ''
    if not name.endswith('-operated'):
        return source
    
    # Find CRD sources in the same namespace
    crd_in_namespace = [
        s for s in all_sources.values()
        if s.namespace == source.namespace
        and s.origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD
    ]
    
    # Only apply when there's exactly one CRD Alertmanager in this namespace
    # (unambiguous mapping)
    if len(crd_in_namespace) != 1:
        return source
    
    crd_source = crd_in_namespace[0]
    
    # Create aliased source with CRD's namespace/name but keep service's endpoint
    # (since they both point to the same endpoint: alertmanager-operated.svc:9093)
    # Preserve identity anchors from the source (cluster_uid/object_uid)
    aliased_source = AlertmanagerSource(
        source_id=f'service:{source.namespace}/{crd_source.name}',  # Use CRD name
        endpoint=source.endpoint,  # Keep the actual endpoint
        namespace=source.namespace,
        name=crd_source.name,  # Use CRD name for canonical identity
        origin=source.origin,
        state=source.state,
        discovered_at=source.discovered_at,
        verified_at=source.verified_at,
        last_check=source.last_check,
        last_error=source.last_error,
        verified_version=source.verified_version,
        confidence_hints=source.confidence_hints + ('prometheus-operator-alias',),
        merged_provenances=source.merged_provenances,
        cluster_label=source.cluster_label,
        cluster_context=source.cluster_context,
        cluster_uid=source.cluster_uid,
        object_uid=source.object_uid,
    )
    
    _logger.debug(
        'Resolved Prometheus Operator alias: %s/%s -> %s/%s (endpoint %s)',
        source.namespace,
        source.name,
        source.namespace,
        crd_source.name,
        source.endpoint,
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
