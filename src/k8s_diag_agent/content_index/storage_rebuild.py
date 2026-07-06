"""Content index storage rebuild operations.

This module provides atomic database replacement operations.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _checkpoint_and_close(conn: sqlite3.Connection) -> None:
    """Checkpoint WAL and close connection safely."""
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass
    conn.close()


def atomically_replace_database(
    target_path: Path,
    temp_path: Path,
) -> None:
    """Atomically replace target database with temp database.

    Uses sibling replacement file for safe atomic replacement.

    Args:
        target_path: Path to the existing (or new) target database.
        temp_path: Path to the temporary database with new content.

    Raises:
        FileNotFoundError: If temp database doesn't exist.
    """
    if not temp_path.exists():
        raise FileNotFoundError(f"Temp database not found: {temp_path}")

    # Ensure target parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Use sibling replacement file for atomic swap
    replacement_path = target_path.with_suffix(target_path.suffix + ".replacement")

    # Clean up any existing replacement file
    if replacement_path.exists():
        replacement_path.unlink()

    # Ensure temp DB is checkpointed before moving (WAL -> DELETE mode)
    try:
        temp_conn = sqlite3.connect(str(temp_path))
        try:
            temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            temp_conn.execute("PRAGMA journal_mode = DELETE")
            temp_conn.commit()
        finally:
            temp_conn.close()
    except sqlite3.Error:
        pass

    # Move temp to replacement (atomic on POSIX)
    temp_path.replace(replacement_path)

    # Clean up any leftover WAL/SHM files from temp
    for suffix in (".wal", ".shm"):
        leftover = temp_path.with_suffix(suffix)
        if leftover.exists():
            leftover.unlink()

    # Move replacement to target (atomic on POSIX)
    replacement_path.replace(target_path)
