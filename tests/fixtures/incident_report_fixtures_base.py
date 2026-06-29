"""Base fixtures for incident report testing.

This module provides shared helpers and type definitions used across
incident report fixture families.
"""

from __future__ import annotations

from typing import Any, TypeAlias

JsonObject: TypeAlias = dict[str, Any]


def _freshness(status: str) -> dict[str, Any]:
    """Return a freshness payload with the given status."""
    return {
        "ageSeconds": 600,
        "expectedIntervalSeconds": 300,
        "status": status,
    }
