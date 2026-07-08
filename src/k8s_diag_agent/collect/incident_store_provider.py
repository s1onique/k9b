"""Application-level incident store provider/factory.

This module provides an injectable factory for creating fresh IncidentStore instances,
enabling deterministic test injection and clean separation of ownership.

Store ownership:
- Process-local by default (in-memory)
- File-backed when K9B_INCIDENT_STORE_BACKEND=file
- SQLite-backed when K9B_INCIDENT_STORE_BACKEND=sqlite (production default after this ACT)
- Owned by the backend/API layer
- Exposed through provider function for test injection

Process roles (enforced via K9B_PROCESS_ROLE):
- backend: Can use any backend (SQLite, file, memory). Backend process owns SQLite writes.
- scheduler: Cannot use SQLite backend directly - must submit via internal API.
- (unset): Development mode, all backends allowed.

Environment variables:
- K9B_INCIDENT_STORE_BACKEND: Backend type (memory|file|sqlite)
    - memory: In-memory IncidentStore (default for tests)
    - file: FileBackedIncidentStore via K9B_INCIDENT_STORE_PATH
    - sqlite: SQLiteIncidentStore via K9B_INCIDENT_STORE_SQLITE_PATH
- K9B_INCIDENT_STORE_PATH: Path to JSON file for file-backed store
- K9B_INCIDENT_STORE_SQLITE_PATH: Path to SQLite database for sqlite store
- K9B_INCIDENT_SQLITE_JOURNAL_MODE: SQLite journal mode (DELETE|TRUNCATE|PERSIST|WAL)
- K9B_PROCESS_ROLE: Process role (backend|scheduler). SQLite requires backend role.

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO scheduler direct SQLite writes (backend-owned only)

Architecture note:
- In-memory store: process-local singleton, lost on pod restart
- File-backed store: shared via mounted volume, survives pod restarts
- SQLite store: backend-owned, append-only event sourcing, survives restarts
- Scheduler does NOT write SQLite directly - submits via internal API
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .incident_store import IncidentStore
from .incident_store_file import DEFAULT_INCIDENT_STORE_DIR, FileBackedIncidentStore

# Import SQLite store conditionally (only if sqlite3 is available)
try:
    from .incident_store_sqlite import (
        DEFAULT_JOURNAL_MODE,
        DEFAULT_SQLITE_PATH,
        SQLiteIncidentStore,
    )
    from .incident_store_sqlite import (
        ENV_JOURNAL_MODE as SQLITE_ENV_JOURNAL_MODE,
    )
    from .incident_store_sqlite import (
        ENV_SQLITE_PATH as SQLITE_ENV_PATH,
    )
    _SQLITE_AVAILABLE = True
except ImportError:
    _SQLITE_AVAILABLE = False
    SQLiteIncidentStore = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

# Environment variables
ENV_INCIDENT_STORE_PATH = "K9B_INCIDENT_STORE_PATH"
ENV_INCIDENT_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Backend types
BACKEND_MEMORY = "memory"
BACKEND_FILE = "file"
BACKEND_SQLITE = "sqlite"

# Process roles
ROLE_BACKEND = "backend"
ROLE_SCHEDULER = "scheduler"

# Global process-local store instance (for production use)
# Tests can inject their own store via set_store()
_process_store: IncidentStore | None = None


def _get_process_role() -> str:
    """Get the current process role from environment.

    Returns:
        Process role string ("backend", "scheduler", or "" for unset/dev)
    """
    return os.environ.get(ENV_PROCESS_ROLE, "").lower()


def _can_use_sqlite_backend() -> bool:
    """Check if current process can use SQLite backend.

    SQLite backend requires ROLE_BACKEND to prevent scheduler from writing directly.

    Returns:
        True if SQLite backend is allowed, False if forbidden
    """
    role = _get_process_role()
    if role == ROLE_SCHEDULER:
        _logger.error(
            "Scheduler process cannot use SQLite incident store directly. "
            "Must submit promotions via internal API.",
            extra={
                "event": "sqlite-backend-forbidden",
                "role": role,
                "allowed_role": ROLE_BACKEND,
            },
        )
        return False
    return True


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


def _configure_sqlite_store(
    path: Path,
    journal_mode: str = DEFAULT_JOURNAL_MODE,
) -> SQLiteIncidentStore:
    """Configure and log SQLite store initialization."""
    _logger.info(
        "Configuring SQLite incident store",
        extra={
            "event": "incident-store-configuring",
            "store_kind": "sqlite",
            "path": str(path),
            "journal_mode": journal_mode,
        },
    )
    store = SQLiteIncidentStore(path, journal_mode=journal_mode)
    _logger.info(
        "SQLite incident store configured",
        extra={
            "event": "incident-store-configured",
            "store_kind": "sqlite",
            "path": str(path),
            "journal_mode": journal_mode,
            "loaded_incidents": len(store),
        },
    )
    return store


def get_incident_store() -> IncidentStore:
    """Get the current incident store instance.

    Returns the configured store based on environment:
    - K9B_INCIDENT_STORE_BACKEND=sqlite: SQLiteIncidentStore (requires K9B_PROCESS_ROLE=backend)
    - K9B_INCIDENT_STORE_BACKEND=file or K9B_INCIDENT_STORE_PATH set: FileBackedIncidentStore
    - Otherwise: In-memory IncidentStore

    Returns the process-local store if set, otherwise creates a new one.

    This function enables test injection by allowing tests to set
    a fresh store instance before calling handlers that depend on it.

    Returns:
        The current IncidentStore instance

    Raises:
        RuntimeError: If SQLite backend is requested but K9B_PROCESS_ROLE is not "backend"
    """
    global _process_store
    if _process_store is None:
        backend = os.environ.get(ENV_INCIDENT_STORE_BACKEND, "").lower()

        if backend == BACKEND_SQLITE:
            # Enforce role guard: scheduler cannot use SQLite directly
            if not _can_use_sqlite_backend():
                raise RuntimeError(
                    "Cannot use SQLite backend: scheduler process must not open SQLite incident store. "
                    "Submit promotions via internal API instead."
                )

            if not _SQLITE_AVAILABLE:
                _logger.error(
                    "SQLite backend requested but sqlite3 module not available. "
                    "Falling back to in-memory store."
                )
                _process_store = IncidentStore()
            else:
                sqlite_path = os.environ.get(
                    SQLITE_ENV_PATH,
                    DEFAULT_SQLITE_PATH,
                )
                journal_mode = os.environ.get(
                    SQLITE_ENV_JOURNAL_MODE,
                    DEFAULT_JOURNAL_MODE,
                )
                _process_store = _configure_sqlite_store(Path(sqlite_path), journal_mode)

        elif backend == BACKEND_FILE or os.environ.get(ENV_INCIDENT_STORE_PATH):
            store_path_env = os.environ.get(ENV_INCIDENT_STORE_PATH)
            if store_path_env:
                _process_store = _configure_file_backed_store(Path(store_path_env))
            else:
                _process_store = _configure_file_backed_store(
                    Path(f"{DEFAULT_INCIDENT_STORE_DIR}/incident-store.json")
                )

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


def create_sqlite_store(
    path: Path | str | None = None,
    journal_mode: str = DEFAULT_JOURNAL_MODE,
) -> SQLiteIncidentStore | None:
    """Create a SQLite incident store.

    Args:
        path: Path to the SQLite database file. If None, uses
            K9B_INCIDENT_STORE_SQLITE_PATH or DEFAULT_SQLITE_PATH.
        journal_mode: SQLite journal mode (DELETE|TRUNCATE|PERSIST|WAL)

    Returns:
        A new SQLiteIncidentStore instance, or None if SQLite not available

    Raises:
        RuntimeError: If called from scheduler process (must use backend API)
    """
    # Enforce role guard - scheduler must not open SQLite directly
    if not _can_use_sqlite_backend():
        raise RuntimeError(
            "Cannot create SQLite incident store: scheduler process must not "
            "open SQLite directly. Use the backend internal API instead."
        )

    if not _SQLITE_AVAILABLE:
        _logger.warning(
            "SQLite store requested but sqlite3 module not available"
        )
        return None

    if path is None:
        path = os.environ.get(SQLITE_ENV_PATH, DEFAULT_SQLITE_PATH)

    return SQLiteIncidentStore(Path(path), journal_mode=journal_mode)


def get_incident_store_path() -> Path | None:
    """Get the configured incident store path.

    Returns:
        The Path if K9B_INCIDENT_STORE_PATH is set, None otherwise
    """
    store_path_env = os.environ.get(ENV_INCIDENT_STORE_PATH)
    return Path(store_path_env) if store_path_env else None


def get_incident_store_sqlite_path() -> Path | None:
    """Get the configured SQLite incident store path.

    Returns:
        The Path if K9B_INCIDENT_STORE_SQLITE_PATH is set, None otherwise
    """
    if not _SQLITE_AVAILABLE:
        return None
    sqlite_path_env = os.environ.get(SQLITE_ENV_PATH)
    return Path(sqlite_path_env) if sqlite_path_env else None


def is_file_backed() -> bool:
    """Check if the current store is file-backed.

    Returns:
        True if K9B_INCIDENT_STORE_PATH is set, False otherwise
    """
    return os.environ.get(ENV_INCIDENT_STORE_PATH) is not None


def is_sqlite_backed() -> bool:
    """Check if SQLite backend is configured.

    Returns:
        True if K9B_INCIDENT_STORE_BACKEND=sqlite, False otherwise
    """
    if not _SQLITE_AVAILABLE:
        return False
    backend = os.environ.get(ENV_INCIDENT_STORE_BACKEND, "").lower()
    return backend == BACKEND_SQLITE


def get_backend_type() -> str:
    """Get the configured backend type.

    Returns:
        Backend type: "memory", "file", or "sqlite"
    """
    backend = os.environ.get(ENV_INCIDENT_STORE_BACKEND, "").lower()
    if backend in (BACKEND_MEMORY, BACKEND_FILE, BACKEND_SQLITE):
        return backend

    # Legacy behavior: check K9B_INCIDENT_STORE_PATH
    if os.environ.get(ENV_INCIDENT_STORE_PATH):
        return BACKEND_FILE

    return BACKEND_MEMORY


__all__ = [
    "IncidentStore",
    "FileBackedIncidentStore",
    "SQLiteIncidentStore",
    "get_incident_store",
    "set_incident_store",
    "reset_incident_store",
    "create_fresh_store",
    "create_file_backed_store",
    "create_sqlite_store",
    "get_incident_store_path",
    "get_incident_store_sqlite_path",
    "is_file_backed",
    "is_sqlite_backed",
    "get_backend_type",
    "ENV_INCIDENT_STORE_PATH",
    "ENV_INCIDENT_STORE_BACKEND",
    "BACKEND_MEMORY",
    "BACKEND_FILE",
    "BACKEND_SQLITE",
    "DEFAULT_SQLITE_PATH",
]
