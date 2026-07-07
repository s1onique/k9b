"""Alertmanager source registry reconciliation for persisted duplicates.

This module provides reconciliation logic for persisted registry entries:
- detect_duplicate_registry_entries(): find duplicates in existing registry
- collapse_duplicate_registry_entries(): migrate registry to canonical entries

Priority for registry entries (higher = more authoritative):
1. manual/tracked desired state - operator-promoted, never collapsed away
2. disabled desired state - explicitly excluded, preserved
3. chart-facing services - kube-prometheus-stack-alertmanager
4. Alertmanager CRD / Prometheus CRD config
5. headless -operated services - lowest service type priority
6. generic service heuristic - resolved by service-name classification

Note: Manual sources are not collapsed away. They win canonical when exact
identity evidence matches. Discovered sources become aliases.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .alertmanager_discovery_backing_identity import BackingPodIdentity
    from .alertmanager_discovery_models import (
        AlertmanagerSource,
        AlertmanagerSourceInventory,
    )
    from .alertmanager_source_models import (
        AlertmanagerSourceRegistry,
        RegistryEntry,
    )

from .alertmanager_discovery_dedup_helpers import (
    _is_chart_alertmanager_service,
    _is_headless_operated_service,
)
from .alertmanager_source_reconciliation_grouping import build_backing_identity_cache
from .alertmanager_source_reconciliation_keys import LogicalSourceKey

# Module logger
_logger = logging.getLogger(__name__)


def detect_duplicate_registry_entries(
    registry: AlertmanagerSourceRegistry | None,
    inventory: AlertmanagerSourceInventory,
    kube_context: str | None = None,
) -> list[tuple[str, str]]:
    """Detect duplicate entries in registry that map to same logical source.

    This helps identify registry entries that should be collapsed.

    Args:
        registry: The source registry (may be None)
        inventory: Current source inventory
        kube_context: Kubernetes context for backing pod queries

    Returns:
        List of (canonical_key, duplicate_key) pairs that should be collapsed
    """
    if registry is None or not registry.entries:
        return []

    # Build source map for backing identity lookup
    sources_list = list(inventory.sources.values())
    backing_cache = build_backing_identity_cache(sources_list, kube_context)

    # Find duplicate registry entries
    duplicates: list[tuple[str, str]] = []
    canonical_entries: dict[LogicalSourceKey, str] = {}

    for entry_key, entry in registry.entries.items():
        # Extract canonical identity from entry key
        parts = entry_key.split(":", 1)
        if len(parts) < 2:
            continue
        canonical_identity = parts[1]

        # Find matching source
        matching_source = None
        for source in sources_list:
            if source.canonical_identity == canonical_identity:
                matching_source = source
                break

        if matching_source and matching_source.namespace and matching_source.name:
            key = f"{matching_source.namespace}/{matching_source.name}"
            backing: BackingPodIdentity | None = backing_cache.get(key)
        else:
            backing = None

        log_key = LogicalSourceKey(
            cluster_context=parts[0] if parts else "unknown",
            namespace=canonical_identity.split("/")[0] if "/" in canonical_identity else "default",
            identity_kind=backing.kind if backing else "endpoint",
            identity_value=tuple(sorted(backing.uid_set)) if backing and backing.uid_set else (canonical_identity,),
        )

        if log_key in canonical_entries:
            duplicates.append((canonical_entries[log_key], entry_key))
        else:
            canonical_entries[log_key] = entry_key

    return duplicates


def collapse_duplicate_registry_entries(
    registry: AlertmanagerSourceRegistry,
    inventory: AlertmanagerSourceInventory,
    kube_context: str | None = None,
) -> tuple[AlertmanagerSourceRegistry, int]:
    """Collapse duplicate registry entries using backing identity and aliases.

    When the same Alertmanager is registered under multiple keys (e.g.,
    alertmanager-operated headless service vs chart service), this collapses
    them into a single canonical entry using the reconciliation priority.

    Matching supports:
    - Canonical source canonical_identity
    - Alias namespace/name
    - Backing pod identity when available
    - Normalized endpoint fallback only when backing identity unavailable

    Priority: manual > disabled > chart > CRD > headless/operated

    Note: Manual sources are not collapsed away. They win canonical when exact
    identity evidence matches. Discovered sources become aliases.

    Args:
        registry: The source registry with potential duplicates
        inventory: Current source inventory (may already be reconciled)
        kube_context: Kubernetes context for backing pod queries

    Returns:
        Tuple of (cleaned_registry, duplicate_count) where duplicate_count
        is the number of duplicate entries that were removed
    """
    if not registry.entries:
        return registry, 0

    # Build source list and backing identity cache
    sources_list = list(inventory.sources.values())
    backing_cache = build_backing_identity_cache(sources_list, kube_context)

    # Build alias map: alias_name -> (canonical_identity, backing_cache_key)
    # This allows matching registry entries that refer to alias identities
    alias_map: dict[tuple[str, str], str] = {}  # (namespace, name) -> canonical_identity
    for source in sources_list:
        # Map canonical source identity
        if source.namespace and source.name:
            key = (source.namespace, source.name)
            alias_map[key] = source.canonical_identity

        # Map all aliases
        for alias in source.aliases:
            if alias.alias_namespace and alias.alias_name:
                key = (alias.alias_namespace, alias.alias_name)
                alias_map[key] = source.canonical_identity

    # Group entries by logical source key, keeping the canonical one
    source_groups: dict[LogicalSourceKey, list[tuple[str, RegistryEntry, int]]] = {}

    for entry_key, entry in registry.entries.items():
        parts = entry_key.split(":", 1)
        if len(parts) < 2:
            continue
        cluster_part = parts[0]
        canonical_identity = parts[1]

        # Find matching source - check canonical identity first, then aliases
        matching_source = None
        for source in sources_list:
            if source.canonical_identity == canonical_identity:
                matching_source = source
                break

        # If no match on canonical identity, check if this is an alias
        if matching_source is None:
            identity_parts = canonical_identity.split("/")
            if len(identity_parts) == 2:
                alias_ns, alias_name = identity_parts
                alias_key = (alias_ns, alias_name)
                if alias_key in alias_map:
                    # This is an alias - find the canonical source
                    mapped_identity = alias_map[alias_key]
                    for source in sources_list:
                        if source.canonical_identity == mapped_identity:
                            matching_source = source
                            break

        # Get backing identity for matching source
        backing: BackingPodIdentity | None = None
        if matching_source and matching_source.namespace and matching_source.name:
            backing_key = f"{matching_source.namespace}/{matching_source.name}"
            backing = backing_cache.get(backing_key)

        # Determine priority for this entry
        # Higher priority = should be the canonical entry
        priority = _get_entry_priority(entry, matching_source)

        log_key = LogicalSourceKey(
            cluster_context=cluster_part,
            namespace=canonical_identity.split("/")[0] if "/" in canonical_identity else "default",
            identity_kind=backing.kind if backing else "endpoint",
            identity_value=tuple(sorted(backing.uid_set)) if backing and backing.uid_set else (canonical_identity,),
        )

        if log_key not in source_groups:
            source_groups[log_key] = []

        source_groups[log_key].append((entry_key, entry, priority))

    # Build cleaned registry, keeping the highest-priority entry per group
    cleaned_entries: dict[str, RegistryEntry] = {}
    duplicate_count = 0

    for log_key, entries in source_groups.items():
        if len(entries) == 1:
            # No duplicates, keep the single entry
            entry_key, entry, _ = entries[0]
            cleaned_entries[entry_key] = entry
        else:
            # Multiple entries for same logical source - keep highest priority
            entries_sorted = sorted(entries, key=lambda x: x[2], reverse=True)
            canonical_key, canonical_entry, _ = entries_sorted[0]
            cleaned_entries[canonical_key] = canonical_entry

            # Count duplicates that will be removed
            duplicate_count += len(entries) - 1

            # Log which entries were collapsed
            _logger.debug(
                "Collapsing %d duplicate registry entries for logical source %s: keeping %s",
                len(entries) - 1,
                log_key,
                canonical_key,
            )

    # Create new registry with cleaned entries
    from ..external_analysis.alertmanager_source_models import AlertmanagerSourceRegistry
    cleaned_registry = AlertmanagerSourceRegistry(entries=cleaned_entries)

    if duplicate_count > 0:
        _logger.info(
            "Registry migration: collapsed %d duplicate entries into %d canonical entries",
            duplicate_count,
            len(cleaned_entries),
        )

    return cleaned_registry, duplicate_count


def _get_entry_priority(
    entry: RegistryEntry,
    matching_source: AlertmanagerSource | None,
) -> int:
    """Determine priority for a registry entry.

    Priority scale (higher = more authoritative):
    - 40: manual desired state (operator-promoted, never collapsed away)
    - 35: disabled (explicitly excluded)
    - 25: chart-facing service (kube-prometheus-stack-alertmanager)
    - 20: Alertmanager CRD / Prometheus CRD config
    - 10: headless -operated service (lowest service type priority)
    - 0: generic/neutral (default, resolved by service-name classification)

    Note: Manual sources are not collapsed away. They win canonical when
    exact identity evidence matches. Discovered sources become aliases.

    Args:
        entry: The registry entry
        matching_source: The matching source from inventory (may be None)

    Returns:
        Priority value (higher = more authoritative)
    """
    from ..external_analysis.alertmanager_discovery_models import AlertmanagerSourceOrigin

    # Manual state has highest priority (operator-promoted, never collapsed away)
    if entry.desired_state.value == "manual":
        return 40

    # Disabled entries get high priority (explicit exclusion preserved)
    if entry.desired_state.value == "disabled":
        return 35

    # Get the service name for chart/headless classification
    service_name = entry.name or ""

    # Check for chart-facing service (preferred over -operated)
    if _is_chart_alertmanager_service(service_name):
        return 25

    # Check for headless -operated service (lowest priority among service types)
    if _is_headless_operated_service(service_name):
        return 10

    # Determine by origin
    if matching_source:
        origin = matching_source.origin
        if origin == AlertmanagerSourceOrigin.MANUAL:
            return 40  # Shouldn't happen in registry, but handle it
        elif origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD:
            return 20
        elif origin == AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG:
            return 20
        elif origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC:
            # Already handled above via service name check
            return 0

    # Check metadata fallback
    original_origin = getattr(entry, 'original_origin', None)
    if original_origin:
        origin_str = str(original_origin)
        if 'alertmanager-crd' in origin_str:
            return 20
        elif 'prometheus-crd-config' in origin_str:
            return 20

    # Default: generic/lowest priority
    return 0


__all__ = [
    "collapse_duplicate_registry_entries",
    "detect_duplicate_registry_entries",
]
