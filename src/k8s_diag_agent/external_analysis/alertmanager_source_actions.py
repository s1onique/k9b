"""Operator overrides for Alertmanager source management.

## Conceptual Clarification

This module handles two distinct concepts that are sometimes conflated:

1. **Per-run override artifacts** (`{run_id}-alertmanager-source-overrides.json`)
   - Run-scoped mutable artifacts that apply effective state within a single run
   - Derived support artifacts for UI display and run-scoped state computation
   - NOT the authoritative cross-run source of truth
   - Overwritten each run with the latest per-run overrides

2. **Immutable action artifacts** (`alertmanager-source-actions/`)
   - Append-only audit trail written once per action (never overwritten)
   - Each action creates a new file with unique artifact_id
   - Provides cross-run audit capability beyond the current run
   - Survives beyond run-scoped overrides

## Source-of-Truth Boundary

The durable cross-run source of truth for operator intent is the **registry**
(`alertmanager-source-registry.json`), NOT the per-run override artifacts.

- **Registry**: Mutable cross-run store; records operator promote/disable decisions
  that persist across runs. This is the authoritative source for cross-run intent.
- **Per-run overrides**: Run-scoped mutable artifacts; derived from registry state
  for UI display within the current run.
- **Immutable action artifacts**: Append-only audit trail; provides evidence trail
  independent of current registry state.

## Design Rationale

- Manual sources are authoritative and never silently deleted
- Promotion preserves endpoint/namespace/name as pinned identity
- Disable is explicit and reversible (re-enable via discovery)
- Separate artifact keeps overrides auditable and composable
- Immutable action artifacts provide cross-run audit trail independent of registry
"""

from __future__ import annotations

import json
import re as _re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..datetime_utils import ensure_utc
from ..identity.artifact import new_artifact_id


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
                timestamp = ensure_utc(datetime.fromisoformat(timestamp_str))
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
    
    Per-run override artifacts are DERIVED support artifacts for UI display
    and run-scoped state computation. They are NOT the authoritative cross-run
    source of truth.
    
    The durable cross-run source of truth is the registry
    (`alertmanager-source-registry.json`), which records operator promote/disable
    decisions that persist across runs.
    
    Artifact lifecycle:
    - Written: Per-run, overwritten each run with latest overrides
    - Read by: UI for display of effective state in current run
    - Authority: Derived from registry; NOT the source of truth
    
    For immutable cross-run audit trail, see write_source_action_artifact().
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
                last_updated = ensure_utc(datetime.fromisoformat(last_updated_str))
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


def _sanitize_for_filename(value: str) -> str:
    """Sanitize a string for use in filenames.
    
    Replaces characters that are problematic in filenames with underscores.
    Preserves alphanumeric, hyphens, underscores, and dots.
    Colons and slashes are replaced because they're not safe across all filesystems
    (colons are problematic on macOS, slashes are path separators everywhere).
    """
    if not value:
        return "empty"
    # Replace characters that are problematic in filenames
    result = _re.sub(r'[<>:"/"|?*]', "_", value)
    # Collapse multiple underscores
    result = _re.sub(r'_+', "_", result)
    # Strip leading/trailing underscores
    result = result.strip("_")
    return result if result else "sanitized"


