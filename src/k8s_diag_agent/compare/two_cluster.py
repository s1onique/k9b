"""Simple comparator for two cluster snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..collect.cluster_snapshot import ClusterSnapshot


@dataclass(frozen=True)
class ComparisonIntentMetadata:
    intent: Optional[str]
    expected_drift_categories: Tuple[str, ...] = ()
    unexpected_drift_categories: Tuple[str, ...] = ()
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "expected_drift_categories": list(self.expected_drift_categories),
            "unexpected_drift_categories": list(self.unexpected_drift_categories),
            "notes": self.notes,
        }

@dataclass(frozen=True)
class ClusterComparison:
    primary_snapshot: ClusterSnapshot
    secondary_snapshot: ClusterSnapshot
    differences: Dict[str, Dict[str, Any]]
    metadata: Optional[ComparisonIntentMetadata] = None


def compare_snapshots(
    primary: ClusterSnapshot,
    secondary: ClusterSnapshot,
    metadata: Optional[ComparisonIntentMetadata] = None,
) -> ClusterComparison:
    metadata_diffs = _compare_metadata(primary, secondary)
    metric_diffs = _compare_metrics(primary, secondary)
    helm_diffs = _compare_helm_releases(primary, secondary)
    crd_diffs = _compare_crds(primary, secondary)
    differences: Dict[str, Dict[str, Any]] = {}
    if metadata_diffs:
        differences["metadata"] = metadata_diffs
    if metric_diffs:
        differences["metrics"] = metric_diffs
    if helm_diffs:
        differences["helm_releases"] = helm_diffs
    if crd_diffs:
        differences["crds"] = crd_diffs
    return ClusterComparison(
        primary_snapshot=primary,
        secondary_snapshot=secondary,
        differences=differences,
        metadata=metadata,
    )


def _compare_metadata(
    primary: ClusterSnapshot, secondary: ClusterSnapshot
) -> Dict[str, Dict[str, Any]]:
    diffs: Dict[str, Dict[str, Any]] = {}
    fields = [
        "node_count",
        "pod_count",
        "region",
        "control_plane_version",
    ]
    for field_name in fields:
        primary_value = getattr(primary.metadata, field_name)
        secondary_value = getattr(secondary.metadata, field_name)
        if primary_value != secondary_value:
            diffs[field_name] = {
                "primary": primary_value,
                "secondary": secondary_value,
            }
    return diffs


def _compare_metrics(
    primary: ClusterSnapshot, secondary: ClusterSnapshot
) -> Dict[str, Dict[str, Any]]:
    diffs: Dict[str, Dict[str, Any]] = {}
    keys = set(primary.metrics) | set(secondary.metrics)
    for key in keys:
        primary_value = primary.metrics.get(key)
        secondary_value = secondary.metrics.get(key)
        if primary_value != secondary_value:
            diffs[key] = {
                "primary": primary_value,
                "secondary": secondary_value,
            }
    return diffs


def _compare_helm_releases(
    primary: ClusterSnapshot, secondary: ClusterSnapshot
) -> Dict[str, Dict[str, Any]]:
    diffs: Dict[str, Dict[str, Any]] = {}
    keys = sorted(set(primary.helm_releases) | set(secondary.helm_releases))
    for key in keys:
        primary_release = primary.helm_releases.get(key)
        secondary_release = secondary.helm_releases.get(key)
        if primary_release and secondary_release:
            if (
                primary_release.chart_version != secondary_release.chart_version
                or primary_release.app_version != secondary_release.app_version
            ):
                diffs[key] = {
                    "primary": primary_release.to_dict(),
                    "secondary": secondary_release.to_dict(),
                }
        elif primary_release:
            diffs[key] = {
                "primary": primary_release.to_dict(),
                "secondary": None,
            }
        elif secondary_release:
            diffs[key] = {
                "primary": None,
                "secondary": secondary_release.to_dict(),
            }
    return diffs


def _compare_crds(
    primary: ClusterSnapshot, secondary: ClusterSnapshot
) -> Dict[str, Dict[str, Any]]:
    diffs: Dict[str, Dict[str, Any]] = {}
    keys = sorted(set(primary.crds) | set(secondary.crds))
    for key in keys:
        primary_crd = primary.crds.get(key)
        secondary_crd = secondary.crds.get(key)
        if primary_crd and secondary_crd:
            if (
                primary_crd.storage_version != secondary_crd.storage_version
                or primary_crd.served_versions != secondary_crd.served_versions
            ):
                diffs[key] = {
                    "primary": primary_crd.to_dict(),
                    "secondary": secondary_crd.to_dict(),
                }
        elif primary_crd:
            diffs[key] = {
                "primary": primary_crd.to_dict(),
                "secondary": None,
            }
        elif secondary_crd:
            diffs[key] = {
                "primary": None,
                "secondary": secondary_crd.to_dict(),
            }
    return diffs
