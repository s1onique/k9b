"""Type narrowing helpers for incident LLM diagnosis.

This module provides runtime type narrowing for handling object types from
Mapping[str, object] case-file packets.
"""

from __future__ import annotations

from collections.abc import Mapping


def _as_object_mapping(value: object) -> Mapping[str, object]:
    """Narrow object to Mapping[str, object] with runtime safety check."""
    if isinstance(value, Mapping):
        return value
    return {}


def _as_object_list(value: object) -> list[object]:
    """Narrow object to list[object] with runtime safety check."""
    if isinstance(value, list):
        return value
    return []
