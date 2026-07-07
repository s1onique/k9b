"""Cluster attribution tests for _run_alertmanager_snapshot_collection.

Tests cluster label attribution in compact artifacts.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig, HealthTarget


class TestAlertmanagerSnapshotClusterAttribution:
    """Regression tests for cluster attribution in compact artifacts."""

    @pytest.fixture
    def temp_dir(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def minimal_config(self, temp_dir: Path) -> HealthRunConfig:
        target = HealthTarget(
            context="test-cluster",
            label="test-cluster",
            monitor_health=True,
            watched_helm_releases=(),
            watched_crd_families=(),
            cluster_class="production",
            cluster_role="primary",
            baseline_cohort="test",
        )
        return HealthRunConfig(
            run_label="test-run",
            output_dir=temp_dir,
            collector_version="test",
            targets=(target,),
            peers=(),
            trigger_policy=MagicMock(
                control_plane_version=False,
                watched_helm_release=False,
                watched_crd=False,
                health_regression=False,
                missing_evidence=False,
                manual=False,
            ),
            manual_pairs=(),
            baseline_policy=MagicMock(),
        )

    @pytest.fixture
    def runner(self, minimal_config: HealthRunConfig) -> HealthLoopRunner:
        return HealthLoopRunner(
            config=minimal_config,
            available_contexts=["test-cluster"],
            quiet=True,
        )

    def test_compact_uses_cluster_label_when_alerts_lack_cluster(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Compact artifact uses selected_source.cluster_label for cluster attribution.

        This is a regression test for the fix where:
        - alerts without cluster labels should use cluster_label from the selected source
        - affected_clusters should include the cluster_label
        - by_cluster should contain an entry for the cluster_label
        """
        inventory = AlertmanagerSourceInventory()

        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
            cluster_label="cluster1",
            namespace="monitoring",
            name="alertmanager",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        alerts = [
            {
                "labels": {
                    "alertname": "HighMemoryUsage",
                    "severity": "warning",
                    "namespace": "default",
                },
                "annotations": {"summary": "Memory usage is high"},
                "startsAt": "2024-01-01T00:00:00Z",
            },
            {
                "labels": {
                    "alertname": "PodCrashLooping",
                    "severity": "critical",
                    "namespace": "kube-system",
                },
                "annotations": {"summary": "Pod is crash looping"},
                "startsAt": "2024-01-01T00:01:00Z",
            },
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(alerts).encode()

        def urlopen_mock(*args: object, **kwargs: object) -> MagicMock:
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=urlopen_mock):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        compact_files = list(temp_dir.glob("*-alertmanager-compact.json"))
        assert len(compact_files) == 1, f"Expected 1 compact file, found: {list(temp_dir.glob('*.json'))}"

        compact_content = json.loads(compact_files[0].read_text())

        assert "affected_clusters" in compact_content
        affected_clusters = compact_content["affected_clusters"]
        assert "cluster1" in affected_clusters, (
            f"Expected 'cluster1' in affected_clusters, got: {affected_clusters}. "
            "The cluster_label from selected_source should be used when alerts lack cluster labels."
        )

        assert "by_cluster" in compact_content
        by_cluster = compact_content["by_cluster"]
        assert len(by_cluster) > 0, (
            f"Expected non-empty by_cluster when cluster_label is provided, got: {by_cluster}"
        )

        cluster1_entry = None
        for entry in by_cluster:
            if entry.get("cluster") == "cluster1":
                cluster1_entry = entry
                break

        assert cluster1_entry is not None, (
            f"Expected by_cluster to contain entry for 'cluster1', got: {by_cluster}"
        )

        assert cluster1_entry.get("alert_count") == 2, (
            f"Expected 2 alerts in cluster1, got: {cluster1_entry.get('alert_count')}"
        )

    def test_snapshot_source_provenance(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot artifact includes source endpoint for provenance tracking."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://alertmanager.monitoring.svc:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
            cluster_label="cluster1",
            namespace="monitoring",
            name="alertmanager",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()

        def urlopen_mock(*args: object, **kwargs: object) -> MagicMock:
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        with patch("urllib.request.urlopen", side_effect=urlopen_mock):
            with patch("subprocess.Popen", return_value=mock_process):
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        snapshot_content = json.loads(snapshot_files[0].read_text())

        assert "source" in snapshot_content
        assert snapshot_content["source"] == "http://alertmanager.monitoring.svc:9093", (
            f"Expected source to be the endpoint URL, got: {snapshot_content.get('source')}"
        )
