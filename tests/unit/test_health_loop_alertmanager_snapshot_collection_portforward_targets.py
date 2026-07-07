"""Target derivation tests for _run_alertmanager_snapshot_collection.

Tests that port-forward targets are derived from endpoint host, not source name.
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


class TestAlertmanagerSnapshotCollectionTargetDerivation:
    """Tests for port-forward target derivation in alertmanager snapshot collection."""

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

    def test_snapshot_collection_derives_port_forward_target_from_endpoint_host(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Port-forward target is derived from endpoint host DNS, not source name.

        Real Prometheus Operator case:
        - Alertmanager CR name: kube-prometheus-stack-alertmanager
        - Service DNS in endpoint: alertmanager-operated.monitoring:9093
        - Port-forward should target: svc/alertmanager-operated (from endpoint host)
        - NOT: svc/kube-prometheus-stack-alertmanager (which would fail)
        """
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://alertmanager-operated.monitoring:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
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

        with patch("urllib.request.urlopen", side_effect=urlopen_mock):
            with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
                with patch.object(runner, "_choose_free_local_port", return_value=18457):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "svc/alertmanager-operated" in call_args, (
            f"Port-forward should target alertmanager-operated (from endpoint), "
            f"not kube-prometheus-stack-alertmanager (from name). Got: {call_args}"
        )
        assert "svc/kube-prometheus-stack-alertmanager" not in call_args, (
            f"Port-forward should NOT use source.name. Got: {call_args}"
        )
        assert "-n" in call_args
        assert "monitoring" in call_args

        assert len(called_urls) == 1
        assert "127.0.0.1:18457" in called_urls[0]
        assert "/api/v2/alerts" in called_urls[0]

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        mock_process.terminate.assert_called_once()

    def test_snapshot_collection_endpoint_with_longer_fqdn(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Port-forward target is correctly derived from multi-part FQDN."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="default/main-alertmanager",
            endpoint="http://am-cluster-0.monitoring.svc.cluster.local:9093",
            namespace="monitoring",
            name="main-alertmanager",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        kubectl_cmds: list[list[str]] = []

        def capture_popen(*args: object, **kwargs: object) -> MagicMock:
            if args and args[0]:
                kubectl_cmds.append(list(args[0]))  # type: ignore[call-overload]
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stderr = MagicMock()
            mock_process.stderr.read.return_value = "Forwarding from 127.0.0.1:20000 -> 9093\n"
            return mock_process

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("subprocess.Popen", side_effect=capture_popen):
                with patch.object(runner, "_choose_free_local_port", return_value=20000):
                    with patch.object(runner, "_wait_for_port_ready", return_value=True):
                        runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        assert len(kubectl_cmds) == 1
        cmd = kubectl_cmds[0]
        assert "svc/am-cluster-0" in cmd, f"Expected svc/am-cluster-0, got: {cmd}"
        assert "svc/main-alertmanager" not in cmd
