"""View models for deterministic next-check UI layer (UI model module).

This module contains deterministic next-check-specific view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_deterministic_next_checks.py -> model_primitives.py
- model.py imports from model_deterministic_next_checks.py for re-export compatibility.

Note: Deterministic next-check models are intentionally isolated from plan/candidate models
because they represent a different workflow (rule-based next checks vs. LLM-planned candidates).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class DeterministicNextCheckSummaryView:
    """View model for a single deterministic next-check summary within a cluster."""
    description: str
    owner: str
    method: str
    evidence_needed: tuple[str, ...]
    workstream: str
    urgency: str
    is_primary_triage: bool
    why_now: str
    priority_score: int | None = None


@dataclass(frozen=True)
class DeterministicNextCheckClusterView:
    """View model for a cluster's deterministic next-check state."""
    label: str
    context: str
    top_problem: str | None
    deterministic_next_check_count: int
    deterministic_next_check_summaries: tuple[DeterministicNextCheckSummaryView, ...]
    drilldown_available: bool
    assessment_artifact_path: str | None
    drilldown_artifact_path: str | None


@dataclass(frozen=True)
class DeterministicNextChecksView:
    """View model for the complete deterministic next-checks state."""
    cluster_count: int
    total_next_check_count: int
    clusters: tuple[DeterministicNextCheckClusterView, ...]


def _build_deterministic_next_check_summary_view(
    raw: Mapping[str, object],
) -> DeterministicNextCheckSummaryView:
    """Build DeterministicNextCheckSummaryView from raw JSON data.

    Handles both camelCase keys (from artifact API) and snake_case variants.
    Returns a view with defaults for non-Mapping input.
    """
    return DeterministicNextCheckSummaryView(
        description=_coerce_str(raw.get("description")),
        owner=_coerce_str(raw.get("owner")),
        method=_coerce_str(raw.get("method")),
        evidence_needed=_coerce_sequence(raw.get("evidenceNeeded")),
        workstream=_coerce_str(raw.get("workstream")),
        urgency=_coerce_str(raw.get("urgency")),
        is_primary_triage=bool(raw.get("isPrimaryTriage")),
        why_now=_coerce_str(raw.get("whyNow")),
        priority_score=_coerce_optional_int(raw.get("priorityScore")),
    )


def _build_deterministic_next_check_cluster_view(
    raw: Mapping[str, object],
) -> DeterministicNextCheckClusterView:
    """Build DeterministicNextCheckClusterView from raw JSON data.

    Handles both camelCase keys (from artifact API) and snake_case variants.
    Returns a view with defaults for non-Mapping input.
    """
    summaries_raw = raw.get("deterministicNextCheckSummaries") or ()
    summaries = tuple(
        _build_deterministic_next_check_summary_view(entry)
        for entry in summaries_raw
        if isinstance(entry, Mapping)
    )
    return DeterministicNextCheckClusterView(
        label=_coerce_str(raw.get("label")),
        context=_coerce_str(raw.get("context")),
        top_problem=_coerce_optional_str(raw.get("topProblem")),
        deterministic_next_check_count=_coerce_int(raw.get("deterministicNextCheckCount")),
        deterministic_next_check_summaries=summaries,
        drilldown_available=bool(raw.get("drilldownAvailable")),
        assessment_artifact_path=_coerce_optional_str(raw.get("assessmentArtifactPath")),
        drilldown_artifact_path=_coerce_optional_str(raw.get("drilldownArtifactPath")),
    )


def _build_deterministic_next_checks_view(
    raw: object | None,
) -> DeterministicNextChecksView | None:
    """Build DeterministicNextChecksView from raw JSON data (deterministic_next_checks field).

    Returns None for non-Mapping input to signal missing data.
    Silently skips non-Mapping entries in cluster lists.
    Handles both camelCase keys (from artifact API) and snake_case variants.
    """
    if not isinstance(raw, Mapping):
        return None
    clusters_raw = raw.get("clusters") or ()
    clusters = tuple(
        _build_deterministic_next_check_cluster_view(entry)
        for entry in clusters_raw
        if isinstance(entry, Mapping)
    )
    return DeterministicNextChecksView(
        cluster_count=_coerce_int(raw.get("clusterCount")),
        total_next_check_count=_coerce_int(raw.get("totalNextCheckCount")),
        clusters=clusters,
    )
