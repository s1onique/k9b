"""Application-level incident store provider/factory.

This module provides an injectable factory for creating fresh IncidentStore instances,
enabling deterministic test injection and clean separation of ownership.

Store ownership:
- Process-local by default
- Owned by the backend/API layer
- Exposed through provider function for test injection

Hard constraints enforced:
- NO remediation actions
- NO Kubernetes resource mutation
- NO LLM calls
- NO external tool invocation
- NO persistence (in-memory only)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_store import IncidentStore

if TYPE_CHECKING:
    pass


# Global process-local store instance (for production use)
# Tests can inject their own store via set_store()
_process_store: IncidentStore | None = None


def get_incident_store() -> IncidentStore:
    """Get the current incident store instance.

    Returns the process-local store if set, otherwise creates a new one.

    This function enables test injection by allowing tests to set
    a fresh store instance before calling handlers that depend on it.

    Returns:
        The current IncidentStore instance
    """
    global _process_store
    if _process_store is None:
        _process_store = IncidentStore()
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

    After calling this, get_incident_store() will create a fresh store.
    This is useful for test cleanup.
    """
    global _process_store
    _process_store = None


def create_fresh_store() -> IncidentStore:
    """Create a fresh incident store instance.

    This is a convenience factory function that always returns a new store,
    useful when you need to ensure isolation from the process-local store.

    Returns:
        A new IncidentStore instance
    """
    return IncidentStore()


__all__ = [
    "IncidentStore",
    "get_incident_store",
    "set_incident_store",
    "reset_incident_store",
    "create_fresh_store",
]
