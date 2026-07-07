"""Tests for Alertmanager discovery snapshot artifact behavior.

Covers:
- rendered health loop snapshot shape
- artifact JSON fields
- summary counts
- degraded/error discovery projection
- backward-compatible snapshot contract
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot, ClusterSnapshotMetadata
from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig, HealthSnapshotRecord, HealthTarget


def _write_empty_baseline(tmpdir: Path) -> Path:
    """Write an empty baseline policy file."""
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


class TestHealthLoopAlertmanagerDiscoverySnapshot(unittest.TestCase):
    """Tests for Alertmanager discovery snapshot artifact behavior."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.output_dir = self.tmpdir / "runs"
        self.output_dir.mkdir(parents=True)

        # Write empty baseline policy (required by HealthRunConfig.load)
        self.baseline_path = _write_empty_baseline(self.tmpdir)

        # Create minimal config for testing
        config_data = {
            "run_label": "test-run",
            "output_dir": str(self.output_dir),
            "collector_version": "test",
            "targets": [
                {
                    "context": "test-context",
                    "label": "test-cluster",
                    "monitor_health": True,
                    "watched_helm_releases": [],
                    "watched_crd_families": [],
                    "cluster_class": "test-class",
                    "cluster_role": "test-role",
                    "baseline_cohort": "test-cohort",
                    "baseline_policy_path": "baseline.json",
                }
            ],
            "peer_mappings": [],
            "comparison_triggers": {},
            "baseline_policy_path": "baseline.json",
        }

        config_path = self.tmpdir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        self.config = HealthRunConfig.load(config_path)
        self.run_id = "test-run-123"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @pytest.mark.mock_kubectl
    def test_writes_alertmanager_sources_artifact(self) -> None:
        """Test that discovery writes {run_id}-alertmanager-sources.json artifact."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["test-context"],
            quiet=True,
            run_id=self.run_id,
        )

        metadata = ClusterSnapshotMetadata(
            cluster_id="test-id",
            captured_at=datetime.now(UTC),
            control_plane_version="1.28.0",
            node_count=3,
            pod_count=10,
        )

        mock_snapshot = MagicMock(spec=ClusterSnapshot)
        mock_snapshot.metadata = metadata

        target = HealthTarget(
            context="test-context",
            label="test-cluster",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="test-class",
            cluster_role="test-role",
            baseline_cohort="test-cohort",
        )

        mock_record = HealthSnapshotRecord(
            target=target,
            snapshot=mock_snapshot,
            path=self.output_dir / "health" / "snapshots" / "test.json",
            baseline_policy=BaselinePolicy.empty(),
        )

        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers") as discover_mock, \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources") as write_mock:

            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id="crd:monitoring/main",
                endpoint="http://alertmanager.monitoring.svc:9093",
                namespace="monitoring",
                name="main",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                state=AlertmanagerSourceState.AUTO_TRACKED,
            ))
            discover_mock.return_value = inventory

            expected_path = self.output_dir / "health" / f"{self.run_id}-alertmanager-sources.json"
            write_mock.return_value = expected_path

            runner._run_alertmanager_discovery([mock_record], {"root": self.output_dir / "health"})

            # Verify write was called
            write_mock.assert_called_once()
            call_args = write_mock.call_args
            written_inventory = call_args[0][1]
            assert isinstance(written_inventory, AlertmanagerSourceInventory)
            assert len(written_inventory.sources) == 1

    def test_empty_inventory_writes_artifact(self) -> None:
        """Test that empty inventory still writes artifact with empty sources."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["test-context"],
            quiet=True,
            run_id=self.run_id,
        )

        metadata = ClusterSnapshotMetadata(
            cluster_id="test-id",
            captured_at=datetime.now(UTC),
            control_plane_version="1.28.0",
            node_count=3,
            pod_count=10,
        )

        mock_snapshot = MagicMock(spec=ClusterSnapshot)
        mock_snapshot.metadata = metadata

        target = HealthTarget(
            context="test-context",
            label="test-cluster",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="test-class",
            cluster_role="test-role",
            baseline_cohort="test-cohort",
        )

        mock_record = HealthSnapshotRecord(
            target=target,
            snapshot=mock_snapshot,
            path=self.output_dir / "health" / "snapshots" / "test.json",
            baseline_policy=BaselinePolicy.empty(),
        )

        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers", return_value=AlertmanagerSourceInventory()), \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources") as write_mock:

            expected_path = self.output_dir / "health" / f"{self.run_id}-alertmanager-sources.json"
            write_mock.return_value = expected_path

            runner._run_alertmanager_discovery([mock_record], {"root": self.output_dir / "health"})

            # Verify write was called with empty inventory
            write_mock.assert_called_once()
            call_args = write_mock.call_args
            written_inventory = call_args[0][1]
            assert isinstance(written_inventory, AlertmanagerSourceInventory)
            assert len(written_inventory.sources) == 0


