"""Basic port-forward tests for _run_alertmanager_snapshot_collection.

Tests port-forward behavior, endpoint handling, and localhost bypass.
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


class TestAlertmanagerSnapshotCollectionPortForwardBasic:
    """Basic port-forward tests for alertmanager snapshot collection."""

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

    def test_snapshot_collection_uses_port_forward_for_cluster_internal_endpoint(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection uses port-forward when endpoint is cluster-internal DNS."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="monitoring/alertmanager-operated",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="alertmanager-operated",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        called_urls: list[str] = []

        def urlopen_mock(*args: object, **kwargs: object) -> MagicMock:
            request = args[0] if args else None
            if hasattr(request, "full_url"):
                called_urls.append(request.full_url)
            elif hasattr(request, "get_full_url"):
                called_urls.append(request.get_full_url())
            else:
                called_urls.append(str(request))
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps([]).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Forwarding from 127.0.0.1:18457 -> 9093\n"
        mock_process.stdout = MagicMock()
        mock_process.stdout.read.return_value = ""

        with patch("urllib.request.urlopen", side_effect=urlopen_mock):
            with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "kubectl" in call_args
        assert "port-forward" in call_args
        assert "-n" in call_args
        assert "monitoring" in call_args
        assert "svc/alertmanager-operated" in call_args

        assert len(called_urls) == 1
        assert "127.0.0.1:18457" in called_urls[0]
        assert "/api/v2/alerts" in called_urls[0]

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        mock_process.terminate.assert_called_once()

    def test_snapshot_collection_port_forward_success_writes_artifacts(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Successful port-forward + fetch writes snapshot and compact artifacts."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="monitoring/alertmanager-main",
            endpoint="http://alertmanager-main.Monitoring:9093",
            namespace="monitoring",
            name="alertmanager-main",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = "Forwarding from 127.0.0.1:21543 -> 9093\n"

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
            with patch("subprocess.Popen", return_value=mock_process):
                with patch.object(runner, "_choose_free_local_port", return_value=21543):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        compact_files = list(temp_dir.glob("*-alertmanager-compact.json"))
        assert len(compact_files) == 1

        mock_process.terminate.assert_called_once()

    def test_snapshot_collection_skips_port_forward_for_localhost(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection skips port-forward for localhost endpoint."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="manual-localhost",
            endpoint="http://localhost:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        called_urls: list[str] = []

        def urlopen_mock(*args: object, **kwargs: object) -> MagicMock:
            request = args[0] if args else None
            if hasattr(request, "full_url"):
                called_urls.append(request.full_url)
            elif hasattr(request, "get_full_url"):
                called_urls.append(request.get_full_url())
            else:
                called_urls.append(str(request))
            mock_response = MagicMock()
            mock_response.read.return_value = json.dumps([]).encode()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response

        with patch("urllib.request.urlopen", side_effect=urlopen_mock):
            with patch("subprocess.Popen") as mock_popen:
                runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        mock_popen.assert_not_called()

        assert len(called_urls) == 1
        assert "localhost:9093" in called_urls[0]

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1
