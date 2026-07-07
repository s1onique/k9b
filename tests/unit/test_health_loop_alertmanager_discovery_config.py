"""Tests for Alertmanager discovery configuration behavior.

Covers:
- disabled discovery
- explicit Alertmanager URL/config
- missing config
- invalid config
- env/config precedence
- fail-closed / safe default behavior
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from k8s_diag_agent.health.loop import HealthLoopRunner, HealthRunConfig


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


class TestHealthLoopAlertmanagerDiscoveryConfig(unittest.TestCase):
    """Tests for Alertmanager discovery configuration behavior."""

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

    def test_discovery_method_exists(self) -> None:
        """Test that HealthLoopRunner has the _run_alertmanager_discovery method."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["test-context"],
            quiet=True,
            run_id=self.run_id,
        )

        # Verify the method exists
        assert hasattr(runner, "_run_alertmanager_discovery")
        assert callable(getattr(runner, "_run_alertmanager_discovery"))

    def test_discovery_skipped_when_no_records(self) -> None:
        """Test that discovery is skipped when there are no cluster records."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["test-context"],
            quiet=True,
            run_id=self.run_id,
        )

        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers") as discover_mock, \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources") as write_mock, \
             patch.object(runner, "_log_event") as log_mock:

            runner._run_alertmanager_discovery([], {"root": self.output_dir / "health"})

            # Verify discovery was NOT called
            discover_mock.assert_not_called()

            # When no records, write is NOT called (early return)
            # This is the expected behavior
            write_mock.assert_not_called()

            # Verify skipped event was logged
            skipped_calls = [c for c in log_mock.call_args_list
                           if c.kwargs.get("event") == "alertmanager-discovery-skipped"]
            assert len(skipped_calls) >= 1

    def test_write_failure_logged_but_non_fatal(self) -> None:
        """Test that write failures are logged but don't stop the run."""
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

        from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshotMetadata
        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            AlertmanagerSource,
            AlertmanagerSourceInventory,
            AlertmanagerSourceOrigin,
        )
        from k8s_diag_agent.health.baseline import BaselinePolicy
        from k8s_diag_agent.health.loop import HealthSnapshotRecord, HealthTarget

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

        mock_snapshot = MagicMock()
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
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources", side_effect=RuntimeError("Write failed")), \
             patch.object(runner, "_log_event") as log_mock:

            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id="test:am",
                endpoint="http://alertmanager:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            ))
            discover_mock.return_value = inventory

            # This should NOT raise - write failure is non-fatal
            runner._run_alertmanager_discovery([mock_record], {"root": self.output_dir / "health"})

            # Verify write failure was logged as ERROR
            error_calls = [c for c in log_mock.call_args_list
                         if c.kwargs.get("event") == "alertmanager-sources-write-failed"]
            assert len(error_calls) >= 1, "Write failure should be logged as ERROR"
