"""View models for run status/statistics and planner availability (UI layer).

This module contains run-level status, statistics, and planner availability view models
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Moved symbols:
- RunStatsView
- PlannerAvailabilityView
- _build_run_stats_view
- _build_planner_availability_view
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class RunStatsView:
    """View model for run statistics summary."""
    last_run_duration_seconds: int | None = None
    total_runs: int = 0
    p50_run_duration_seconds: int | None = None
    p95_run_duration_seconds: int | None = None
    p99_run_duration_seconds: int | None = None


@dataclass(frozen=True)
class PlannerAvailabilityView:
    """View model for planner availability status."""
    status: str
    reason: str | None
    hint: str | None
    artifact_path: str | None
    next_action_hint: str | None


def _build_run_stats_view(raw: object | None) -> RunStatsView:
    """Build RunStatsView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return RunStatsView()
    return RunStatsView(
        last_run_duration_seconds=_coerce_optional_int(raw.get("last_run_duration_seconds")),
        total_runs=_coerce_int(raw.get("total_runs")),
        p50_run_duration_seconds=_coerce_optional_int(raw.get("p50_run_duration_seconds")),
        p95_run_duration_seconds=_coerce_optional_int(raw.get("p95_run_duration_seconds")),
        p99_run_duration_seconds=_coerce_optional_int(raw.get("p99_run_duration_seconds")),
    )


def _build_planner_availability_view(raw: object | None) -> PlannerAvailabilityView | None:
    """Build PlannerAvailabilityView from raw JSON data, or None if input is not a Mapping."""
    if not isinstance(raw, Mapping):
        return None
    return PlannerAvailabilityView(
        status=_coerce_str(raw.get("status")),
        reason=_coerce_optional_str(raw.get("reason")),
        hint=_coerce_optional_str(raw.get("hint")),
        artifact_path=_coerce_optional_str(raw.get("artifactPath"))
        or _coerce_optional_str(raw.get("artifact_path")),
        next_action_hint=_coerce_optional_str(raw.get("nextActionHint"))
        or _coerce_optional_str(raw.get("next_action_hint")),
    )
