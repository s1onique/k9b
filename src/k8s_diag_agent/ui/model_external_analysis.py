"""View models for external analysis UI layer (UI model module).

This module contains external-analysis-related view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_external_analysis.py -> model_primitives.py
- model.py imports from model_external_analysis.py for re-export compatibility.

Note: External-analysis models represent provider-assisted analysis artifacts
(LLM-based or external tool outputs) that enrich the diagnostic pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
)


@dataclass(frozen=True)
class ExternalAnalysisView:
    """View model for a single external analysis artifact in the UI."""
    tool_name: str
    cluster_label: str | None
    status: str
    summary: str | None
    findings: tuple[str, ...]
    suggested_next_checks: tuple[str, ...]
    timestamp: str
    artifact_path: str | None


@dataclass(frozen=True)
class ExternalAnalysisSummary:
    """View model for the aggregated external analysis summary across all artifacts."""
    count: int
    status_counts: tuple[tuple[str, int], ...]
    artifacts: tuple[ExternalAnalysisView, ...]


def _build_external_analysis_view(raw: Mapping[str, object]) -> ExternalAnalysisView:
    """Build ExternalAnalysisView from raw JSON data.

    Returns a view with defaults for non-Mapping input.
    Handles snake_case keys from artifact storage.
    """
    return ExternalAnalysisView(
        tool_name=_coerce_str(raw.get("tool_name")),
        cluster_label=_coerce_optional_str(raw.get("cluster_label")),
        status=_coerce_str(raw.get("status")),
        summary=_coerce_optional_str(raw.get("summary")),
        findings=_coerce_sequence(raw.get("findings")),
        suggested_next_checks=_coerce_sequence(raw.get("suggested_next_checks")),
        timestamp=_coerce_str(raw.get("timestamp")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
    )


def _build_external_analysis(raw: object | None) -> ExternalAnalysisSummary:
    """Build ExternalAnalysisSummary from raw JSON data.

    Returns a default view with count=0 for non-Mapping input.
    Silently skips non-Mapping entries in status_counts and artifacts lists.
    Handles snake_case keys from artifact storage.
    """
    if not isinstance(raw, Mapping):
        return ExternalAnalysisSummary(count=0, status_counts=(), artifacts=())
    status_counts_raw = raw.get("status_counts") or ()
    status_counts = tuple(
        (_coerce_str(entry.get("status")), _coerce_int(entry.get("count")))
        for entry in status_counts_raw
        if isinstance(entry, Mapping)
    )
    artifacts_raw = raw.get("artifacts") or ()
    artifacts: tuple[ExternalAnalysisView, ...] = ()
    if isinstance(artifacts_raw, Sequence) and not isinstance(artifacts_raw, str | bytes):
        artifacts = tuple(
            _build_external_analysis_view(entry)
            for entry in artifacts_raw
            if isinstance(entry, Mapping)
        )
    return ExternalAnalysisSummary(
        count=_coerce_int(raw.get("count")),
        status_counts=status_counts,
        artifacts=artifacts,
    )
