"""Shared test support for Alertmanager discovery tests.

This module provides shared builders, fixtures, and assertions for
test_health_loop_alertmanager_discovery_*.py test files.

Usage:
    from tests.unit.health_loop_alertmanager_discovery_test_support import (
        make_mock_snapshot,
        make_health_target,
        make_health_snapshot_record,
        make_alertmanager_source,
        make_alertmanager_inventory,
        write_empty_baseline,
    )
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from k8s_diag_agent.health.loop import HealthSnapshotRecord

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot, ClusterSnapshotMetadata
from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import HealthTarget


def write_empty_baseline(tmpdir: Path) -> Path:
    """Write an empty baseline policy file.

    Args:
        tmpdir: Temporary directory path

    Returns:
        Path to the written baseline.json file
    """
    baseline_path = tmpdir / "baseline.json"
    baseline_path.write_text(
        json.dumps({
            "control_plane_version_range": {},
            "watched_releases": [],
            "required_crd_families": [],
            "ignored_drift": [],
            "peer_roles": {},
        }),
        encoding="utf-8"
    )
    return baseline_path


def make_mock_snapshot(
    cluster_id: str = "test-id",
    control_plane_version: str = "1.28.0",
    node_count: int = 3,
    pod_count: int = 10,
) -> MagicMock:
    """Create a mock ClusterSnapshot with minimal required attributes.

    Args:
        cluster_id: Cluster identifier
        control_plane_version: Kubernetes version
        node_count: Number of nodes
        pod_count: Number of pods

    Returns:
        MagicMock with ClusterSnapshot spec and required attributes
    """
    metadata = ClusterSnapshotMetadata(
        cluster_id=cluster_id,
        captured_at=datetime.now(UTC),
        control_plane_version=control_plane_version,
        node_count=node_count,
        pod_count=pod_count,
    )

    mock_snapshot = MagicMock(spec=ClusterSnapshot)
    mock_snapshot.metadata = metadata
    mock_snapshot.health_signals = MagicMock()
    mock_snapshot.health_signals.pod_counts = MagicMock()
    mock_snapshot.health_signals.pod_counts.image_pull_backoff = 0
    mock_snapshot.health_signals.warning_events = []

    return mock_snapshot


def make_health_target(
    context: str = "test-context",
    label: str = "test-cluster",
    monitor_health: bool = True,
) -> HealthTarget:
    """Create a HealthTarget with minimal required attributes.

    Args:
        context: Kubernetes context name
        label: Cluster label
        monitor_health: Whether to monitor health

    Returns:
        HealthTarget instance
    """
    return HealthTarget(
        context=context,
        label=label,
        monitor_health=monitor_health,
        watched_helm_releases=(),
        watched_crd_families=(),
        cluster_class="test-class",
        cluster_role="test-role",
        baseline_cohort="test-cohort",
    )


def make_health_snapshot_record(
    output_dir: Path,
    snapshot: MagicMock | None = None,
    target: HealthTarget | None = None,
    snapshot_filename: str = "test.json",
) -> HealthSnapshotRecord:
    """Create a HealthSnapshotRecord with mock snapshot and target.

    Args:
        output_dir: Output directory for health snapshots
        snapshot: Mock snapshot (created if None)
        target: Health target (created if None)
        snapshot_filename: Filename for snapshot path

    Returns:
        HealthSnapshotRecord instance
    """
    # Import here to avoid circular import
    from k8s_diag_agent.health.loop import HealthSnapshotRecord as HSR

    if snapshot is None:
        snapshot = make_mock_snapshot()
    if target is None:
        target = make_health_target()

    return HSR(
        target=target,
        snapshot=snapshot,
        path=output_dir / "health" / "snapshots" / snapshot_filename,
        baseline_policy=BaselinePolicy.empty(),
    )


def make_alertmanager_source(
    source_id: str = "test:am",
    endpoint: str = "http://alertmanager:9093",
    origin: AlertmanagerSourceOrigin = AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
    namespace: str | None = None,
    name: str | None = None,
    cluster_label: str | None = None,
    cluster_uid: str | None = None,
    state: AlertmanagerSourceState = AlertmanagerSourceState.AUTO_TRACKED,
) -> AlertmanagerSource:
    """Create an AlertmanagerSource with specified attributes.

    Args:
        source_id: Unique source identifier
        endpoint: Alertmanager endpoint URL
        origin: Source origin type
        namespace: Kubernetes namespace (for canonical_identity)
        name: Alertmanager name (for canonical_identity)
        cluster_label: Cluster label for per-source tagging
        cluster_uid: Cluster UID
        state: Source state

    Returns:
        AlertmanagerSource instance
    """
    return AlertmanagerSource(
        source_id=source_id,
        endpoint=endpoint,
        origin=origin,
        namespace=namespace,
        name=name,
        cluster_label=cluster_label,
        cluster_uid=cluster_uid,
        state=state,
    )


def make_alertmanager_inventory(
    sources: list[AlertmanagerSource] | None = None,
    cluster_context: str | None = None,
) -> AlertmanagerSourceInventory:
    """Create an AlertmanagerSourceInventory with optional sources.

    Args:
        sources: List of AlertmanagerSource to add (empty if None)
        cluster_context: Cluster context for inventory

    Returns:
        AlertmanagerSourceInventory with added sources
    """
    inventory = AlertmanagerSourceInventory(cluster_context=cluster_context)
    if sources:
        for source in sources:
            inventory.add_source(source)
    return inventory


def capture_write_inventory() -> dict[str, AlertmanagerSourceInventory | None]:
    """Create a dict for capturing written inventory in tests.

    Returns:
        Dict that will be populated with the written inventory
    """
    return {"inv": None}


def write_capture_side_effect(
    output_dir: Path,
    run_id: str,
    captured: dict[str, AlertmanagerSourceInventory | None],
) -> Any:
    """Create a side effect function for capturing write inventory.

    Args:
        output_dir: Output directory
        run_id: Run identifier
        captured: Dict to populate with written inventory

    Returns:
        Side effect function for patching write_alertmanager_sources
    """
    def capture_write(*args: Any, **kwargs: Any) -> Path:
        captured["inv"] = args[1] if len(args) > 1 else kwargs.get("inventory")
        return output_dir / "health" / f"{run_id}-alertmanager-sources.json"
    return capture_write
