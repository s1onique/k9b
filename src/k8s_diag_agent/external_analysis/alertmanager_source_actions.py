"""Operator overrides for Alertmanager source management.

This module handles explicit operator actions on Alertmanager sources:
- promote: Convert a discovered/auto-tracked source to manual
- disable: Remove auto-tracking from a non-manual source

Overrides are persisted as a separate artifact to preserve discovery data
and remain composable with future reconciliation logic.

Design rationale:
- Manual sources are authoritative and never silently deleted
- Promotion preserves endpoint/namespace/name as pinned identity
- Disable is explicit and reversible (re-enable via discovery)
- Separate artifact keeps overrides auditable and composable
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class SourceAction(StrEnum):
    """Types of operator actions on Alertmanager sources."""
    PROMOTE = "promote"  # Promote to manual
    DISABLE = "disable"  # Disable auto-tracking


@dataclass(frozen=True)
class SourceOverride:
    """A single operator action on an Alertmanager source.
    
    This records an explicit operator decision that modifies how
    the source is treated in the inventory view.
    """
    source_id: str
    action: SourceAction
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    # The source identity at time of action (for auditing)
    endpoint: str | None = None
    namespace: str | None = None
    name: str | None = None
    # Original state before action (for rollback/debugging)
    original_origin: str | None = None
    original_state: str | None = None
    # Optional reason for the action (for audit trail)
    reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        result = {
            "source_id": self.source_id,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "endpoint": self.endpoint,
            "namespace": self.namespace,
            "name": self.name,
            "original_origin": self.original_origin,
            "original_state": self.original_state,
        }
        if self.reason is not None:
            result["reason"] = self.reason
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceOverride:
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            if timestamp_str.endswith("Z"):
                timestamp_str = f"{timestamp_str[:-1]}+00:00"
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                timestamp = datetime.now(UTC)
        else:
            timestamp = datetime.now(UTC)
        
        return cls(
            source_id=str(data["source_id"]),
            action=SourceAction(data["action"]),
            timestamp=timestamp,
            endpoint=data.get("endpoint"),
            namespace=data.get("namespace"),
            name=data.get("name"),
            original_origin=data.get("original_origin"),
            original_state=data.get("original_state"),
            reason=data.get("reason"),
        )


@dataclass
class AlertmanagerSourceOverrides:
    """Collection of operator overrides for Alertmanager sources.
    
    This artifact is separate from the discovery inventory to preserve
    discovery data and keep overrides auditable.
    """
    overrides: dict[str, SourceOverride] = field(default_factory=dict)
    cluster_context: str | None = None
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    def add_override(self, override: SourceOverride) -> None:
        """Add an override, keyed by source_id.
        
        If an override already exists for the source, it is replaced.
        """
        self.overrides[override.source_id] = override
        self.last_updated = datetime.now(UTC)
    
    def get_override(self, source_id: str) -> SourceOverride | None:
        """Get override for a specific source."""
        return self.overrides.get(source_id)
    
    def remove_override(self, source_id: str) -> bool:
        """Remove override for a source. Returns True if it existed."""
        if source_id in self.overrides:
            del self.overrides[source_id]
            self.last_updated = datetime.now(UTC)
            return True
        return False
    
    def get_disabled_sources(self) -> tuple[str, ...]:
        """Get list of disabled source IDs."""
        return tuple(
            source_id for source_id, override in self.overrides.items()
            if override.action == SourceAction.DISABLE
        )
    
    def get_promoted_sources(self) -> tuple[str, ...]:
        """Get list of promoted (manual) source IDs."""
        return tuple(
            source_id for source_id, override in self.overrides.items()
            if override.action == SourceAction.PROMOTE
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "overrides": [o.to_dict() for o in self.overrides.values()],
            "cluster_context": self.cluster_context,
            "last_updated": self.last_updated.isoformat(),
            "version": "v1",
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourceOverrides:
        overrides_list = data.get("overrides", [])
        overrides = {
            o["source_id"]: SourceOverride.from_dict(o)
            for o in overrides_list
            if "source_id" in o and "action" in o
        }
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
            overrides=overrides,
            cluster_context=data.get("cluster_context"),
            last_updated=last_updated,
        )


def write_source_overrides(
    directory: Path,
    overrides: AlertmanagerSourceOverrides,
    run_id: str,
) -> Path:
    """Write Alertmanager source overrides to run artifact directory.
    
    Returns the path to the written file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}-alertmanager-source-overrides.json"
    path.write_text(json.dumps(overrides.to_dict(), indent=2), encoding="utf-8")
    return path


def read_source_overrides(path: Path) -> AlertmanagerSourceOverrides | None:
    """Read Alertmanager source overrides from artifact file.
    
    Returns None if file does not exist or cannot be parsed.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AlertmanagerSourceOverrides.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def source_overrides_exist(root: Path, run_id: str) -> bool:
    """Check if Alertmanager source overrides artifact exists for a run."""
    return (root / f"{run_id}-alertmanager-source-overrides.json").exists()


def merge_source_overrides(
    overrides: AlertmanagerSourceOverrides,
) -> dict[str, str]:
    """Compute effective state for sources based on overrides.
    
    Returns a dict mapping source_id -> effective_state.
    - DISABLE override -> "disabled"
    - PROMOTE override -> "manual"
    - No override -> source not in dict (use original state)
    """
    effective_states: dict[str, str] = {}
    
    for source_id, override in overrides.overrides.items():
        if override.action == SourceAction.DISABLE:
            effective_states[source_id] = "disabled"
        elif override.action == SourceAction.PROMOTE:
            effective_states[source_id] = "manual"
    
    return effective_states