def _write_source_action_artifact_impl(
    directory: Path,
    run_id: str,
    source_id: str,
    action: SourceAction,
    cluster_label: str | None,
    cluster_context: str | None,
    canonical_identity: str,
    endpoint: str | None = None,
    namespace: str | None = None,
    name: str | None = None,
    original_origin: str | None = None,
    original_state: str | None = None,
    resulting_state: str | None = None,
    reason: str | None = None,
    previous_desired_state: str | None = None,
    artifact_id_fn: Callable[[], str] | None = None,
    timestamp: datetime | None = None,
) -> Path:
    """Internal implementation for writing source action artifacts.

    This helper accepts injectable dependencies (artifact_id_fn, timestamp) for
    testing and reproducibility. Production code should use write_source_action_artifact().
    
    Args:
        artifact_id_fn: Optional callable to generate artifact IDs; defaults to new_artifact_id()
        timestamp: Optional datetime to use for created_at/timestamp; defaults to now()
        
    Returns:
        Path to the written artifact
    """
    # Create the action artifacts directory
    action_dir = directory / "alertmanager-source-actions"
    action_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate artifact ID using repo standard (UUIDv7)
    if artifact_id_fn is None:
        artifact_id_fn = new_artifact_id
    artifact_id = artifact_id_fn()
    
    # Sanitize source_id for filename safety
    sanitized_source_id = _sanitize_for_filename(source_id)
    
    # Build filename: {run_id}-{sanitized_source_id}-{action}-{artifact_id}.json
    filename = f"{run_id}-{sanitized_source_id}-{action.value}-{artifact_id}.json"
    path = action_dir / filename
    
    # Reject overwrite if path already exists (immutability guarantee)
    if path.exists():
        raise FileExistsError(f"Action artifact path already exists: {path}")
    
    # Generate timestamp once and reuse for both fields
    if timestamp is None:
        timestamp = datetime.now(UTC)
    ts_str = timestamp.isoformat()
    
    # Build the artifact payload
    artifact = {
        # Artifact identity
        "artifact_id": artifact_id,
        "run_id": run_id,
        "action": action.value,
        
        # Timestamps - use the same value for both (single timestamp for audit)
        "created_at": ts_str,
        "timestamp": ts_str,
        
        # Source identity
        "source_id": source_id,
        "canonical_identity": canonical_identity,
        "cluster_label": cluster_label,
        "cluster_context": cluster_context,
        "registry_key": f"{(cluster_label or cluster_context or 'unknown')}:{canonical_identity}",
        
        # Source details at time of action
        "endpoint": endpoint,
        "namespace": namespace,
        "name": name,
        
        # State tracking for audit trail
        "original_origin": original_origin,
        "original_state": original_state,
        "resulting_state": resulting_state,
        "previous_desired_state": previous_desired_state,
        
        # Audit metadata
        "reason": reason,
        "schema_version": "1",
    }
    
    # Write the artifact
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    
    return path


def write_source_action_artifact(
    directory: Path,
    run_id: str,
    source_id: str,
    action: SourceAction,
    cluster_label: str | None,
    cluster_context: str | None,
    canonical_identity: str,
    endpoint: str | None = None,
    namespace: str | None = None,
    name: str | None = None,
    original_origin: str | None = None,
    original_state: str | None = None,
    resulting_state: str | None = None,
    reason: str | None = None,
    previous_desired_state: str | None = None,
) -> Path:
    """Write an immutable action artifact for Alertmanager source actions.
    
    This creates an append-only audit trail for operator actions on Alertmanager
    sources. Each action produces a new artifact with a unique filename that
    cannot be overwritten.
    
    Artifact path pattern:
    runs/health/alertmanager-source-actions/{run_id}-{sanitized_source_id}-{action}-{artifact_id}.json
    
    Uses repo-standard UUIDv7 artifact IDs for immutable identity consistency.
    
    Args:
        directory: Directory to write the artifact (typically health root)
        run_id: Run identifier for this action
        source_id: Source identifier from the action request
        action: The action taken (promote/disable)
        cluster_label: Operator-facing cluster label (preferred for stability)
        cluster_context: Kubernetes context (may change)
        canonical_identity: Canonical source identity (namespace/name)
        endpoint: Source endpoint at time of action
        namespace: Source namespace at time of action
        name: Source name at time of action
        original_origin: Source origin before action
        original_state: Source state before action
        resulting_state: Resulting desired state after action
        reason: Operator-provided reason for the action
        previous_desired_state: Previous desired state if registry entry existed
        
    Returns:
        Path to the written artifact
        
    Raises:
        FileExistsError: If the artifact path already exists
    """
    return _write_source_action_artifact_impl(
        directory=directory,
        run_id=run_id,
        source_id=source_id,
        action=action,
        cluster_label=cluster_label,
        cluster_context=cluster_context,
        canonical_identity=canonical_identity,
        endpoint=endpoint,
        namespace=namespace,
        name=name,
        original_origin=original_origin,
        original_state=original_state,
        resulting_state=resulting_state,
        reason=reason,
        previous_desired_state=previous_desired_state,
    )


def source_action_artifact_path(
    directory: Path,
    run_id: str,
    source_id: str,
    action: SourceAction,
    artifact_id: str,
) -> Path:
    """Compute the expected path for a source action artifact.
    
    This is the inverse of write_source_action_artifact's path generation.
    Used for lookup and validation.
    """
    sanitized_source_id = _sanitize_for_filename(source_id)
    filename = f"{run_id}-{sanitized_source_id}-{action.value}-{artifact_id}.json"
    return directory / "alertmanager-source-actions" / filename
