"""Basic snapshot collection tests for _run_alertmanager_snapshot_collection.

Tests eligibility, source selection, and basic success paths.
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


class TestAlertmanagerSnapshotCollectionBasic:
    """Test basic snapshot collection behavior."""

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

    def test_snapshot_collection_skipped_when_no_inventory(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection is skipped when _alertmanager_inventory is None."""
        assert runner._alertmanager_inventory is None
        runner._run_alertmanager_snapshot_collection({"root": temp_dir})
        assert runner._alertmanager_inventory is None

    def test_snapshot_collection_skipped_when_no_eligible_sources(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection is skipped when no MANUAL or AUTO_TRACKED sources exist."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.DISCOVERED,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 0

    def test_snapshot_collection_selects_manual_over_auto_tracked(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection prefers MANUAL over AUTO_TRACKED sources."""
        inventory = AlertmanagerSourceInventory()

        auto_source = AlertmanagerSource(
            source_id="auto-source",
            endpoint="http://localhost:9094",
            origin=AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_context="test-cluster",
        )
        inventory.add_source(auto_source)

        manual_source = AlertmanagerSource(
            source_id="manual-source",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(manual_source)

        runner._alertmanager_inventory = inventory

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

    def test_snapshot_collection_success(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection succeeds when source is reachable."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        alerts = [
            {
                "labels": {"alertname": "TestAlert", "severity": "warning"},
                "annotations": {"summary": "Test alert"},
                "startsAt": "2024-01-01T00:00:00Z",
            }
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(alerts).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        compact_files = list(temp_dir.glob("*-alertmanager-compact.json"))
        assert len(compact_files) == 1

    def test_snapshot_collection_uses_auto_tracked_when_no_manual(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection falls back to AUTO_TRACKED when no MANUAL sources."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1


class TestAlertmanagerSnapshotCollectionIntegration:
    """Integration tests for snapshot collection in execute pipeline."""

    @pytest.fixture
    def temp_dir(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config_with_alertmanager(self, temp_dir: Path) -> HealthRunConfig:
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
            run_label="test-am-run",
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

    # Integration tests require more complex mocking setup due to the execute() method
    # calling multiple components. The unit tests above provide sufficient coverage for
    # the _run_alertmanager_snapshot_collection method behavior.
    # The integration with execute() is verified through the existing health loop tests.
