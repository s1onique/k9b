"""Application-level incident store provider/factory.

This module provides an injectable factory for creating fresh IncidentStore instances,
enabling deterministic test injection and clean separation of ownership.

Store ownership:
- Process-local by default (in-memory)
- File-backed when K9B_INCIDENT_STORE_PATH is set
- Owned by the backend/API layer
- Exposed through provider function for test injection

Environment variables:
- K9B_INCIDENT_STORE_PATH: Path to JSON file for persistent incident store.
    When set, uses FileBackedIncidentStore instead of in-memory store.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation

Architecture note:
- In-memory store: process-local singleton, lost on pod restart
- File-backed store: shared via mounted volume, survives pod restarts
- Both pods (scheduler, backend) must use the same path for shared visibility
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .incident_store import IncidentStore
from .incident_store_file import DEFAULT_INCIDENT_STORE_DIR, FileBackedIncidentStore

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Environment variable for file-backed store path
ENV_INCIDENT_STORE_PATH = "K9B_INCIDENT_STORE_PATH"

# Global process-local store instance (for production use)
# Tests can inject their own store via set_store()
_process_store: IncidentStore | None = None


def _configure_file_backed_store(path: Path) -> FileBackedIncidentStore:
    """Configure and log file-backed store initialization."""
    _logger.info(
        "Configuring file-backed incident store",
        extra={
            "event": "incident-store-configuring",
            "store_kind": "file",
            "path": str(path),
        },
    )
    store = FileBackedIncidentStore(path)
    _logger.info(
        "File-backed incident store configured",
        extra={
            "event": "incident-store-configured",
            "store_kind": "file",
            "path": str(path),
            "loaded_incidents": len(store),
        },
    )
    return store


def get_incident_store() -> IncidentStore:
    """Get the current incident store instance.

    Returns the configured store based on environment:
    - K9B_INCIDENT_STORE_PATH set: FileBackedIncidentStore
    - Otherwise: In-memory IncidentStore

    Returns the process-local store if set, otherwise creates a new one.

    This function enables test injection by allowing tests to set
    a fresh store instance before calling handlers that depend on it.

    Returns:
        The current IncidentStore instance
    """
    global _process_store
    if _process_store is None:
        # Check for file-backed store configuration
        store_path_env = os.environ.get(ENV_INCIDENT_STORE_PATH)
        if store_path_env:
            path = Path(store_path_env)
            _process_store = _configure_file_backed_store(path)
        else:
            _process_store = IncidentStore()
            _logger.debug(
                "Using in-memory incident store",
                extra={
                    "event": "incident-store-configured",
                    "store_kind": "memory",
                },
            )
    return _process_store


def set_incident_store(store: IncidentStore | None) -> None:
    """Set a custom incident store instance.

    This is intended for test injection to provide a fresh, controllable store.

    Args:
        store: The IncidentStore instance to use, or None to reset to default
    """
    global _process_store
    _process_store = store


def reset_incident_store() -> None:
    """Reset the incident store to None.

    After calling this, get_incident_store() will create a fresh store
    based on environment configuration.

    This is useful for test cleanup.
    """
    global _process_store
    _process_store = None


def create_fresh_store() -> IncidentStore:
    """Create a fresh incident store instance.

    This is a convenience factory function that always returns a new store,
    useful when you need to ensure isolation from the process-local store.

    Returns:
        A new IncidentStore instance (in-memory only)
    """
    return IncidentStore()


def create_file_backed_store(path: Path | str | None = None) -> FileBackedIncidentStore:
    """Create a file-backed incident store.

    Args:
        path: Path to the incident store file. If None, uses the environment
            variable K9B_INCIDENT_STORE_PATH, or falls back to
            {DEFAULT_INCIDENT_STORE_DIR}/incident-store.json

    Returns:
        A new FileBackedIncidentStore instance
    """
    if path is None:
        path = os.environ.get(
            ENV_INCIDENT_STORE_PATH,
            f"{DEFAULT_INCIDENT_STORE_DIR}/incident-store.json",
        )
    return FileBackedIncidentStore(Path(path))


def get_incident_store_path() -> Path | None:
    """Get the configured incident store path.

    Returns:
        The Path if K9B_INCIDENT_STORE_PATH is set, None otherwise
    """
    store_path_env = os.environ.get(ENV_INCIDENT_STORE_PATH)
    return Path(store_path_env) if store_path_env else None


def is_file_backed() -> bool:
    """Check if the current store is file-backed.

    Returns:
        True if K9B_INCIDENT_STORE_PATH is set, False otherwise
    """
    return os.environ.get(ENV_INCIDENT_STORE_PATH) is not None


__all__ = [
    "IncidentStore",
    "FileBackedIncidentStore",
    "get_incident_store",
    "set_incident_store",
    "reset_incident_store",
    "create_fresh_store",
    "create_file_backed_store",
    "get_incident_store_path",
    "is_file_backed",
    "ENV_INCIDENT_STORE_PATH",
]