class TestHealthLoopAllClustersTaggedWithClusterLabel(unittest.TestCase):
    """Regression: First cluster's sources must also get cluster_label tagged."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.output_dir = self.tmpdir / "runs"
        self.output_dir.mkdir(parents=True)

        # Write empty baseline policy
        baseline_path = self.tmpdir / "baseline.json"
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

        # Create minimal config
        config_data = {
            "run_label": "test-run",
            "output_dir": str(self.output_dir),
            "collector_version": "test",
            "targets": [
                {
                    "context": "test-context",
                    "label": "test-cluster",
                    "monitor_health": True,
                    "watched_helm_releases": [],
                    "watched_crd_families": [],
                    "cluster_class": "test-class",
                    "cluster_role": "test-role",
                    "baseline_cohort": "test-cohort",
                    "baseline_policy_path": "baseline.json",
                }
            ],
            "peer_mappings": [],
            "comparison_triggers": {},
            "baseline_policy_path": "baseline.json",
        }

        config_path = self.tmpdir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        self.config = HealthRunConfig.load(config_path)
        self.run_id = "test-run-123"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_all_clusters_tagged_with_cluster_label_including_first(self) -> None:
        """Regression: First cluster's sources must also get cluster_label tagged.

        Previously, the code only injected cluster_label in the else branch
        (when aggregated_inventory was not None). For the first cluster,
        aggregated_inventory was set directly from discovered_inventory without
        tagging, so first-cluster sources kept cluster_label=None.

        This test verifies that ALL clusters (first and subsequent) have
        cluster_label correctly injected for per-cluster UI filtering.
        """
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["cluster-alpha", "cluster-beta"],
            quiet=True,
            run_id=self.run_id,
        )

        # Create two mock records for different clusters
        records = []
        for ctx, lbl in [("cluster-alpha", "cluster-alpha"), ("cluster-beta", "cluster-beta")]:
            metadata = ClusterSnapshotMetadata(
                cluster_id=f"{lbl}-id",
                captured_at=datetime.now(UTC),
                control_plane_version="1.28.0",
                node_count=3,
                pod_count=10,
            )

            mock_snapshot = MagicMock(spec=ClusterSnapshot)
            mock_snapshot.metadata = metadata

            target = HealthTarget(
                context=ctx,
                label=lbl,
                monitor_health=True,
                watched_helm_releases=(),
                watched_crd_families=(),
                cluster_class="test-class",
                cluster_role="test-role",
                baseline_cohort="test-cohort",
            )

            records.append(HealthSnapshotRecord(
                target=target,
                snapshot=mock_snapshot,
                path=self.output_dir / "health" / "snapshots" / f"{lbl}.json",
                baseline_policy=BaselinePolicy.empty(),
            ))

        # Mock discovery to return one source per cluster
        def mock_discover(context: str, cluster_uid: str | None = None) -> AlertmanagerSourceInventory:
            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id=f"{context}:am",
                endpoint=f"http://alertmanager-{context}:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                cluster_label=context,
                cluster_uid=cluster_uid,
            ))
            return inventory

        from typing import Any
        captured_inventory: dict[str, AlertmanagerSourceInventory | None] = {"inv": None}

        def capture_write(*args: Any, **kwargs: Any) -> Path:
            captured_inventory["inv"] = args[1] if len(args) > 1 else kwargs.get("inventory")
            return self.output_dir / "health" / f"{self.run_id}-alertmanager-sources.json"

        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers", side_effect=mock_discover), \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources", side_effect=capture_write):

            runner._run_alertmanager_discovery(records, {"root": self.output_dir / "health"})

            # Verify the written inventory has 2 sources
            assert captured_inventory["inv"] is not None, "Inventory was not captured"
            sources = list(captured_inventory["inv"].sources.values())
            assert len(sources) == 2, f"Expected 2 sources, got {len(sources)}"

            # Critical assertion: ALL sources must have cluster_label set
            for source in sources:
                assert source.cluster_label is not None, (
                    f"Source {source.source_id} has cluster_label=None! "
                    "First cluster sources must also be tagged."
                )

            # Verify both cluster labels are present
            cluster_labels = {source.cluster_label for source in sources}
            assert cluster_labels == {"cluster-alpha", "cluster-beta"}, (
                f"Expected cluster labels {{'cluster-alpha', 'cluster-beta'}}, "
                f"got {cluster_labels}"
            )

            # Verify each source has the correct cluster label matching its source_id
            for source in sources:
                expected_cluster = source.source_id.split(":")[0]
                assert source.cluster_label == expected_cluster, (
                    f"Source {source.source_id} has cluster_label={source.cluster_label}, "
                    f"expected {expected_cluster}"
                )
