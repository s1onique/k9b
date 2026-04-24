"""Primitives (helpers, coercers, constants) for UI model construction.

This module contains dependency-free model primitives extracted from model.py.
It exists to enable incremental modularization without changing behavior.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import SupportsInt


def _coerce_str(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_str_tuple(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _coerce_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_optional_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    return None


def _coerce_sequence(value: object | None) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    if value is None:
        return ()
    return (str(value),)


def _serialize_map(value: object | None) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Mapping):
        return ()
    results: list[tuple[str, str]] = []
    for key, entry in value.items():
        results.append((str(key), _stringify(entry)))
    return tuple(results)


def _stringify(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _value_from_mapping(mapping: object | None, key: str) -> object | None:
    if isinstance(mapping, Mapping):
        return mapping.get(key)
    return None


# Human-readable labels for origin and state values
_ORIGIN_LABELS: dict[str, str] = {
    "manual": "Manual",
    "alertmanager-crd": "Alertmanager CRD",
    "prometheus-crd-config": "Prometheus Config",
    "service-heuristic": "Service Heuristic",
}

_STATE_LABELS: dict[str, str] = {
    "manual": "Manual",
    "auto-tracked": "Auto-tracked",
    "discovered": "Discovered",
    "degraded": "Degraded",
    "missing": "Missing",
}

_STATE_COLOR_HINTS: dict[str, str] = {
    "manual": "green",
    "auto-tracked": "green",
    "discovered": "yellow",
    "degraded": "red",
    "missing": "gray",
}
