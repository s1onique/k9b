"""UI model for cross-cluster comparison findings.

This module provides data classes and builders for surfacing comparison-triggered
cross-cluster findings in the incident report.

Cross-cluster findings are derived from ComparisonTriggerArtifact entries and provide
fleet-level visibility into drift patterns that individual cluster assessments may miss.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..datetime_utils import parse_iso_to_utc


@dataclass(frozen=True)
class CrossClusterFindingView:
    """A cross-cluster finding derived from comparison triggers.

    Cross-cluster findings represent fleet-level drift patterns that involve
    multiple clusters. They are synthesized from comparison trigger artifacts
    and are distinct from per-cluster observations.

    Claims made here follow the incident report taxonomy:
    - observed: deterministic drift signals (e.g., helm release diff count)
    - hypothesis: speculative explanations of why drift exists
    - unknown: missing fleet context
    """

    primary_label: str
    secondary_label: str
    # Drift category counts: e.g., {"helm_releases": 2, "crds": 0, "metadata": 1}
    drift_counts: dict[str, int]
    # The comparison intent classification
    intent: str
    # Trigger reasons - these are the deterministic signals that fired the comparison
    trigger_reasons: tuple[str, ...]
    # Path to the trigger artifact for provenance
    artifact_path: str | None
    # Timestamp of the comparison
    timestamp: datetime


def _build_cross_cluster_findings(
    raw_triggers: list[dict[str, Any]] | None,
) -> tuple[CrossClusterFindingView, ...]:
    """Build cross-cluster findings from raw trigger artifacts.

    Args:
        raw_triggers: List of trigger artifacts from the UI index.

    Returns:
        Tuple of CrossClusterFindingView objects sorted by timestamp (newest first).
    """
    if not raw_triggers:
        return ()

    findings: list[CrossClusterFindingView] = []
    for trigger_raw in raw_triggers:
        if not isinstance(trigger_raw, Mapping):
            continue

        # Parse timestamp
        timestamp_value = trigger_raw.get("timestamp")
        if isinstance(timestamp_value, str):
            parsed_timestamp = parse_iso_to_utc(timestamp_value) or datetime.now()
        else:
            parsed_timestamp = datetime.now()

        # Parse drift counts
        comparison_summary = trigger_raw.get("comparison_summary") or {}
        drift_counts: dict[str, int] = {}
        if isinstance(comparison_summary, Mapping):
            for key, value in comparison_summary.items():
                if isinstance(value, (int, str)):
                    drift_counts[str(key)] = int(value) if isinstance(value, int) else int(value) if value.isdigit() else 0

        # Parse trigger reasons
        trigger_reasons_raw = trigger_raw.get("trigger_reasons") or []
        trigger_reasons: list[str] = []
        if isinstance(trigger_reasons_raw, list):
            for reason in trigger_reasons_raw:
                if reason:
                    trigger_reasons.append(str(reason))

        findings.append(
            CrossClusterFindingView(
                primary_label=str(trigger_raw.get("primary_label", "")),
                secondary_label=str(trigger_raw.get("secondary_label", "")),
                drift_counts=drift_counts,
                intent=str(trigger_raw.get("comparison_intent", "")),
                trigger_reasons=tuple(trigger_reasons),
                artifact_path=str(trigger_raw.get("artifact_path")) if trigger_raw.get("artifact_path") else None,
                timestamp=parsed_timestamp,
            )
        )

    # Sort by timestamp descending (newest first) for consistent ordering
    return tuple(sorted(findings, key=lambda f: f.timestamp, reverse=True))


# Re-export for convenience
__all__ = [
    "CrossClusterFindingView",
    "_build_cross_cluster_findings",
]
