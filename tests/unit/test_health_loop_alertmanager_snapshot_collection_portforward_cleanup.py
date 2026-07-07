"""Cleanup tests for _run_alertmanager_snapshot_collection.

Tests that port-forward cleanup runs on success and failure paths.
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


class TestAlertmanagerSnapshotCollectionCleanup:
    """Tests for port-forward cleanup in alertmanager snapshot collection."""

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

    def _make_pf_inventory(self, endpoint: str) -> AlertmanagerSourceInventory:
        """Create inventory with a port-forward eligible source."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="monitoring/alertmanager-operated",
            endpoint=endpoint,
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        return inventory

    def _make_mock_process(self, stderr_output: str = "Forwarding from 127.0.0.1:18457 -> 9093\n") -> MagicMock:
        """Create a mock port-forward process."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = stderr_output
        return mock_process

    def test_snapshot_collection_port_forward_startup_failure_non_fatal(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Port-forward startup failure is non-fatal and writes error snapshot."""
        runner._alertmanager_inventory = self._make_pf_inventory(
            "http://alertmanager-operated.monitoring:9093"
        )

        mock_process = MagicMock()
        mock_process.poll.return_value = 1
        mock_process.returncode = 1
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "error: could not find port"
        mock_process.stdout = MagicMock()
        mock_process.stdout.read.return_value = ""
        mock_process.kill = MagicMock()

        with patch("subprocess.Popen", return_value=mock_process):
            with patch.object(runner, "_choose_free_local_port", return_value=18457):
                with patch.object(runner, "_wait_for_port_ready", side_effect=RuntimeError("port forward failed")):
                    runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"

    def test_snapshot_collection_fetch_failure_after_port_forward_cleans_up(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Fetch failure after successful port-forward is non-fatal and still cleans up."""
        runner._alertmanager_inventory = self._make_pf_inventory(
            "http://alertmanager-operated.monitoring:9093"
        )

        mock_process = self._make_mock_process()

        import urllib.error
        fetch_error = urllib.error.URLError("Connection reset by peer")

        with patch("urllib.request.urlopen", side_effect=fetch_error):
            with patch("subprocess.Popen", return_value=mock_process):
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"

        mock_process.terminate.assert_called_once()

    def test_snapshot_collection_cleanup_runs_on_success(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Cleanup runs in success path."""
        runner._alertmanager_inventory = self._make_pf_inventory(
            "http://alertmanager-operated.monitoring:9093"
        )

        mock_process = self._make_mock_process()

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("subprocess.Popen", return_value=mock_process):
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        mock_process.terminate.assert_called_once()

    def test_snapshot_collection_cleanup_runs_on_failure(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Cleanup runs in failure path."""
        runner._alertmanager_inventory = self._make_pf_inventory(
            "http://alertmanager-operated.monitoring:9093"
        )

        mock_process = self._make_mock_process()

        def write_with_error(*args: object, **kwargs: object) -> None:
            raise OSError("Disk full")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "success",
            "data": {"alerts": []}
        }).encode("utf-8")
        mock_urlopen = MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("urllib.request.urlopen", mock_urlopen):
            with patch("subprocess.Popen", return_value=mock_process):
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        with patch(
                            "k8s_diag_agent.health.loop_alertmanager_snapshot_collection.write_alertmanager_artifacts",
                            side_effect=write_with_error
                        ):
                            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        mock_process.terminate.assert_called_once()
