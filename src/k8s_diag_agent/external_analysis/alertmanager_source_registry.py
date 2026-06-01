"""Alertmanager source registry key-building helpers.

This module provides helper functions for building registry keys for
Alertmanager sources. It re-exports the models and persistence functions
from alertmanager_source_models for backward compatibility.

Registry key format: cluster_identifier:canonical_identity

Key design principles:
- cluster_label is preferred over cluster_context for stability
- Canonical identity uses namespace/name format (not raw source_id)
- Legacy key format is supported for backward compatibility
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Re-export models for backward compatibility
from .alertmanager_source_models import (  # noqa: F401 - re-exported for backward compatibility
    AlertmanagerSourceRegistry,
    RegistryDesiredState,
    RegistryEntry,
    read_source_registry,
    source_registry_exists,
    write_source_registry,
)

if TYPE_CHECKING:
    from .alertmanager_discovery import (
        AlertmanagerSource,
        AlertmanagerSourceInventory,
    )

# Module logger
_logger = logging.getLogger(__name__)


def build_registry_key(cluster_context: str | None, source: AlertmanagerSource) -> str:
    """Build a registry key for an Alertmanager source.
    
    Format: cluster_context:canonical_identity
    
    This uses the source's canonical_identity (namespace/name) rather than
    the raw source_id to ensure stable matching across discovery strategies.
    
    Keying priority:
    1. source.cluster_label (most stable - operator-controlled)
    2. cluster_context parameter (if source has no cluster_label)
    3. "unknown" (fallback when neither is available)
    
    NOTE: For new code, prefer using source.operator_intent_key directly,
    which uses cluster_label for stability. This function is kept for backward
    compatibility with code that explicitly passes cluster_context.
    
    Args:
        cluster_context: Kubernetes context (may be used if source has no cluster_label)
        source: The Alertmanager source
        
    Returns:
        Registry key string
    """
    # Prefer operator_intent_key (uses cluster_label when available)
    # Falls back to cluster_context when cluster_label is not set
    # Falls back to "unknown" when neither is available
    if source.cluster_label:
        return source.operator_intent_key
    
    # Source has no cluster_label, use the passed cluster_context
    # This maintains backward compatibility for callers that pass cluster_context
    context = cluster_context or "unknown"
    return f"{context}:{source.canonical_identity}"


def build_canonical_registry_key(
    cluster_context: str | None,
    cluster_label: str | None,
    canonical_identity: str,
) -> str:
    """Build a canonical registry key for cross-run persistence.
    
    Uses the most STABLE available cluster identifier (prefer operator-facing label):
    1. cluster_label if available (operator-facing, stable across runs)
    2. cluster_context if available (Kubernetes context, may change with kubeconfig)
    3. "unknown" as last resort
    
    This ensures registry entries persist across runs even when
    cluster_context differs, is None, or changes between runs.
    
    CRITICAL: For durable operator persistence, cluster_label is preferred because
    it is operator-controlled and stable, while cluster_context can change with
    kubeconfig edits, aliases, or context renames.
    
    Args:
        cluster_context: Kubernetes context (may be None or change between runs)
        cluster_label: Operator-facing cluster label (stable, preferred)
        canonical_identity: Source canonical identity (namespace/name)
        
    Returns:
        Canonical registry key string
    """
    # Prefer cluster_label (stable, operator-facing) over cluster_context
    # because cluster_context can change with kubeconfig edits/renames
    if cluster_label:
        cluster_key = cluster_label
    elif cluster_context:
        cluster_key = cluster_context
    else:
        cluster_key = "unknown"
    
    return f"{cluster_key}:{canonical_identity}"


def lookup_registry_state(
    registry: AlertmanagerSourceRegistry | None,
    cluster_context: str | None,
    source: AlertmanagerSource,
) -> RegistryDesiredState | None:
    """Look up the desired state for a source in the registry.
    
    Uses the canonical key (preferring cluster_label) to ensure the lookup
    matches the key used when writing registry entries. This is critical for
    cross-run persistence when cluster_context may differ between runs.
    
    Backward compatibility: If canonical key is not found, falls back to
    legacy context-keyed lookup for registry entries written before the
    label-first change.
    
    Args:
        registry: The source registry (or None if not loaded)
        cluster_context: Kubernetes context (may be None or change between runs)
        source: The Alertmanager source to look up (provides cluster_label for canonical key)
        
    Returns:
        Desired state if found in registry, None otherwise
    """
    if registry is None:
        return None
    
    # Use canonical key (preferring cluster_label) to match the write path
    # This ensures cross-run persistence even when cluster_context changes
    canonical_key = build_canonical_registry_key(
        cluster_context=cluster_context,
        cluster_label=source.cluster_label,
        canonical_identity=source.canonical_identity,
    )
    
    entry = registry.get_entry(canonical_key)
    if entry:
        return entry.desired_state
    
    # Backward compatibility: try legacy context-keyed lookup
    # This handles registry entries written before the label-first change
    # where entries were keyed by cluster_context instead of cluster_label
    legacy_key = f"{cluster_context or 'unknown'}:{source.canonical_identity}"
    if legacy_key != canonical_key:
        _logger.debug(
            "Canonical key %s not found, trying legacy key %s for source %s",
            canonical_key,
            legacy_key,
            source.canonical_identity,
        )
        legacy_entry = registry.get_entry(legacy_key)
        if legacy_entry:
            _logger.info(
                "Found registry entry via legacy key %s (canonical was %s). "
                "Consider re-promoting the source to migrate to label-first keying.",
                legacy_key,
                canonical_key,
            )
            return legacy_entry.desired_state
    
    return None


def apply_registry_to_source(
    source: AlertmanagerSource,
    registry: AlertmanagerSourceRegistry | None,
    cluster_context: str | None,
) -> AlertmanagerSource | None:
    """Apply registry state to a discovered source.
    
    This applies the desired state from the durable registry to a source
    that was discovered in the current run. If the registry has an entry
    for this source, its state is updated accordingly:
    - "manual": Sets state to MANUAL, origin to MANUAL
    - "disabled": Returns None to indicate source should be filtered out
    
    Args:
        source: The discovered source
        registry: The source registry (or None)
        cluster_context: Kubernetes context for this run
        
    Returns:
        Updated source with registry state applied, or None if disabled
    """
    if registry is None:
        return source
    
    desired_state = lookup_registry_state(registry, cluster_context, source)
    if desired_state is None:
        return source
    
    from .alertmanager_discovery import AlertmanagerSourceMode, AlertmanagerSourceState
    
    if desired_state == RegistryDesiredState.MANUAL:
        # Promote to manual - preserve the original discovery origin
        # and set manual_source_mode to indicate this was promoted from discovery
        from dataclasses import replace as _replace
        _logger.debug(
            "Applying registry state 'manual' to source %s (promoted from %s)",
            source.canonical_identity,
            source.origin.value,
        )
        # CRITICAL: Do NOT overwrite cluster_context with registry identity!
        # The source.cluster_context is the REAL kube execution context (e.g., "admin@rees46-k8s")
        # which is required for kubectl port-forward and snapshot collection.
        # The registry key identity (cluster_label-based) is only for cross-run persistence,
        # not for runtime execution. Use build_canonical_registry_key() for registry matching,
        # but preserve source.cluster_context as-is for execution.
        return _replace(
            source,
            # Preserve original discovery origin (e.g., alertmanager-crd, service-heuristic)
            # Do NOT change origin to MANUAL - that is only for operator-configured sources
            state=AlertmanagerSourceState.MANUAL,
            # Set manual_source_mode to indicate this was promoted from auto-discovery
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
            # Do NOT set cluster_context here - preserve the original discovered context
            # for runtime execution (kubectl, port-forward, etc.)
        )
    elif desired_state == RegistryDesiredState.DISABLED:
        # Return None to indicate this source should be filtered from inventory
        # Disabled sources should not appear in future discovery cycles
        _logger.debug(
            "Filtering out disabled source %s from inventory",
            source.canonical_identity,
        )
        return None
    
    return source


def apply_registry_to_inventory(
    inventory: AlertmanagerSourceInventory,
    registry: AlertmanagerSourceRegistry | None,
    cluster_context: str | None,
) -> AlertmanagerSourceInventory:
    """Apply registry state to all sources in an inventory.
    
    This filters out disabled sources (those that returned None from
    apply_registry_to_source) to ensure disabled sources don't appear
    in future discovery cycles.
    
    Args:
        inventory: The source inventory
        registry: The source registry (or None)
        cluster_context: Kubernetes context for this run
        
    Returns:
        Updated inventory with registry state applied to all sources,
        and disabled sources filtered out
    """
    if registry is None:
        return inventory
    
    updated_sources: dict[str, AlertmanagerSource] = {}
    
    for key, source in inventory.sources.items():
        updated_source = apply_registry_to_source(
            source, registry, cluster_context
        )
        # Only include sources that are not filtered out (not None)
        if updated_source is not None:
            updated_sources[key] = updated_source
    
    # Import here to avoid circular dependency with alertmanager_discovery
    from .alertmanager_discovery import AlertmanagerSourceInventory as _Inventory
    return _Inventory(
        sources=updated_sources,
        discovered_at=inventory.discovered_at,
        cluster_context=inventory.cluster_context,
    )
