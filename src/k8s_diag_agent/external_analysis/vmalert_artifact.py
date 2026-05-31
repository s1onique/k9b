"""Run artifact persistence for vmalert source inventory.

This module provides artifact persistence for vmalert source discovery results,
parallel to the alertmanager_sources module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..identity.artifact import write_append_only_json_artifact

if TYPE_CHECKING:
    from .vmalert_discovery import VmalertSourceInventory


def write_vmalert_sources(directory: Path, inventory: VmalertSourceInventory, run_id: str) -> Path:
    """Write vmalert sources inventory to run artifact directory.

    vmalert sources inventory artifacts are immutable: once written, they must not be overwritten.
    This function rejects writes to an existing path to enforce the immutability contract.
    """
    path = directory / f"{run_id}-vmalert-sources.json"

    write_append_only_json_artifact(path, inventory.to_dict(), context=f"run_id={run_id}")
    return path


def read_vmalert_sources(path: Path) -> VmalertSourceInventory | None:
    """Read vmalert sources inventory from artifact file."""
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        from .vmalert_discovery import VmalertSourceInventory
        return VmalertSourceInventory.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def vmalert_sources_exist(root: Path, run_id: str) -> bool:
    """Check if vmalert sources artifact exists for a run."""
    path = root / f"{run_id}-vmalert-sources.json"
    return path.exists()
