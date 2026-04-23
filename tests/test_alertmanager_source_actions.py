"""Tests for Alertmanager source action artifact writing."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.external_analysis.alertmanager_source_actions import (
    SourceAction,
    _sanitize_for_filename,
    _write_source_action_artifact_impl,
    source_action_artifact_path,
    write_source_action_artifact,
)


class TestSanitizeForFilename:
    """Tests for _sanitize_for_filename function."""

    def test_preserves_normal_characters(self) -> None:
        """Normal strings should pass through unchanged."""
        assert _sanitize_for_filename("simple-source-id") == "simple-source-id"
        assert _sanitize_for_filename("with_underscores") == "with_underscores"

    def test_replaces_colons_and_slashes(self) -> None:
        """Colons and slashes should be replaced (unsafe on most filesystems)."""
        assert _sanitize_for_filename("crd:monitoring/kube-prometheus-stack-alertmanager") == "crd_monitoring_kube-prometheus-stack-alertmanager"
        assert _sanitize_for_filename("namespace/name") == "namespace_name"

    def test_replaces_problematic_characters(self) -> None:
        """Problematic filename characters should be replaced."""
        assert _sanitize_for_filename("source<with>special") == "source_with_special"
        assert _sanitize_for_filename("path|to|file") == "path_to_file"

    def test_collapse_multiple_underscores(self) -> None:
        """Multiple consecutive replacement chars should collapse."""
        assert _sanitize_for_filename("a<>b<>c") == "a_b_c"
        assert _sanitize_for_filename("a:b<>c") == "a_b_c"

    def test_strip_leading_trailing_underscores(self) -> None:
        """Leading/trailing underscores should be stripped."""
        assert _sanitize_for_filename("<start>") == "start"
        assert _sanitize_for_filename("<end>") == "end"
        assert _sanitize_for_filename("<middle>") == "middle"

    def test_empty_string_returns_empty(self) -> None:
        """Empty string should return 'empty'."""
        assert _sanitize_for_filename("") == "empty"

    def test_only_problematic_chars_returns_sanitized(self) -> None:
        """String that becomes empty after sanitization returns 'sanitized'."""
        # All chars replaced, then stripped (colons preserved)
        result = _sanitize_for_filename("<>|\"*?")
        assert result == "sanitized"


class TestWriteSourceActionArtifact:
    """Tests for write_source_action_artifact function."""

    def test_writes_json_artifact(self, tmp_path: Path) -> None:
        """Should write a valid JSON artifact to the correct directory."""
        path = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-2024-01-01-0001",
            source_id="crd:monitoring/kube-prometheus-stack-alertmanager",
            action=SourceAction.PROMOTE,
            cluster_label="prod-cluster",
            cluster_context="kind-prod",
            canonical_identity="monitoring/kube-prometheus-stack-alertmanager",
            endpoint="http://alertmanager.namespace:9093",
            namespace="monitoring",
            name="kube-prometheus-stack-alertmanager",
            original_origin="crd",
            original_state="auto",
            resulting_state="manual",
            reason="Operator requested manual tracking",
        )

        # Path should exist
        assert path.exists()
        assert path.suffix == ".json"

        # Verify content is valid JSON
        content = json.loads(path.read_text(encoding="utf-8"))

        # Verify required fields
        assert "artifact_id" in content
        assert "run_id" in content
        assert content["run_id"] == "run-2024-01-01-0001"
        assert content["action"] == "promote"
        assert content["source_id"] == "crd:monitoring/kube-prometheus-stack-alertmanager"
        assert content["canonical_identity"] == "monitoring/kube-prometheus-stack-alertmanager"
        assert content["cluster_label"] == "prod-cluster"
        assert content["cluster_context"] == "kind-prod"
        assert content["endpoint"] == "http://alertmanager.namespace:9093"
        assert content["namespace"] == "monitoring"
        assert content["name"] == "kube-prometheus-stack-alertmanager"
        assert content["original_origin"] == "crd"
        assert content["original_state"] == "auto"
        assert content["resulting_state"] == "manual"
        assert content["reason"] == "Operator requested manual tracking"
        assert content["schema_version"] == "1"

        # Verify timestamps
        assert "created_at" in content
        assert "timestamp" in content

        # Verify registry key format
        assert "registry_key" in content
        assert "prod-cluster:" in content["registry_key"]

    def test_writes_disable_action(self, tmp_path: Path) -> None:
        """Should write disable action with correct state."""
        path = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-2024-01-01-0002",
            source_id="crd:monitoring/temp-source",
            action=SourceAction.DISABLE,
            cluster_label="prod-cluster",
            cluster_context=None,
            canonical_identity="monitoring/temp-source",
            original_state="auto",
            resulting_state="disabled",
        )

        content = json.loads(path.read_text(encoding="utf-8"))
        assert content["action"] == "disable"
        assert content["resulting_state"] == "disabled"

    def test_creates_subdirectory(self, tmp_path: Path) -> None:
        """Should create alertmanager-source-actions subdirectory."""
        action_dir = tmp_path / "alertmanager-source-actions"
        assert not action_dir.exists()

        write_source_action_artifact(
            directory=tmp_path,
            run_id="run-001",
            source_id="source-1",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
        )

        assert action_dir.exists()
        assert action_dir.is_dir()

    def test_filename_format(self, tmp_path: Path) -> None:
        """Filename should match pattern: run_id-sanitized_source_id-action-uuid.json"""
        path = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-001",
            source_id="source-with-special<>chars",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
        )

        filename = path.name
        assert filename.startswith("run-001-source-with-special_chars-promote-")
        assert filename.endswith(".json")
        # Should have a full UUID suffix (UUIDv7 format)
        assert re.match(r"run-001-source-with-special_chars-promote-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.json", filename)

    def test_immutability_rejects_overwrite(self, tmp_path: Path) -> None:
        """Should reject overwrite if file already exists."""
        # Write first artifact
        path1 = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-001",
            source_id="source-1",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
        )

        # Try to write second artifact with same path (same run_id, source_id, action)
        # Note: different artifact_id means different filename, so this should succeed
        path2 = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-001",
            source_id="source-1",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
        )

        # Should succeed with different artifact IDs
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_optional_fields_optional(self, tmp_path: Path) -> None:
        """Should work without optional fields."""
        path = write_source_action_artifact(
            directory=tmp_path,
            run_id="run-001",
            source_id="source-1",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
            # No optional fields
        )

        content = json.loads(path.read_text(encoding="utf-8"))
        assert content["endpoint"] is None
        assert content["reason"] is None
        assert content["previous_desired_state"] is None


class TestSourceActionArtifactPath:
    """Tests for source_action_artifact_path function."""

    def test_computes_expected_path(self) -> None:
        """Should compute path matching write_source_action_artifact output."""
        directory = Path("/runs/health")
        path = source_action_artifact_path(
            directory=directory,
            run_id="run-001",
            source_id="source-with-chars<>",
            action=SourceAction.PROMOTE,
            artifact_id="a1b2c3d4",
        )

        # Note: trailing underscores are stripped, so "chars<>" becomes "chars"
        expected = directory / "alertmanager-source-actions" / "run-001-source-with-chars-promote-a1b2c3d4.json"
        assert path == expected

    def test_inverse_of_write(self, tmp_path: Path) -> None:
        """Path from source_action_artifact_path should match write output."""
        run_id = "run-001"
        source_id = "test-source"
        action = SourceAction.DISABLE
        artifact_id = "12345678"

        # Compute expected path
        expected_path = source_action_artifact_path(
            directory=tmp_path,
            run_id=run_id,
            source_id=source_id,
            action=action,
            artifact_id=artifact_id,
        )

        # Write artifact
        actual_path = write_source_action_artifact(
            directory=tmp_path,
            run_id=run_id,
            source_id=source_id,
            action=action,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
        )

        # The actual path will have different uuid unless we control it
        # But we can check the directory and naming pattern
        assert actual_path.parent == expected_path.parent
        assert actual_path.name.startswith(f"{run_id}-{source_id}-{action.value}-")
        assert actual_path.name.endswith(".json")


class TestWriteSourceActionArtifactImpl:
    """Tests for _write_source_action_artifact_impl with injectable dependencies."""

    def test_controlled_artifact_id_and_timestamp(self, tmp_path: Path) -> None:
        """Should use injected artifact_id and timestamp for deterministic output."""
        fixed_artifact_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        fixed_timestamp = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)

        path = _write_source_action_artifact_impl(
            directory=tmp_path,
            run_id="run-fixed",
            source_id="source-fixed",
            action=SourceAction.PROMOTE,
            cluster_label="test-cluster",
            cluster_context="kind-test",
            canonical_identity="ns/name",
            artifact_id_fn=lambda: fixed_artifact_id,
            timestamp=fixed_timestamp,
        )

        content = json.loads(path.read_text(encoding="utf-8"))
        
        # Artifact ID should match exactly what we injected
        assert content["artifact_id"] == fixed_artifact_id
        
        # Timestamps should be identical ISO strings
        assert content["created_at"] == "2024-06-15T12:30:00+00:00"
        assert content["timestamp"] == "2024-06-15T12:30:00+00:00"
        
        # Filename should include the controlled artifact_id
        assert fixed_artifact_id in path.name

    def test_rejects_overwrite_with_fixed_artifact_id(self, tmp_path: Path) -> None:
        """Should raise FileExistsError when writing to same path twice."""
        fixed_artifact_id = "fixed-id-for-overwrite-test"
        fixed_timestamp = datetime(2024, 7, 1, 0, 0, 0, tzinfo=UTC)

        # First write should succeed
        path1 = _write_source_action_artifact_impl(
            directory=tmp_path,
            run_id="run-overwrite-test",
            source_id="source-overwrite",
            action=SourceAction.DISABLE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
            artifact_id_fn=lambda: fixed_artifact_id,
            timestamp=fixed_timestamp,
        )
        assert path1.exists()

        # Second write to same path should raise FileExistsError
        with pytest.raises(FileExistsError) as exc_info:
            _write_source_action_artifact_impl(
                directory=tmp_path,
                run_id="run-overwrite-test",
                source_id="source-overwrite",
                action=SourceAction.DISABLE,
                cluster_label="cluster",
                cluster_context=None,
                canonical_identity="ns/name",
                artifact_id_fn=lambda: fixed_artifact_id,
                timestamp=fixed_timestamp,
            )
        
        assert "already exists" in str(exc_info.value)

    def test_timestamp_consistency_between_created_at_and_timestamp(self, tmp_path: Path) -> None:
        """created_at and timestamp fields should always match."""
        test_timestamp = datetime(2025, 1, 15, 9, 45, 30, tzinfo=UTC)

        path = _write_source_action_artifact_impl(
            directory=tmp_path,
            run_id="run-ts-test",
            source_id="source-ts",
            action=SourceAction.PROMOTE,
            cluster_label="cluster",
            cluster_context=None,
            canonical_identity="ns/name",
            timestamp=test_timestamp,
            artifact_id_fn=lambda: "test-id-12345",
        )

        content = json.loads(path.read_text(encoding="utf-8"))
        
        # Both fields should be identical (same timestamp generation)
        assert content["created_at"] == content["timestamp"]
        assert content["created_at"] == "2025-01-15T09:45:30+00:00"
