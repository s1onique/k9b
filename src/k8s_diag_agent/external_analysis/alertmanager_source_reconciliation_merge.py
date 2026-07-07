"""Alertmanager source reconciliation merge logic.

This module provides the main reconciliation function:
- reconcile_alertmanager_sources(): collapses duplicate sources by backing identity
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alertmanager_discovery_models import AlertmanagerSource

# Import models for runtime use
from .alertmanager_discovery_dedup_helpers import (
    _is_chart_alertmanager_service,
    _is_headless_operated_service,
)
from .alertmanager_discovery_models import AlertmanagerSourceInventory
from .alertmanager_source_reconciliation_grouping import (
    build_backing_identity_cache,
    group_sources_by_backing_identity,
)

# Module logger
_logger = logging.getLogger(__name__)


def _build_alias_records(source: AlertmanagerSource) -> tuple:
    """Build AlertmanagerSourceAlias records from source data.

    Args:
        source: Source to create alias from

    Returns:
        Tuple of AlertmanagerSourceAlias records
    """
    from .alertmanager_discovery_models import AlertmanagerSourceAlias

    name = source.name or ""
    if _is_headless_operated_service(name):
        management_type = "operator-managed"
    elif _is_chart_alertmanager_service(name):
        management_type = "chart-managed"
    else:
        management_type = "unknown"

    return (
        AlertmanagerSourceAlias(
            alias_name=source.name or "",
            alias_namespace=source.namespace or "",
            alias_endpoint=source.endpoint,
            discovery_method=source.origin,
            management_type=management_type,
        ),
    )


def reconcile_alertmanager_sources(
    inventory: AlertmanagerSourceInventory,
    kube_context: str | None = None,
) -> AlertmanagerSourceInventory:
    """Reconcile Alertmanager sources by collapsing duplicate logical sources.

    This function runs after initial discovery and deduplication to handle
    cases where sources from different discovery strategies (CRD, Prometheus
    config, service heuristic) represent the same logical Alertmanager.

    The reconciliation:
    1. Groups sources by backing pod UIDs (or endpoint fallback)
    2. Selects a canonical source based on priority
    3. Merges aliases into the canonical source
    4. Returns an inventory with logical sources only

    Canonical selection priority:
    1. Already tracked/manual/promoted source
    2. Non-headless chart-facing service
    3. Alertmanager CR-backed service
    4. Operator headless alertmanager-operated
    5. Any reachable endpoint

    Args:
        inventory: Source inventory with potentially duplicate sources
        kube_context: Kubernetes context for backing pod queries

    Returns:
        Reconciled inventory with logical sources and merged aliases
    """
    from dataclasses import replace as _replace

    from .alertmanager_discovery_models import (
        AlertmanagerSourceAlias,
    )

    if not inventory.sources:
        return inventory

    # Build backing identity cache
    sources_list = list(inventory.sources.values())
    backing_cache = build_backing_identity_cache(sources_list, kube_context)

    _logger.debug(
        "Reconciliation: built backing cache for %d sources",
        len(backing_cache),
    )

    # Group sources by backing identity
    groups = group_sources_by_backing_identity(
        sources_list,
        backing_cache,
        kube_context,
    )

    _logger.debug(
        "Reconciliation: grouped into %d logical sources",
        len(groups),
    )

    # Build reconciled sources
    reconciled: dict[str, AlertmanagerSource] = {}

    for log_key, group in groups.items():
        canonical = group.canonical

        # Skip if no meaningful aliases to merge
        if len(group.aliases) == 0:
            reconciled[canonical.canonical_identity] = canonical
            continue

        # Build alias records from all aliases
        all_aliases: list[AlertmanagerSourceAlias] = []

        # Add aliases that aren't already tracked in canonical
        existing_alias_names = {a.alias_name for a in canonical.aliases}
        for alias_source in group.aliases:
            alias_record = _build_alias_records(alias_source)
            for rec in alias_record:
                if rec.alias_name and rec.alias_name not in existing_alias_names:
                    all_aliases.append(rec)
                    existing_alias_names.add(rec.alias_name)

        # Merge with existing aliases in canonical
        merged_aliases = list(canonical.aliases)
        for rec in all_aliases:
            if rec.alias_name not in {a.alias_name for a in merged_aliases}:
                merged_aliases.append(rec)

        # Create reconciled source with merged aliases
        # Preserve canonical's identity and properties
        reconciled_source = _replace(
            canonical,
            aliases=tuple(merged_aliases) if merged_aliases else canonical.aliases,
        )

        # Use canonical_identity as key
        reconciled_key = canonical.canonical_identity
        reconciled[reconciled_key] = reconciled_source

        _logger.debug(
            "Reconciled %d aliases into canonical %s (backing: %s)",
            len(all_aliases),
            canonical.name,
            log_key.identity_kind,
        )

    # Log if we reduced source count
    original_count = len(inventory.sources)
    reconciled_count = len(reconciled)
    if reconciled_count < original_count:
        _logger.info(
            "Reconciliation collapsed %d sources into %d logical sources",
            original_count,
            reconciled_count,
        )

    return AlertmanagerSourceInventory(
        sources=reconciled,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
        artifact_id=inventory.artifact_id,
    )


__all__ = [
    "reconcile_alertmanager_sources",
]
