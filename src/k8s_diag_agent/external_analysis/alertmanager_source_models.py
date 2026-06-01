"""Alertmanager source registry models and persistence.

This module provides the data models and persistence functions for the
Alertmanager source durable registry. It defines the registry schema,
entry types, and I/O operations.

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

from ..datetime_utils import ensure_utc

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
                updated_at = ensure_utc(datetime.fromisoformat(updated_at_str))
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
                last_updated = ensure_utc(datetime.fromisoformat(last_updated_str))
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
