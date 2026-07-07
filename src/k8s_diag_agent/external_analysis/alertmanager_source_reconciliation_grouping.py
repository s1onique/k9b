"""Alertmanager source reconciliation grouping helpers.

This module provides grouping logic for sources by backing identity:
- ReconciliationGroup: a group of sources representing the same logical Alertmanager
- Backing identity cache construction
- Source grouping by backing identity
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alertmanager_discovery_backing_identity import BackingPodIdentity
    from .alertmanager_discovery_models import AlertmanagerSource
    from .alertmanager_source_reconciliation_keys import LogicalSourceKey

from .alertmanager_discovery_backing_identity import get_service_backing_identity
from .alertmanager_discovery_dedup_helpers import (
    _is_ambiguous_operated_service,
    _is_chart_alertmanager_service,
    _is_headless_operated_service,
)
from .alertmanager_source_reconciliation_keys import (
    LogicalSourceKey,
    compute_logical_source_key,
)

# Module logger
_logger = logging.getLogger(__name__)


@dataclass
class ReconciliationGroup:
    """A group of sources that represent the same logical Alertmanager."""
    canonical: AlertmanagerSource
    aliases: list[AlertmanagerSource] = field(default_factory=list)
    backing_identity: BackingPodIdentity | None = None
    all_service_names: list[str] = field(default_factory=list)


def _compute_reconciliation_priority(source: AlertmanagerSource) -> int:
    """Compute reconciliation priority score (lower is better).

    Priority:
    1. Manual/promoted sources (always preferred)
    2. Non-headless chart-facing services
    3. Alertmanager CR-backed services
    4. Operator headless alertmanager-operated
    5. Other services
    """
    # Manual/promoted sources get highest priority (0)
    if source.origin.value == "manual":
        return 0
    if source.manual_source_mode.value != "not-manual":
        return 0

    name = source.name or ""

    # Chart-facing services get priority 1
    if _is_chart_alertmanager_service(name):
        return 1

    # CR-backed services (not from service heuristic) get priority 2
    if source.origin.value == "alertmanager-crd":
        return 2

    # Operator headless services get priority 3
    if _is_headless_operated_service(name):
        return 3

    # All other services get priority 4
    return 4


def build_backing_identity_cache(
    sources: list[AlertmanagerSource],
    kube_context: str | None = None,
) -> dict[str, BackingPodIdentity | None]:
    """Build a cache of backing pod identities for sources.

    Args:
        sources: List of Alertmanager sources
        kube_context: Kubernetes context for kubectl

    Returns:
        Dict mapping "namespace/name" to BackingPodIdentity
    """
    cache: dict[str, BackingPodIdentity | None] = {}

    for source in sources:
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            if key not in cache:
                cache[key] = get_service_backing_identity(
                    source.namespace,
                    source.name,
                    context=kube_context,
                )

    return cache


def group_sources_by_backing_identity(
    sources: list[AlertmanagerSource],
    backing_cache: dict[str, BackingPodIdentity | None],
    kube_context: str | None = None,
) -> dict[LogicalSourceKey, ReconciliationGroup]:
    """Group sources by their logical backing identity.

    Sources that share the same backing pod UIDs (even with different service names)
    are grouped together as aliases.

    Args:
        sources: List of Alertmanager sources to group
        backing_cache: Pre-computed backing pod identity cache
        kube_context: Kubernetes context for cluster identification

    Returns:
        Dict mapping LogicalSourceKey to ReconciliationGroup
    """
    groups: dict[LogicalSourceKey, ReconciliationGroup] = {}

    for source in sources:
        # Get backing identity for this source
        if source.namespace and source.name:
            key = f"{source.namespace}/{source.name}"
            backing = backing_cache.get(key)
        else:
            backing = None

        # Compute logical key
        log_key = compute_logical_source_key(source, backing, kube_context)
        
        # For ambiguous -operated services, add service name to key to prevent
        # grouping with CRDs that share the same endpoint
        if _is_ambiguous_operated_service(source, sources):
            # Create a unique key that includes the service name to prevent merging
            # with CRDs that have the same endpoint
            log_key = LogicalSourceKey(
                cluster_context=log_key.cluster_context,
                namespace=log_key.namespace,
                identity_kind="ambiguous_operated_service",
                identity_value=(f"{source.namespace}/{source.name}",) + log_key.identity_value,
            )

        if log_key not in groups:
            groups[log_key] = ReconciliationGroup(
                canonical=source,
                backing_identity=backing,
                all_service_names=[],
            )

        # Track all service names in this group
        if source.name:
            groups[log_key].all_service_names.append(source.name)

        # If this source has better priority than current canonical, swap
        current_canonical = groups[log_key].canonical
        if _compute_reconciliation_priority(source) < _compute_reconciliation_priority(current_canonical):
            # Add old canonical as alias
            groups[log_key].aliases.append(current_canonical)
            groups[log_key].canonical = source
            groups[log_key].backing_identity = backing
        elif source != current_canonical:
            # Add as alias
            groups[log_key].aliases.append(source)

    return groups


__all__ = [
    "ReconciliationGroup",
    "build_backing_identity_cache",
    "group_sources_by_backing_identity",
    "_compute_reconciliation_priority",
]
