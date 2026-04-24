"""Findings and drilldown availability view models extracted from model.py.

This module contains findings/drilldown-related UI model types extracted from model.py
to enable focused modularization while preserving behavior and import compatibility.

Symbols extracted:
- FindingsView: findings dataclass
- DrilldownCoverageEntry: drilldown coverage entry dataclass
- DrilldownAvailabilityView: drilldown availability summary dataclass
- _build_findings: builder for FindingsView from Mapping
- _build_drilldown_coverage: builder for DrilldownCoverageEntry from Mapping
- _build_drilldown_availability: builder for DrilldownAvailabilityView from Mapping
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
    _serialize_map,
)


@dataclass(frozen=True)
class FindingsView:
    """View model for findings from latest drilldown."""

    label: str | None
    context: str | None
    trigger_reasons: tuple[str, ...]
    warning_events: int
    non_running_pods: int
    summary: tuple[tuple[str, str], ...]
    rollout_status: tuple[str, ...]
    pattern_details: tuple[tuple[str, str], ...]
    artifact_path: str | None = None


@dataclass(frozen=True)
class DrilldownCoverageEntry:
    """View model for a single cluster's drilldown coverage status."""

    label: str
    context: str
    available: bool
    timestamp: str | None
    artifact_path: str | None


@dataclass(frozen=True)
class DrilldownAvailabilityView:
    """View model for overall drilldown availability summary."""

    total_clusters: int
    available: int
    missing: int
    missing_clusters: tuple[str, ...]
    coverage: tuple[DrilldownCoverageEntry, ...]


def _build_findings(raw: object | None) -> FindingsView | None:
    """Build a FindingsView from raw findings data.

    Args:
        raw: Raw findings data mapping or None

    Returns:
        FindingsView constructed from the raw data, or None if input is not a Mapping
    """
    if not isinstance(raw, Mapping):
        return None
    return FindingsView(
        label=_coerce_optional_str(raw.get("label")),
        context=_coerce_optional_str(raw.get("context")),
        trigger_reasons=_coerce_sequence(raw.get("trigger_reasons")),
        warning_events=_coerce_int(raw.get("warning_events")),
        non_running_pods=_coerce_int(raw.get("non_running_pods")),
        summary=_serialize_map(raw.get("summary")),
        rollout_status=_coerce_sequence(raw.get("rollout_status")),
        pattern_details=_serialize_map(raw.get("pattern_details")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _build_drilldown_coverage(raw: Mapping[str, object]) -> DrilldownCoverageEntry:
    """Build a DrilldownCoverageEntry from raw cluster coverage data.

    Args:
        raw: Raw cluster drilldown coverage data mapping

    Returns:
        DrilldownCoverageEntry constructed from the raw data
    """
    return DrilldownCoverageEntry(
        label=_coerce_str(raw.get("label")),
        context=_coerce_str(raw.get("context")),
        available=bool(raw.get("available")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _build_drilldown_availability(raw: object | None) -> DrilldownAvailabilityView:
    """Build a DrilldownAvailabilityView from raw drilldown availability data.

    Args:
        raw: Raw drilldown availability data mapping or None

    Returns:
        DrilldownAvailabilityView with coverage entries constructed from the raw data
    """
    if not isinstance(raw, Mapping):
        return DrilldownAvailabilityView(
            total_clusters=0,
            available=0,
            missing=0,
            missing_clusters=(),
            coverage=(),
        )
    coverage_raw = raw.get("coverage") or ()
    coverage = tuple(
        _build_drilldown_coverage(entry)
        for entry in coverage_raw
        if isinstance(entry, Mapping)
    )
    return DrilldownAvailabilityView(
        total_clusters=_coerce_int(raw.get("total_clusters")),
        available=_coerce_int(raw.get("available")),
        missing=_coerce_int(raw.get("missing")),
        missing_clusters=_coerce_sequence(raw.get("missing_clusters")),
        coverage=coverage,
    )
