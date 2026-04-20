"""Durable registry for Alertmanager source operator actions.

This module provides persistent cross-run state for operator promote/disable actions
on Alertmanager sources. Unlike run-scoped override artifacts, this registry persists
across runs so that operator intent is durable.

Design principles:
- Registry artifact lives under runs/health/ (not run-scoped)
- Entries are keyed by stable identity: cluster_context + canonical_identity
- Supports desired states: "manual" (promoted), "disabled"
- Preserves audit metadata: reason, operator, updated_at, source_run_id
- Canonical identity uses namespace/name format (not raw source_id)
- Prometheus Operator alias handling is preserved (alertmanager-operated -> CRD name)

Schema version: 1
Artifact path: runs/health/alertmanager-source-registry.json
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .alertmanager_discovery import AlertmanagerSource, AlertmanagerSourceMode

# Module logger
_logger = logging.getLogger(__name__)

# Current schema version
_SCHEMA_VERSION = "1"

# Default registry artifact path (relative to runs/health/)
_REGISTRY_FILENAME = "alertmanager-source-registry.json"


class RegistryDesiredState(StrEnum):
    """Desired state for a source in the durable registry."""
    MANUAL = "manual"  # Promoted to manual - should appear as manual in future runs
    DISABLED = "disabled"  # Disabled - should not be tracked in future runs


@dataclass(frozen=True)
class RegistryEntry:
    """A durable registry entry for an Alertmanager source.
    
    This records an operator's explicit action on a source that should persist
    across runs.
    """
    # Stable identity key components
    cluster_context: str  # Kubernetes context (e.g., "minikube", "prod-cluster")
    canonical_identity: str  # Canonical identity (namespace/name format)
    
    # Desired state
    desired_state: RegistryDesiredState
    
    # Audit metadata
    reason: str | None = None  # Operator-provided reason for the action
    operator: str | None = None  # Operator identifier (for future use)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_run_id: str | None = None  # Run where the action was first recorded
    
    # Source metadata at time of action (for debugging/auditing)
    endpoint: str | None = None
    namespace: str | None = None
    name: str | None = None
    original_origin: str | None = None
    original_state: str | None = None
    
    @property
    def registry_key(self) -> str:
        """Generate the registry key for this entry.
        
        Format: cluster_context:canonical_identity
        Example: "minikube:monitoring/alertmanager-main"
        """
        return f"{self.cluster_context}:{self.canonical_identity}"
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON persistence."""
        return {
            "cluster_context": self.cluster_context,
            "canonical_identity": self.canonical_identity,
            "desired_state": self.desired_state.value,
            "reason": self.reason,
            "operator": self.operator,
            "updated_at": self.updated_at.isoformat(),
            "source_run_id": self.source_run_id,
            "endpoint": self.endpoint,
            "namespace": self.namespace,
            "name": self.name,
            "original_origin": self.original_origin,
            "original_state": self.original_state,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryEntry:
        """Deserialize from dict."""
        updated_at_str = data.get("updated_at")
        if updated_at_str:
            if updated_at_str.endswith("Z"):
                updated_at_str = f"{updated_at_str[:-1]}+00:00"
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
            except ValueError:
                updated_at = datetime.now(UTC)
        else:
            updated_at = datetime.now(UTC)
        
        return cls(
            cluster_context=str(data["cluster_context"]),
            canonical_identity=str(data["canonical_identity"]),
            desired_state=RegistryDesiredState(data["desired_state"]),
            reason=data.get("reason"),
            operator=data.get("operator"),
            updated_at=updated_at,
            source_run_id=data.get("source_run_id"),
            endpoint=data.get("endpoint"),
            namespace=data.get("namespace"),
            name=data.get("name"),
            original_origin=data.get("original_origin"),
            original_state=data.get("original_state"),
        )


@dataclass
class AlertmanagerSourceRegistry:
    """Collection of durable registry entries for Alertmanager sources.
    
    This registry persists operator actions across runs. It is keyed by
    cluster_context + canonical_identity to ensure stable matching.
    """
    entries: dict[str, RegistryEntry] = field(default_factory=dict)
    schema_version: str = _SCHEMA_VERSION
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    def add_entry(self, entry: RegistryEntry) -> None:
        """Add or update a registry entry.
        
        If an entry already exists for this registry key, it is replaced.
        """
        self.entries[entry.registry_key] = entry
        self.last_updated = datetime.now(UTC)
        _logger.debug(
            "Registry entry added/updated: key=%s desired_state=%s",
            entry.registry_key,
            entry.desired_state.value,
        )
    
    def get_entry(self, registry_key: str) -> RegistryEntry | None:
        """Get registry entry by registry key."""
        return self.entries.get(registry_key)
    
    def remove_entry(self, registry_key: str) -> bool:
        """Remove a registry entry. Returns True if it existed."""
        if registry_key in self.entries:
            del self.entries[registry_key]
            self.last_updated = datetime.now(UTC)
            return True
        return False
    
    def get_desired_state(self, cluster_context: str, canonical_identity: str) -> RegistryDesiredState | None:
        """Get the desired state for a source by its stable identity.
        
        Args:
            cluster_context: Kubernetes context
            canonical_identity: Canonical identity in namespace/name format
            
        Returns:
            RegistryDesiredState if found, None otherwise
        """
        registry_key = f"{cluster_context}:{canonical_identity}"
        entry = self.entries.get(registry_key)
        return entry.desired_state if entry else None
    
    def get_disabled_sources(self) -> tuple[RegistryEntry, ...]:
        """Get all registry entries for disabled sources."""
        return tuple(
            entry for entry in self.entries.values()
            if entry.desired_state == RegistryDesiredState.DISABLED
        )
    
    def get_manual_sources(self) -> tuple[RegistryEntry, ...]:
        """Get all registry entries for manual (promoted) sources."""
        return tuple(
            entry for entry in self.entries.values()
            if entry.desired_state == RegistryDesiredState.MANUAL
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON persistence."""
        return {
            "schema_version": self.schema_version,
            "entries": {key: entry.to_dict() for key, entry in self.entries.items()},
            "last_updated": self.last_updated.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourceRegistry:
        """Deserialize from dict."""
        schema_version = data.get("schema_version", _SCHEMA_VERSION)
        
        entries_raw = data.get("entries", {})
        entries: dict[str, RegistryEntry] = {}
        for key, entry_data in entries_raw.items():
            try:
                entries[key] = RegistryEntry.from_dict(entry_data)
            except (KeyError, ValueError) as exc:
                _logger.warning(
                    "Failed to parse registry entry for key %s: %s",
                    key,
                    exc,
                )
                continue
        
        last_updated_str = data.get("last_updated")
        if last_updated_str:
            if last_updated_str.endswith("Z"):
                last_updated_str = f"{last_updated_str[:-1]}+00:00"
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
            except ValueError:
                last_updated = datetime.now(UTC)
        else:
            last_updated = datetime.now(UTC)
        
        return cls(
            entries=entries,
            schema_version=schema_version,
            last_updated=last_updated,
        )


def write_source_registry(
    registry: AlertmanagerSourceRegistry,
    health_root: Path,
) -> Path:
    """Write Alertmanager source registry to the health root directory.
    
    The registry is stored as a durable artifact under runs/health/
    (not run-scoped like override artifacts).
    
    Args:
        registry: The registry to persist
        health_root: Path to the runs/health/ directory
        
    Returns:
        Path to the written registry file
    """
    health_root.mkdir(parents=True, exist_ok=True)
    path = health_root / _REGISTRY_FILENAME
    path.write_text(json.dumps(registry.to_dict(), indent=2), encoding="utf-8")
    _logger.debug("Alertmanager source registry written to %s", path)
    return path


def read_source_registry(health_root: Path) -> AlertmanagerSourceRegistry | None:
    """Read Alertmanager source registry from the health root directory.
    
    Args:
        health_root: Path to the runs/health/ directory
        
    Returns:
        The registry if found and valid, None otherwise
    """
    path = health_root / _REGISTRY_FILENAME
    if not path.exists():
        return None
    
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AlertmanagerSourceRegistry.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        _logger.warning(
            "Failed to parse Alertmanager source registry at %s: %s",
            path,
            exc,
        )
        return None


def source_registry_exists(health_root: Path) -> bool:
    """Check if Alertmanager source registry exists."""
    return (health_root / _REGISTRY_FILENAME).exists()


def build_registry_key(cluster_context: str | None, source: AlertmanagerSource) -> str:
    """Build a registry key for an Alertmanager source.
    
    Format: cluster_context:canonical_identity
    
    This uses the source's canonical_identity (namespace/name) rather than
    the raw source_id to ensure stable matching across discovery strategies.
    
    Args:
        cluster_context: Kubernetes context (uses "unknown" if None)
        source: The Alertmanager source
        
    Returns:
        Registry key string
    """
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
    return entry.desired_state if entry else None


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
    
    from .alertmanager_discovery import AlertmanagerSourceState
    
    if desired_state == RegistryDesiredState.MANUAL:
        # Promote to manual - preserve the original discovery origin
        # and set manual_source_mode to indicate this was promoted from discovery
        from dataclasses import replace as _replace
        _logger.debug(
            "Applying registry state 'manual' to source %s (promoted from %s)",
            source.canonical_identity,
            source.origin.value,
        )
        # Get the registry entry's cluster_context to use for the source
        # This ensures the serializer can match the source to the registry entry
        # Use the cluster_context that was used to find this match
        entry_cluster_context = cluster_context or "unknown"
        return _replace(
            source,
            # Preserve original discovery origin (e.g., alertmanager-crd, service-heuristic)
            # Do NOT change origin to MANUAL - that is only for operator-configured sources
            state=AlertmanagerSourceState.MANUAL,
            # Set manual_source_mode to indicate this was promoted from auto-discovery
            manual_source_mode=AlertmanagerSourceMode.OPERATOR_PROMOTED,
            # Set cluster_context from registry entry so serializer can match it
            # This is critical for the UI to correctly identify promoted sources
            cluster_context=entry_cluster_context,
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
    inventory: "AlertmanagerSourceInventory",  # type: ignore[name-defined]  # noqa: UP037,F821
    registry: AlertmanagerSourceRegistry | None,
    cluster_context: str | None,
) -> "AlertmanagerSourceInventory":  # type: ignore[name-defined]  # noqa: UP037,F821
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
