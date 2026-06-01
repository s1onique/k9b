"""Tests for health/artifact_readers.py - ClusterSnapshot typed readers.

This module tests the typed artifact reader boundary for ClusterSnapshot.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from k8s_diag_agent.collect.cluster_snapshot import ClusterSnapshot
from k8s_diag_agent.health.artifact_readers import (
    read_cluster_snapshot_artifact,
    try_read_cluster_snapshot_artifact,
)


def _make_valid_snapshot(
    cluster_id: str = "test-cluster",
    captured_at: str = "2026-04-05T00:00:00Z",
    control_plane_version: str = "1.28.0",
    node_count: int = 3,
) -> dict:
    """Create a valid ClusterSnapshot dict for testing."""
    return {
        "metadata": {
            "cluster_id": cluster_id,
            "captured_at": captured_at,
            "control_plane_version": control_plane_version,
            "node_count": node_count,
        },
        "workloads": {},
        "metrics": {},
        "helm_releases": [],
        "crds": [],
    }


class TestReadClusterSnapshotArtifact:
    """Tests for the strict reader."""

    def test_valid_snapshot_loads_and_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid snapshot should load and return typed ClusterSnapshot."""
        snapshot_data = _make_valid_snapshot()
        snapshot_path = tmp_path / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        result = read_cluster_snapshot_artifact(snapshot_path)

        assert isinstance(result, ClusterSnapshot)
        assert result.metadata.cluster_id == "test-cluster"
        assert result.metadata.node_count == 3
        assert result.metadata.control_plane_version == "1.28.0"

    def test_malformed_json_fails_with_json_decode_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should raise JSONDecodeError."""
        snapshot_path = tmp_path / "malformed.json"
        snapshot_path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_cluster_snapshot_artifact(snapshot_path)

    def test_missing_required_cluster_id_field_fails(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing required cluster_id field should raise KeyError/ValueError from from_dict."""
        incomplete = {
            "metadata": {
                "captured_at": "2026-04-05T00:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
        }
        snapshot_path = tmp_path / "incomplete.json"
        snapshot_path.write_text(json.dumps(incomplete), encoding="utf-8")

        with pytest.raises((KeyError, ValueError, TypeError)):
            read_cluster_snapshot_artifact(snapshot_path)

    def test_non_object_json_fails(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-object JSON (array, number) should raise ValueError."""
        # Array instead of object
        snapshot_path = tmp_path / "array.json"
        snapshot_path.write_text("[1, 2, 3]", encoding="utf-8")

        with pytest.raises(ValueError, match="not a mapping"):
            read_cluster_snapshot_artifact(snapshot_path)

    def test_unreadable_missing_file_raises_os_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should raise OSError (FileNotFoundError)."""
        nonexistent = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            read_cluster_snapshot_artifact(nonexistent)

    def test_roundtrip_with_all_fields(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Snapshot with various fields should roundtrip correctly."""
        snapshot_data = {
            "metadata": {
                "cluster_id": "full-test",
                "captured_at": "2026-04-05T00:00:00Z",
                "control_plane_version": "1.29.0",
                "node_count": 5,
                "cluster_uid": "uid-12345",
                "pod_count": 42,
                "region": "us-west-2",
                "labels": {"env": "prod"},
            },
            "workloads": {"deployments": {"nginx": {"replicas": 3}}},
            "metrics": {"cpu_usage": 0.65, "memory_usage": 0.72},
            "helm_releases": [
                {
                    "name": "ingress-nginx",
                    "namespace": "ingress-nginx",
                    "chart": "ingress-nginx-4.8.0",
                    "chart_version": "4.8.0",
                }
            ],
            "crds": [
                {
                    "name": "certificates.cert-manager.io",
                    "served_versions": ["v1", "v1alpha3", "v1beta1"],
                }
            ],
        }
        snapshot_path = tmp_path / "full.json"
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        result = read_cluster_snapshot_artifact(snapshot_path)

        assert result.metadata.cluster_id == "full-test"
        assert result.metadata.node_count == 5
        assert result.metadata.cluster_uid == "uid-12345"
        assert result.metadata.pod_count == 42
        assert result.metadata.region == "us-west-2"
        assert result.metadata.labels == {"env": "prod"}
        assert result.metrics == {"cpu_usage": 0.65, "memory_usage": 0.72}
        assert "ingress-nginx/ingress-nginx" in result.helm_releases
        assert "certificates.cert-manager.io" in result.crds


class TestTryReadClusterSnapshotArtifact:
    """Tests for the optional reader with graceful fallback."""

    def test_valid_snapshot_returns_typed_object(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid snapshot should return typed object (no logging on success)."""
        snapshot_data = _make_valid_snapshot(cluster_id="valid-cluster")
        snapshot_path = tmp_path / "valid.json"
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        result = try_read_cluster_snapshot_artifact(
            snapshot_path,
            run_id="run-valid",
            artifact_kind="cluster-snapshot",
        )

        assert result is not None
        assert isinstance(result, ClusterSnapshot)
        assert result.metadata.cluster_id == "valid-cluster"

    def test_malformed_json_returns_none_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Malformed JSON should return None and log warning with safe metadata."""
        snapshot_path = tmp_path / "bad.json"
        snapshot_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_cluster_snapshot_artifact(
                snapshot_path,
                run_id="run-789",
                artifact_kind="cluster-snapshot",
            )

        assert result is None
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert "Skipped malformed" in log_record.message
        assert "cluster-snapshot" in log_record.message
        # Verify run_id is in the extra dict (accessible via __dict__)
        assert log_record.__dict__.get("run_id") == "run-789"
        # Verify no sensitive content in logs
        assert "{" not in log_record.message
        assert "not valid" not in log_record.message

    def test_missing_file_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing file should return None."""
        nonexistent = tmp_path / "missing.json"

        result = try_read_cluster_snapshot_artifact(
            nonexistent,
            run_id="run-missing",
            artifact_kind="cluster-snapshot",
        )

        assert result is None

    def test_log_failures_false_returns_none_without_logging(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When log_failures=False, should return None without logging."""
        snapshot_path = tmp_path / "bad.json"
        snapshot_path.write_text("{ not valid }", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_cluster_snapshot_artifact(
                snapshot_path,
                run_id="run-silent",
                artifact_kind="cluster-snapshot",
                log_failures=False,  # Silent mode
            )

        assert result is None
        # No warning should be logged
        assert len(caplog.records) == 0

    def test_log_failures_false_with_valid_snapshot(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Valid snapshot should return object even with log_failures=False."""
        snapshot_data = _make_valid_snapshot(cluster_id="valid-silent")
        snapshot_path = tmp_path / "valid.json"
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = try_read_cluster_snapshot_artifact(
                snapshot_path,
                run_id="run-valid",
                artifact_kind="cluster-snapshot",
                log_failures=False,
            )

        assert result is not None
        assert result.metadata.cluster_id == "valid-silent"
        # No warning for valid snapshot
        assert len(caplog.records) == 0

    def test_missing_cluster_id_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Snapshot missing required cluster_id should return None."""
        incomplete = {
            "metadata": {
                "captured_at": "2026-04-05T00:00:00Z",
                "control_plane_version": "1.28.0",
                "node_count": 3,
            },
        }
        snapshot_path = tmp_path / "incomplete.json"
        snapshot_path.write_text(json.dumps(incomplete), encoding="utf-8")

        result = try_read_cluster_snapshot_artifact(
            snapshot_path,
            artifact_kind="cluster-snapshot",
        )

        assert result is None

    def test_array_json_returns_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Array JSON should return None."""
        snapshot_path = tmp_path / "array.json"
        snapshot_path.write_text("[1, 2, 3]", encoding="utf-8")

        result = try_read_cluster_snapshot_artifact(
            snapshot_path,
            artifact_kind="cluster-snapshot",
        )

        assert result is None


class TestRegressionCliCallSite:
    """Regression tests proving CLI call-site behavior is preserved."""

    def test_cli_load_snapshot_still_works(self, tmp_path: Path) -> None:
        """Test that cli_snapshot_handlers._load_snapshot pattern still works."""
        from k8s_diag_agent.cli_snapshot_handlers import _load_snapshot

        snapshot_data = _make_valid_snapshot(cluster_id="cli-test")
        snapshot_path = tmp_path / "cli-test.json"
        snapshot_path.write_text(json.dumps(snapshot_data), encoding="utf-8")

        result = _load_snapshot(snapshot_path)

        assert isinstance(result, ClusterSnapshot)
        assert result.metadata.cluster_id == "cli-test"

    def test_cli_compare_reports_differences_still_works(self, tmp_path: Path) -> None:
        """Test that handle_compare still reports differences after migration."""
        from k8s_diag_agent.cli_snapshot_handlers import _load_snapshot
        from k8s_diag_agent.compare.two_cluster import compare_snapshots

        snapshot_a_data = _make_valid_snapshot(cluster_id="alpha", node_count=3)
        snapshot_b_data = _make_valid_snapshot(cluster_id="beta", node_count=5)

        path_a = tmp_path / "a.json"
        path_b = tmp_path / "b.json"
        path_a.write_text(json.dumps(snapshot_a_data), encoding="utf-8")
        path_b.write_text(json.dumps(snapshot_b_data), encoding="utf-8")

        primary = _load_snapshot(path_a)
        secondary = _load_snapshot(path_b)

        comparison = compare_snapshots(primary, secondary)

        # Should detect node_count difference
        assert "metadata" in comparison.differences

    def test_malformed_snapshot_raises_in_strict_mode(self, tmp_path: Path) -> None:
        """Strict reader should raise on malformed snapshot (CLI behavior)."""
        from k8s_diag_agent.cli_snapshot_handlers import _load_snapshot

        snapshot_path = tmp_path / "malformed.json"
        snapshot_path.write_text("{ invalid", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            _load_snapshot(snapshot_path)
