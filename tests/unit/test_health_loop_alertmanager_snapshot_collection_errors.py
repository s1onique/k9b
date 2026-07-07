"""Error handling tests for _run_alertmanager_snapshot_collection.

Tests HTTP errors, connection errors, and write failures.
"""

from __future__ import annotations

import json
import tempfile
import urllib.error
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


class TestAlertmanagerSnapshotCollectionErrors:
    """Test error handling in snapshot collection."""

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

    def _setup_inventory(
        self,
        runner: HealthLoopRunner,
        endpoint: str = "http://localhost:9093",
    ) -> None:
        """Set up inventory with a single MANUAL source."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint=endpoint,
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

    def test_snapshot_collection_handles_http_error(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection handles HTTP errors gracefully."""
        self._setup_inventory(runner)

        from http.client import HTTPMessage

        error = urllib.error.HTTPError(
            url="http://localhost:9093/api/v2/alerts",
            code=500,
            msg="Internal Server Error",
            hdrs=HTTPMessage(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=error):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"
        errors = content.get("errors", [])
        assert any("500" in str(e) for e in errors)

    def test_snapshot_collection_handles_connection_error(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection handles connection errors gracefully."""
        self._setup_inventory(runner)

        error = urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=error):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"
        errors = content.get("errors", [])
        assert any("unreachable" in str(e).lower() for e in errors)

    def test_snapshot_collection_handles_timeout_error(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection handles timeout errors gracefully."""
        self._setup_inventory(runner)

        error = urllib.error.URLError("timed out")

        with patch("urllib.request.urlopen", side_effect=error):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"

    def test_snapshot_collection_handles_404_error(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection handles 404 Not Found gracefully."""
        self._setup_inventory(runner)

        from http.client import HTTPMessage

        error = urllib.error.HTTPError(
            url="http://localhost:9093/api/v2/alerts",
            code=404,
            msg="Not Found",
            hdrs=HTTPMessage(),
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=error):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"
        errors = content.get("errors", [])
        assert any("404" in str(e) for e in errors)

    def test_snapshot_collection_handles_dns_resolution_failure(
        self,
        runner: HealthLoopRunner,
        temp_dir: Path,
    ) -> None:
        """Snapshot collection handles DNS resolution failures gracefully."""
        inventory = AlertmanagerSourceInventory()
        source = AlertmanagerSource(
            source_id="test-source",
            endpoint="http://nonexistent.cluster.local:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
            cluster_context="test-cluster",
            namespace="monitoring",
        )
        inventory.add_source(source)
        runner._alertmanager_inventory = inventory

        error = urllib.error.URLError("Name or service not known")

        with patch("urllib.request.urlopen", side_effect=error):
            runner._run_alertmanager_snapshot_collection({"root": temp_dir})

        snapshot_files = list(temp_dir.glob("*-alertmanager-snapshot.json"))
        assert len(snapshot_files) == 1

        content = json.loads(snapshot_files[0].read_text())
        assert content.get("status") == "upstream_error"
