"""Fleet status summary model extracted from model.py.

This module contains FleetStatusSummary and its builder extracted from model.py
to enable focused modularization while preserving behavior and import compatibility.

Symbols extracted:
- FleetStatusSummary: dataclass for fleet health rating counts and degraded clusters
- _build_fleet_status: builder for FleetStatusSummary from Mapping
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class FleetStatusSummary:
    """View model for fleet health status summary."""

    rating_counts: tuple[tuple[str, int], ...]
    degraded_clusters: tuple[str, ...]


def _build_fleet_status(raw: object | None) -> FleetStatusSummary:
    """Build a FleetStatusSummary from raw fleet status data.

    Args:
        raw: Raw fleet status data mapping or None

    Returns:
        FleetStatusSummary constructed from the raw data
    """
    if not isinstance(raw, Mapping):
        return FleetStatusSummary(rating_counts=(), degraded_clusters=())
    counts_raw = raw.get("rating_counts") or ()
    rating_counts = tuple(
        (_coerce_str(entry.get("rating")), _coerce_int(entry.get("count")))
        for entry in counts_raw
        if isinstance(entry, Mapping)
    )
    degraded = _coerce_sequence(raw.get("degraded_clusters"))
    return FleetStatusSummary(rating_counts=rating_counts, degraded_clusters=degraded)