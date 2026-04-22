"""Run-config helpers for the health loop.

Extracts support helpers around HealthRunConfig.load() from loop.py into a focused module.
Preserves behavior exactly - no schema or artifact contract changes.

This module provides config-owned helpers for:
1. Output directory resolution
2. Collector version resolution

Keep in loop.py:
- HealthRunConfig class
- HealthRunConfig.load() method
- Comparison-policy helper family
- Assessment builder logic
- Orchestration and delegator families
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _resolve_output_dir(raw_output_dir: Any | None) -> Path:
    """Resolve output directory from raw config value, defaulting to 'runs'."""
    if raw_output_dir is None:
        return Path("runs")
    return Path(str(raw_output_dir))


def _resolve_collector_version(raw_version: Any | None) -> str:
    """Resolve collector version from raw config value, defaulting to 'dev'."""
    if raw_version is None:
        return "dev"
    return str(raw_version)


__all__ = [
    "_resolve_output_dir",
    "_resolve_collector_version",
]