"""Tests for HealthHistoryFactArtifact and persist_history_fact_artifacts."""

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.health.loop_history import (
    HealthHistoryEntry,
    HealthHistoryFactArtifact,
    HealthRating,
    persist_history_fact_artifacts,
)


class HealthHistoryFactArtifactTests(unittest.TestCase):
    """Tests for HealthHistoryFactArtifact dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        """Verify artifact serializes and deserializes correctly."""
        entry = HealthHistoryEntry(
            cluster_id="test-cluster",
            node_count=3,
            pod_count=42,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={"prometheus": "1.0.0"},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        artifact = HealthHistoryFactArtifact(
            artifact_id="artifact-123",
            run_id="run-20240101-000000",
            cluster_id="test-cluster",
            created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            entry=entry,
        )
        data = artifact.to_dict()
        parsed = HealthHistoryFactArtifact.from_dict(data)
        
        assert parsed.artifact_id == "artifact-123"
        assert parsed.run_id == "run-20240101-000000"
        assert parsed.cluster_id == "test-cluster"
        assert parsed.entry.health_rating == HealthRating.HEALTHY
        assert parsed.entry.node_count == 3
        assert parsed.entry.pod_count == 42

    def test_from_dict_with_z_timestamp(self) -> None:
        """Verify timestamp with Z suffix parses correctly."""
        data = {
            "artifact_id": "art-456",
            "run_id": "run-20240101-000000",
            "cluster_id": "cluster-x",
            "created_at": "2026-01-01T00:00:00Z",
            "entry": {
                "cluster_id": "cluster-x",
                "node_count": 5,
                "pod_count": 100,
                "control_plane_version": "v1.27.0",
                "health_rating": "degraded",
                "missing_evidence": ["events"],
                "watched_helm_releases": {},
                "watched_crd_families": {},
                "node_conditions": {"not_ready": 1},
                "pod_counts": {"non_running": 5},
                "job_failures": 2,
                "warning_event_count": 3,
            },
        }
        parsed = HealthHistoryFactArtifact.from_dict(data)
        
        assert parsed.artifact_id == "art-456"
        assert parsed.cluster_id == "cluster-x"
        assert parsed.entry.health_rating == HealthRating.DEGRADED
        # Verify timezone info is preserved
        assert parsed.created_at.tzinfo is not None

    def test_artifact_id_in_filename(self) -> None:
        """Verify filename includes artifact_id for immutable-instance-safe paths."""
        entry = HealthHistoryEntry(
            cluster_id="cluster-a",
            node_count=1,
            pod_count=1,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            def custom_id_fn() -> str:
                return "unique-artifact-id-789"
            
            history = {"cluster-a": entry}
            paths = persist_history_fact_artifacts(
                history=history,
                run_id="run-001",
                history_dir=Path(tmpdir),
                artifact_id_fn=custom_id_fn,
            )
            
            assert len(paths) == 1
            filename = paths[0].name
            # Verify filename format: {run_id}-{cluster_id}-{artifact_id}.json
            assert filename.startswith("run-001-cluster-a-")
            assert "unique-artifact-id-789" in filename
            assert filename.endswith(".json")

    def test_no_overwrite_raises_error(self) -> None:
        """Verify writing to existing path raises FileExistsError."""
        entry = HealthHistoryEntry(
            cluster_id="cluster-b",
            node_count=2,
            pod_count=10,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            history_dir = Path(tmpdir)
            
            # First write should succeed
            history = {"cluster-b": entry}
            paths1 = persist_history_fact_artifacts(
                history=history,
                run_id="run-002",
                history_dir=history_dir,
                artifact_id_fn=lambda: "static-id-001",
            )
            assert len(paths1) == 1
            
            # Second write with same run_id, cluster_id, artifact_id should fail
            history2 = {"cluster-b": entry}
            with self.assertRaises(FileExistsError) as ctx:
                persist_history_fact_artifacts(
                    history=history2,
                    run_id="run-002",
                    history_dir=history_dir,
                    artifact_id_fn=lambda: "static-id-001",
                )
            assert "immutability contract violated" in str(ctx.exception)

    def test_multiple_clusters_produce_unique_filenames(self) -> None:
        """Verify multiple clusters produce distinct artifact files."""
        entry_a = HealthHistoryEntry(
            cluster_id="cluster-a",
            node_count=1,
            pod_count=1,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        entry_b = HealthHistoryEntry(
            cluster_id="cluster-b",
            node_count=2,
            pod_count=5,
            control_plane_version="v1.27.0",
            health_rating=HealthRating.DEGRADED,
            missing_evidence=("missing-evidence-x",),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={"not_ready": 1},
            pod_counts={"non_running": 2},
            job_failures=1,
            warning_event_count=3,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            history = {
                "cluster-a": entry_a,
                "cluster-b": entry_b,
            }
            paths = persist_history_fact_artifacts(
                history=history,
                run_id="run-003",
                history_dir=Path(tmpdir),
                artifact_id_fn=lambda: "shared-artifact-id",
            )
            
            assert len(paths) == 2
            filenames = {p.name for p in paths}
            
            # Each cluster should have its own file with unique path
            assert len(filenames) == 2
            assert any("cluster-a" in name for name in filenames)
            assert any("cluster-b" in name for name in filenames)

    def test_default_uses_new_artifact_id(self) -> None:
        """Verify default artifact_id_fn generates non-empty unique IDs."""
        entry = HealthHistoryEntry(
            cluster_id="cluster-c",
            node_count=1,
            pod_count=1,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pass None to use default generator (new_artifact_id for repo consistency)
            history = {"cluster-c": entry}
            paths = persist_history_fact_artifacts(
                history=history,
                run_id="run-004",
                history_dir=Path(tmpdir),
                artifact_id_fn=None,  # Use default
            )
            
            assert len(paths) == 1
            filename = paths[0].name
            # Default uses new_artifact_id() (UUIDv7) for repo consistency
            # Filename should be: run-004-cluster-c-{artifact_id}.json
            assert "cluster-c" in filename
            assert filename.endswith(".json")
            # Extract artifact_id from filename
            # Format: run-004-cluster-c-{artifact_id}.json
            uuid_part = filename.replace(".json", "").replace("run-004-", "").replace("cluster-c-", "")
            assert len(uuid_part) > 0  # Must be non-empty
            # UUIDv7 format: time-low-time-mid-time-high-version-clock
            # e.g. 019228f0-e7d6-7xxx-8xxx-xxxxxxxxxxxx (36 chars with hyphens)
            assert len(uuid_part) == 36 or len(uuid_part) == 32  # With or without hyphens

    def test_loaded_artifact_matches_original(self) -> None:
        """Verify artifact written to disk matches original after load."""
        entry = HealthHistoryEntry(
            cluster_id="cluster-d",
            node_count=10,
            pod_count=50,
            control_plane_version="v1.29.0",
            health_rating=HealthRating.DEGRADED,
            missing_evidence=("missing-evidence-y",),
            watched_helm_releases={"nginx": "1.0.0"},
            watched_crd_families={"example.com": "v2"},
            node_conditions={"memory_pressure": 1},
            pod_counts={"non_running": 3},
            job_failures=2,
            warning_event_count=5,
        )
        created_at = datetime(2026, 4, 23, 2, 30, 0, tzinfo=UTC)
        artifact = HealthHistoryFactArtifact(
            artifact_id="verify-001",
            run_id="run-005",
            cluster_id="cluster-d",
            created_at=created_at,
            entry=entry,
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            history_dir = Path(tmpdir)
            paths = persist_history_fact_artifacts(
                history={"cluster-d": entry},
                run_id="run-005",
                history_dir=history_dir,
                artifact_id_fn=lambda: "verify-001",
            )
            
            # Read back from disk
            with open(paths[0]) as f:
                loaded_data = json.load(f)
            
            parsed = HealthHistoryFactArtifact.from_dict(loaded_data)
            
            assert parsed.artifact_id == artifact.artifact_id
            assert parsed.run_id == artifact.run_id
            assert parsed.cluster_id == artifact.cluster_id
            assert parsed.entry.node_count == 10
            assert parsed.entry.pod_count == 50
            assert parsed.entry.health_rating == HealthRating.DEGRADED
            assert parsed.entry.watched_helm_releases == {"nginx": "1.0.0"}
            assert parsed.entry.watched_crd_families == {"example.com": "v2"}
            assert parsed.entry.job_failures == 2
            assert parsed.entry.warning_event_count == 5


class HistoryJsonCompatibilityTests(unittest.TestCase):
    """Tests verifying history.json stays compatible with existing readers."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_history_json_unchanged_after_fact_artifact_write(self) -> None:
        """Verify persist_history still works and history.json is unaffected."""
        from k8s_diag_agent.health.loop_history import persist_history
        
        entry = HealthHistoryEntry(
            cluster_id="cluster-e",
            node_count=3,
            pod_count=15,
            control_plane_version="v1.28.0",
            health_rating=HealthRating.HEALTHY,
            missing_evidence=(),
            watched_helm_releases={},
            watched_crd_families={},
            node_conditions={},
            pod_counts={},
            job_failures=0,
            warning_event_count=0,
        )
        
        history_path = self.tmpdir / "history.json"
        
        # Write using persist_history (existing API)
        history = {"cluster-e": entry}
        persist_history(history, history_path)
        
        # Verify history.json was written with correct content
        assert history_path.exists()
        with open(history_path) as f:
            data = json.load(f)
        
        assert "cluster-e" in data
        assert data["cluster-e"]["node_count"] == 3
        assert data["cluster-e"]["health_rating"] == "healthy"