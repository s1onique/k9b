"""Shared UI helper utilities.

This module provides narrowly-scoped helpers that are used across multiple
UI-related modules, keeping shared concerns in one place.

Separated from ui.py to provide a crisp canonical home for:
- Path utility functions (relative_path)
"""

from __future__ import annotations

from pathlib import Path


def _relative_path(base: Path, target: object | None) -> str | None:
    """Compute relative path from base to target for UI artifact paths."""
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)
