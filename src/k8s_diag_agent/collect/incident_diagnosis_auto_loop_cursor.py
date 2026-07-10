"""Cursor persistence for automatic diagnosis loop.

This module provides cursor-based pagination to ensure fair queuing:
- Incidents are never permanently starved behind repeatedly selected items
- The next run resumes from where the previous run left off

Cursor file format: JSON with last_incident_id and saved_at timestamp.
Cursor file is stored under runs/state/ to avoid being misclassified as an artifact.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

_logger = logging.getLogger(__name__)

# Cursor file name for cursor-based pagination
# Stored under runs/state/ to avoid artifact discovery in external-analysis/
_SCAN_CURSOR_FILE = "auto-loop-scan-cursor.json"


def _get_cursor_path(runs_dir: Path) -> Path:
    """Get the cursor file path.

    The runs_dir should be the runs/ directory at the repo root, NOT
    external_analysis_dir. The cursor is stored under:
        {runs_dir}/state/automatic-diagnosis/scan-cursor.json

    Args:
        runs_dir: Path to the runs/ directory at repo root

    Returns:
        Path to the cursor file
    """
    return runs_dir / "state" / "automatic-diagnosis" / _SCAN_CURSOR_FILE


def _load_scan_cursor(runs_dir: Path) -> str | None:
    """Load the persisted scan cursor from file.

    The cursor is the incident_id after which we should resume scanning.
    Returns None if no cursor exists or file is invalid.
    """
    cursor_file = _get_cursor_path(runs_dir)
    try:
        if cursor_file.exists():
            with open(cursor_file) as f:
                data = json.load(f)
                last_id: str | None = data.get("last_incident_id")
                return last_id
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_scan_cursor(runs_dir: Path, last_incident_id: str) -> None:
    """Persist the scan cursor to file (crash-safe).

    Stores the last processed incident_id so the next run can resume after it.
    Uses os.replace() for atomic write on POSIX systems.
    This ensures fair queuing: incidents are never permanently starved.

    The entire operation is wrapped in try/except to ensure the diagnosis
    loop continues even if cursor persistence fails.
    """
    cursor_file = _get_cursor_path(runs_dir)
    try:
        # Ensure directory exists and write atomically
        # Both mkdir and temp file creation are inside try to catch filesystem errors
        cursor_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=cursor_file.parent,
            prefix=".cursor_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "last_incident_id": last_incident_id,
                    "saved_at": datetime.now(UTC).isoformat(),
                }, f)
            # Atomic replace on POSIX - documented as atomic on success
            os.replace(tmp_path, cursor_file)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        # Catch all exceptions including permission errors and filesystem issues
        # The diagnosis loop should continue even if cursor persistence fails
        _logger.warning(
            "Failed to persist scan cursor",
            extra={
                "event": "scan-cursor-persist-failed",
                "last_incident_id": last_incident_id,
                "error": str(e),
            },
        )


def _clear_scan_cursor(runs_dir: Path) -> None:
    """Clear the persisted scan cursor.

    Called when we've completed a full scan cycle (no more incidents to process).
    """
    cursor_file = _get_cursor_path(runs_dir)
    try:
        if cursor_file.exists():
            cursor_file.unlink()
    except OSError:
        pass
