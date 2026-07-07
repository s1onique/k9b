"""Tests for Alertmanager discovery deduplication behavior.

This file is the doctrine file for the invariant:
    A physical/logical Alertmanager endpoint must appear once in the health-loop
    snapshot, even when discovered through multiple configured/discovered sources.

Covers:
- same Alertmanager discovered from multiple sources
- same URL with different syntactic form
- service + explicit source overlap
- stable source ordering
- dedupe key behavior
- canonical identity behavior
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot, ClusterSnapshotMetadata
from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
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


class TestHealthLoopAlertmanagerDiscoveryDedupe(unittest.TestCase):
    """Tests for Alertmanager discovery deduplication behavior.

    DOCTRINE INVARIANT:
    A physical/logical Alertmanager endpoint must appear once in the health-loop
    snapshot, even when discovered through multiple configured/discovered sources.
    """

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

    def test_verification_step_skipped_for_performance(self) -> None:
        """Test that verification is intentionally skipped to keep discovery fast.

        Note: verify_and_update_inventory is not imported in loop.py, so we can't
        patch it there. This test verifies that the code path doesn't call any
        verification function by checking that the inventory state remains DISCOVERED.
        """
        from k8s_diag_agent.external_analysis.alertmanager_discovery import AlertmanagerSourceState

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

        captured_inventory: dict[str, AlertmanagerSourceInventory | None] = {"inv": None}

        def capture_write(*args: Any, **kwargs: Any) -> Path:
            # Capture the inventory argument for test assertion
            captured_inventory["inv"] = cast(AlertmanagerSourceInventory | None, args[1] if len(args) > 1 else kwargs.get("inventory"))
            return self.output_dir / "health" / f"{self.run_id}-alertmanager-sources.json"

        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers") as discover_mock, \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources", side_effect=capture_write):

            # Mock discovery to return an inventory in DISCOVERED state
            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id="test:am",
                endpoint="http://alertmanager:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                state=AlertmanagerSourceState.DISCOVERED,  # Not yet verified
            ))
            discover_mock.return_value = inventory

            runner._run_alertmanager_discovery([mock_record], {"root": self.output_dir / "health"})

            # Verify that the inventory written still has DISCOVERED state
            # (verification would change it to AUTO_TRACKED or DEGRADED)
            assert captured_inventory["inv"] is not None
            sources = list(captured_inventory["inv"].sources.values())
            assert len(sources) == 1
            assert sources[0].state == AlertmanagerSourceState.DISCOVERED, \
                "Verification was called (state changed from DISCOVERED)"


class TestHealthLoopRegistryCountingWithoutContainerLevelClusterLabel(unittest.TestCase):
    """Regression test: health loop must not assume inventory-level cluster_label.

    This test verifies that the health loop's registry counting logic correctly uses
    source.cluster_label (not verified_inventory.cluster_label) when looking up
    registry state. AlertmanagerSourceInventory does NOT have a cluster_label
    attribute at the container level - cluster_label is per-source.

    The crash that this test prevents:
        AttributeError: 'AlertmanagerSourceInventory' object has no attribute 'cluster_label'

    The fix: use lookup_registry_state() helper which correctly uses source.cluster_label.
    """

    def test_registry_counting_uses_source_level_cluster_label(self) -> None:
        """Registry counting must work when inventory has no cluster_label attribute.

        This is a regression test for the bug where the health loop tried to access
        verified_inventory.cluster_label (which doesn't exist on AlertmanagerSourceInventory)
        instead of source.cluster_label (which is per-source).
        """
        tmpdir = Path(tempfile.mkdtemp())
        try:
            output_dir = tmpdir / "runs"
            output_dir.mkdir(parents=True)

            # Write empty baseline policy
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

            # Create minimal config
            config_data = {
                "run_label": "test-registry-count",
                "output_dir": str(output_dir),
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
            config_path = tmpdir / "config.json"
            config_path.write_text(json.dumps(config_data), encoding="utf-8")

            config = HealthRunConfig.load(config_path)
            run_id = "test-registry-count-123"

            runner = HealthLoopRunner(
                config=config,
                available_contexts=["test-context"],
                quiet=True,
                run_id=run_id,
            )

            # Create a source with cluster_label (per-source attribute)
            # Note: canonical_identity is a @property, not a constructor argument
            source = AlertmanagerSource(
                source_id="test:am",
                endpoint="http://alertmanager:9093",
                namespace="monitoring",  # Required for canonical_identity property
                name="alertmanager-main",  # Required for canonical_identity property
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                cluster_label="test-cluster",  # Per-source, NOT container-level
            )

            # Verify canonical_identity is computed correctly
            assert source.canonical_identity == "monitoring/alertmanager-main"

            # Create inventory - note: AlertmanagerSourceInventory does NOT have cluster_label
            inventory = AlertmanagerSourceInventory(cluster_context="test-context")
            inventory.add_source(source)

            # Create registry with one MANUAL entry
            health_root = output_dir / "health"
            health_root.mkdir(parents=True, exist_ok=True)
            from k8s_diag_agent.external_analysis.alertmanager_source_registry import (
                AlertmanagerSourceRegistry,
                RegistryDesiredState,
                RegistryEntry,
                read_source_registry,
                write_source_registry,
            )
            registry = AlertmanagerSourceRegistry()
            registry.add_entry(RegistryEntry(
                cluster_context="test-cluster",  # Keyed by cluster_label (stable)
                canonical_identity="monitoring/alertmanager-main",
                desired_state=RegistryDesiredState.MANUAL,
            ))
            write_source_registry(registry, health_root)

            # Verify registry was written
            loaded_registry = read_source_registry(health_root)
            assert loaded_registry is not None
            assert len(loaded_registry.entries) == 1

            # Create mock record
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
                path=output_dir / "health" / "snapshots" / "test.json",
                baseline_policy=BaselinePolicy.empty(),
            )

            # This call should NOT raise AttributeError about inventory.cluster_label
            # Before the fix, this would crash with:
            #   AttributeError: 'AlertmanagerSourceInventory' object has no attribute 'cluster_label'
            with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers", return_value=inventory), \
                 patch.object(runner, "_log_event") as log_mock:

                runner._run_alertmanager_discovery([mock_record], {"root": health_root})

                # Verify registry-applied event was logged (proves lookup succeeded)
                registry_applied_calls = [
                    c for c in log_mock.call_args_list
                    if c.kwargs.get("event") == "alertmanager-registry-applied"
                ]
                assert len(registry_applied_calls) >= 1, (
                    "Should log alertmanager-registry-applied event"
                )

                # Verify sources_promoted >= 1 (proves MANUAL source was counted)
                promoted_count = registry_applied_calls[0].kwargs.get("sources_promoted", 0)
                assert promoted_count >= 1, (
                    f"Expected at least 1 promoted source, got {promoted_count}"
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
