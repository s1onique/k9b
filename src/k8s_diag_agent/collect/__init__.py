"""Collection module for cluster data gathering and snapshot creation.

Public API:
"""

from .cluster_snapshot import (
    ClusterHealthSignals,
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    CRDRecord,
    HelmReleaseRecord,
    NodeConditionCounts,
    PodHealthCounts,
    WarningEventSummary,
    extract_cluster_snapshots,
)
from .fixture_loader import load_fixture, load_fixture_from_str
from .live_snapshot import (
    collect_cluster_snapshot,
    list_kube_contexts,
)

__all__ = [
    # Cluster snapshot types
    "ClusterSnapshot",
    "ClusterSnapshotMetadata",
    "CollectionStatus",
    "ClusterHealthSignals",
    "NodeConditionCounts",
    "PodHealthCounts",
    "WarningEventSummary",
    "HelmReleaseRecord",
    "CRDRecord",
    # Functions
    "extract_cluster_snapshots",
    "load_fixture",
    "load_fixture_from_str",
    "list_kube_contexts",
    "collect_cluster_snapshot",
]
