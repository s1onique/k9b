#!/usr/bin/env python3
"""Helper functions for CNPG Live Lab bootstrap script.

This module contains utility functions used across the bootstrap
and diagnosis workflow including logging, JSON handling, and Kubernetes
event analysis.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# =============================================================================
# Logging functions
# =============================================================================

def log(msg: str) -> None:
    """Log info message."""
    print(f"[bootstrap] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[bootstrap] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[bootstrap] ERROR: {msg}", file=sys.stderr, flush=True)


# =============================================================================
# JSON file operations
# =============================================================================

def write_json_atomically(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def read_json(path: Path) -> dict:
    """Read JSON file, returning empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    return {}


# =============================================================================
# Environment secret handling
# =============================================================================

def get_env_secret(secret_name: str) -> str | None:
    """Get environment secret value, returning None if not set."""
    # Handle GitHub Actions secrets format
    value = os.environ.get(secret_name)
    if value is None:
        # Try lowercase
        value = os.environ.get(secret_name.lower())
    return value


# =============================================================================
# Kubernetes event analysis
# =============================================================================

def _is_transient_volume_binding_conflict(reason: str, message: str) -> bool:
    """Detect transient VolumeBinding PreBind conflict that should be retried.

    This catches the scheduler PreBind race condition where the PVC object changes
    while the scheduler tries to bind or reserve volume state. Kubernetes should
    retry this automatically, so we treat it as nonfatal.

    Args:
        reason: Event reason (e.g., "FailedScheduling")
        message: Event message containing the error details

    Returns:
        True if this is a transient VolumeBinding PreBind conflict, False otherwise
    """
    msg = message.lower()
    return (
        reason == "FailedScheduling"
        and "prebind plugin" in msg
        and "volumebinding" in msg
        and "object has been modified" in msg
        and "please apply your changes" in msg
    )


def _detect_transient_volume_binding_conflict_from_events(events_json: str) -> tuple[bool, str, str]:
    """Scan events JSON for transient VolumeBinding PreBind conflict.

    Returns: (has_transient, message, pod_name)
    """
    if not events_json:
        return False, "", ""
    try:
        data = json.loads(events_json)
        for event in data.get("items", []):
            if event.get("reason") == "FailedScheduling":
                msg = event.get("message", "") or ""
                if _is_transient_volume_binding_conflict("FailedScheduling", msg):
                    involved = event.get("involvedObject", {})
                    obj_name = involved.get("name", "unknown")
                    return True, msg, obj_name
    except (json.JSONDecodeError, TypeError):
        pass
    return False, "", ""


# Re-export for backward compatibility with tests
__all__ = [
    "log",
    "warn",
    "error",
    "write_json_atomically",
    "read_json",
    "get_env_secret",
    "_is_transient_volume_binding_conflict",
    "_detect_transient_volume_binding_conflict_from_events",
]
