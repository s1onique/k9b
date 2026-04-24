"""View models for cluster-related UI layer.

This module contains cluster-related view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_cluster.py -> model_primitives.py

model.py imports from model_cluster.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
    _value_from_mapping,
)


@dataclass(frozen=True)
class ClusterView:
    """View model for cluster information."""
    label: str
    context: str
    cluster_class: str
    cluster_role: str
    baseline_cohort: str
    node_count: int
    control_plane_version: str
    health_rating: str
    warnings: int
    non_running_pods: int
    baseline_policy_path: str
    missing_evidence: tuple[str, ...]
    latest_run_timestamp: str
    top_trigger_reason: str | None
    drilldown_available: bool
    drilldown_timestamp: str | None
    snapshot_path: str | None
    assessment_path: str | None
    drilldown_path: str | None


def _build_cluster_view(cluster: Mapping[str, object]) -> ClusterView:
    """Build ClusterView from raw cluster mapping."""
    artifacts = cluster.get("artifact_paths")
    snapshot = _coerce_optional_str(_value_from_mapping(artifacts, "snapshot"))
    assessment = _coerce_optional_str(_value_from_mapping(artifacts, "assessment"))
    drilldown = _coerce_optional_str(_value_from_mapping(artifacts, "drilldown"))
    return ClusterView(
        label=_coerce_str(cluster.get("label")),
        context=_coerce_str(cluster.get("context")),
        cluster_class=_coerce_str(cluster.get("cluster_class")),
        cluster_role=_coerce_str(cluster.get("cluster_role")),
        baseline_cohort=_coerce_str(cluster.get("baseline_cohort")),
        node_count=_coerce_int(cluster.get("node_count")),
        control_plane_version=_coerce_str(cluster.get("control_plane_version")),
        health_rating=_coerce_str(cluster.get("health_rating")),
        warnings=_coerce_int(cluster.get("warnings")),
        non_running_pods=_coerce_int(cluster.get("non_running_pods")),
        baseline_policy_path=_coerce_str(cluster.get("baseline_policy_path")),
        missing_evidence=_coerce_sequence(cluster.get("missing_evidence")),
        latest_run_timestamp=_coerce_str(cluster.get("latest_run_timestamp")),
        top_trigger_reason=_coerce_optional_str(cluster.get("top_trigger_reason")),
        drilldown_available=bool(cluster.get("drilldown_available")),
        drilldown_timestamp=_coerce_optional_str(cluster.get("drilldown_timestamp")),
        snapshot_path=snapshot,
        assessment_path=assessment,
        drilldown_path=drilldown,
    )
