"""Run artifact persistence for Alertmanager snapshot and compact outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .alertmanager_snapshot import AlertmanagerCompact, AlertmanagerSnapshot

if TYPE_CHECKING:
    from .alertmanager_discovery import AlertmanagerSourceInventory


def write_alertmanager_snapshot(directory: Path, snapshot: AlertmanagerSnapshot, run_id: str) -> Path:
    """Write Alertmanager snapshot to run artifact directory.
    
    Returns the path to the written file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}-alertmanager-snapshot.json"
    path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
    return path


def write_alertmanager_compact(directory: Path, compact: AlertmanagerCompact, run_id: str) -> Path:
    """Write Alertmanager compact summarization to run artifact directory.
    
    Returns the path to the written file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}-alertmanager-compact.json"
    path.write_text(json.dumps(compact.to_dict(), indent=2), encoding="utf-8")
    return path


def write_alertmanager_artifacts(
    root: Path,
    run_id: str,
    snapshot: AlertmanagerSnapshot,
    compact: AlertmanagerCompact,
) -> tuple[Path, Path]:
    """Write both Alertmanager snapshot and compact artifacts.
    
    Returns tuple of (snapshot_path, compact_path).
    """
    snapshot_path = write_alertmanager_snapshot(root, snapshot, run_id)
    compact_path = write_alertmanager_compact(root, compact, run_id)
    return snapshot_path, compact_path


def read_alertmanager_snapshot(path: Path) -> AlertmanagerSnapshot | None:
    """Read Alertmanager snapshot from artifact file.
    
    Returns None if file does not exist or cannot be parsed.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AlertmanagerSnapshot.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def read_alertmanager_compact(path: Path) -> AlertmanagerCompact | None:
    """Read Alertmanager compact from artifact file.
    
    Returns None if file does not exist or cannot be parsed.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AlertmanagerCompact(
            status=str(raw.get("status", "invalid_response")),
            alert_count=int(raw.get("alert_count", 0)),
            severity_counts=tuple(
                (str(k), int(v))
                for k, v in (raw.get("severity_counts", {}).items())
            ),
            state_counts=tuple(
                (str(k), int(v))
                for k, v in (raw.get("state_counts", {}).items())
            ),
            top_alert_names=tuple(str(n) for n in (raw.get("top_alert_names", []))),
            affected_namespaces=tuple(str(n) for n in (raw.get("affected_namespaces", []))),
            affected_clusters=tuple(str(n) for n in (raw.get("affected_clusters", []))),
            affected_services=tuple(str(n) for n in (raw.get("affected_services", []))),
            truncated=bool(raw.get("truncated", False)),
            captured_at=str(raw.get("captured_at", "")),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def alertmanager_artifacts_exist(root: Path, run_id: str) -> tuple[bool, bool]:
    """Check if Alertmanager artifacts exist for a run.
    
    Returns tuple of (snapshot_exists, compact_exists).
    """
    snapshot_path = root / f"{run_id}-alertmanager-snapshot.json"
    compact_path = root / f"{run_id}-alertmanager-compact.json"
    return snapshot_path.exists(), compact_path.exists()


def write_alertmanager_sources(directory: Path, inventory: AlertmanagerSourceInventory, run_id: str) -> Path:
    """Write Alertmanager sources inventory to run artifact directory.
    
    Returns the path to the written file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}-alertmanager-sources.json"
    path.write_text(json.dumps(inventory.to_dict(), indent=2), encoding="utf-8")
    return path


def read_alertmanager_sources(path: Path) -> AlertmanagerSourceInventory | None:
    """Read Alertmanager sources inventory from artifact file.
    
    Returns None if file does not exist or cannot be parsed.
    """
    from .alertmanager_discovery import AlertmanagerSourceInventory as InventoryClass
    
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return InventoryClass.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def alertmanager_sources_exist(root: Path, run_id: str) -> bool:
    """Check if Alertmanager sources artifact exists for a run."""
    return (root / f"{run_id}-alertmanager-sources.json").exists()