"""Tests for Alertmanager discovery integration in HealthLoopRunner.

Tests cover:
- Discovery invocation from the run pipeline
- Writing {run_id}-alertmanager-sources.json artifact
- Non-fatal behavior when discovery fails
- Empty-inventory artifact behavior
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
    AlertmanagerSourceState,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.loop import (
    HealthLoopRunner,
    HealthRunConfig,
    HealthSnapshotRecord,
    HealthTarget,
)


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


class TestHealthLoopAlertmanagerDiscovery(unittest.TestCase):
    """Tests for Alertmanager discovery in HealthLoopRunner."""

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

    def test_discovery_method_called(self) -> None:
        """Test that Alertmanager discovery method is called with correct parameters."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["test-context"],
            quiet=True,
            run_id=self.run_id,
        )
        
        # Create a minimal mock record that won't fail in _build_assessments
        metadata = ClusterSnapshotMetadata(
            cluster_id="test-id",
            captured_at=datetime.now(UTC),
            control_plane_version="1.28.0",
            node_count=3,
            pod_count=10,
        )
        
        # Create a more complete mock snapshot
        mock_snapshot = MagicMock(spec=ClusterSnapshot)
        mock_snapshot.metadata = metadata
        mock_snapshot.health_signals = MagicMock()
        mock_snapshot.health_signals.pod_counts = MagicMock()
        mock_snapshot.health_signals.pod_counts.image_pull_backoff = 0
        mock_snapshot.health_signals.warning_events = []
        
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
        
        # Track whether discovery was called
        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers") as discover_mock, \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources") as write_mock:
            
            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id="test:am",
                endpoint="http://alertmanager:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            ))
            discover_mock.return_value = inventory
            write_mock.return_value = self.output_dir / "health" / f"{self.run_id}-alertmanager-sources.json"
            
            # Call the discovery method directly to verify it works
            runner._run_alertmanager_discovery([mock_record], {"root": self.output_dir / "health"})
        
        # Verify discovery was called once
        discover_mock.assert_called_once()

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

    def test_aggregates_sources_across_multiple_targets(self) -> None:
        """Test that sources from multiple cluster targets are aggregated."""
        runner = HealthLoopRunner(
            config=self.config,
            available_contexts=["cluster-1", "cluster-2"],
            quiet=True,
            run_id=self.run_id,
        )
        
        # Create two mock records
        records = []
        for ctx, lbl in [("cluster-1", "cluster-1"), ("cluster-2", "cluster-2")]:
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
        
        def mock_discover(context: str, cluster_uid: str | None = None) -> AlertmanagerSourceInventory:
            inventory = AlertmanagerSourceInventory()
            inventory.add_source(AlertmanagerSource(
                source_id=f"{context}:am",
                endpoint=f"http://alertmanager-{context}:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
                cluster_uid=cluster_uid,
            ))
            return inventory
        
        with patch("k8s_diag_agent.health.loop_alertmanager_discovery.discover_alertmanagers", side_effect=mock_discover) as discover_mock, \
             patch("k8s_diag_agent.health.loop_alertmanager_discovery.write_alertmanager_sources") as write_mock:
            
            runner._run_alertmanager_discovery(records, {"root": self.output_dir / "health"})
            
            # Verify discovery was called twice (once per target)
            assert discover_mock.call_count == 2
            
            # Verify write was called with aggregated inventory
            write_mock.assert_called_once()
            call_args = write_mock.call_args
            written_inventory = call_args[0][1]
            assert isinstance(written_inventory, AlertmanagerSourceInventory)
            assert len(written_inventory.sources) == 2

    def test_verification_step_skipped_for_performance(self) -> None:
        """Test that verification is intentionally skipped to keep discovery fast.
        
        Note: verify_and_update_inventory is not imported in loop.py, so we can't
        patch it there. This test verifies that the code path doesn't call any
        verification function by checking that the inventory state remains DISCOVERED.
        """
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
        
        captured_inventory: dict[str, AlertmanagerSourceInventory | None] = {"inv": None}
        
        def capture_write(*args: Any, **kwargs: Any) -> Path:
            captured_inventory["inv"] = cast(
                AlertmanagerSourceInventory | None,
                args[1] if len(args) > 1 else kwargs.get("inventory")
            )
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

    def test_write_failure_logged_but_non_fatal(self) -> None:
        """Test that write failures are logged but don't stop the run."""
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


class TestHealthLoopRegistryCountingWithoutContainerLevelClusterLabel:
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
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock, patch
        
        from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot, ClusterSnapshotMetadata
        from k8s_diag_agent.external_analysis.alertmanager_discovery import (
            AlertmanagerSource,
            AlertmanagerSourceInventory,
            AlertmanagerSourceOrigin,
        )
        from k8s_diag_agent.external_analysis.alertmanager_source_registry import (
            AlertmanagerSourceRegistry,
            RegistryDesiredState,
            RegistryEntry,
            read_source_registry,
            write_source_registry,
        )
        from k8s_diag_agent.health.baseline import BaselinePolicy
        from k8s_diag_agent.health.loop import (
            HealthLoopRunner,
            HealthRunConfig,
            HealthSnapshotRecord,
            HealthTarget,
        )
        
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
            
            # Mock discovery to return our inventory
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


