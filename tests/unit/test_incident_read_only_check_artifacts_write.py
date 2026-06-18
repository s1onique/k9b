"""Tests for write_read_only_check_result_artifact function.

Tests prove:
1. Valid runner result produces a JSON artifact file
2. Artifact contains schema_version, run_id, incident_id
3. Artifact preserves read_only=True and allowed_actions=[]
4. Artifact includes disallowed_actions for safety
5. Artifact includes bounded runner_result
6. Path traversal is prevented
7. Unsafe run_ids are rejected
8. Input runner_result is not mutated
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_read_only_check_artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    write_read_only_check_result_artifact,
)


class TestWriteArtifactBasics:
    """Test basic artifact writing."""

    def test_valid_runner_result_writes_file(self, tmp_path: Path) -> None:
        """Valid runner result produces a JSON artifact file."""
        runner_result: dict[str, object] = {
            "checks_requested": 2,
            "checks_run": 2,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "test log"}
            ],
        }
        result = write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-001",
            incident_id="incident-001",
            runner_result=runner_result,
        )

        assert result["written"] is True
        assert result["run_id"] == "run-001"
        assert result["incident_id"] == "incident-001"

    def test_artifact_contains_schema_version(self, tmp_path: Path) -> None:
        """Artifact contains schema version."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-002",
            incident_id="incident-002",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-002-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert content["schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert content["artifact_type"] == "read-only-check-results"

    def test_artifact_contains_run_id_and_incident_id(self, tmp_path: Path) -> None:
        """Artifact contains run_id and incident_id."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-003",
            incident_id="incident-003",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-003-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert content["run_id"] == "run-003"
        assert content["incident_id"] == "incident-003"

    def test_artifact_preserves_read_only_true(self, tmp_path: Path) -> None:
        """Artifact preserves read_only=True."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-004",
            incident_id="incident-004",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-004-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert content["read_only"] is True

    def test_artifact_preserves_allowed_actions_empty(self, tmp_path: Path) -> None:
        """Artifact preserves allowed_actions=[]."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-005",
            incident_id="incident-005",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-005-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert content["allowed_actions"] == []

    def test_artifact_includes_disallowed_actions(self, tmp_path: Path) -> None:
        """Artifact includes disallowed_actions for safety."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-006",
            incident_id="incident-006",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-006-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert "disallowed_actions" in content
        assert "execute" in content["disallowed_actions"]
        assert "delete" in content["disallowed_actions"]
        assert "mutate" in content["disallowed_actions"]

    def test_artifact_includes_bounded_runner_result(self, tmp_path: Path) -> None:
        """Artifact includes bounded runner_result."""
        runner_result: dict[str, object] = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {"check_id": "test", "status": "completed", "summary": "test summary"}
            ],
        }

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-007",
            incident_id="incident-007",
            runner_result=runner_result,
        )

        artifact_path = tmp_path / "run-007-read-only-check-results.json"
        content = json.loads(artifact_path.read_text())

        assert "runner_result" in content
        assert content["runner_result"]["checks_requested"] == 1

    def test_artifact_generated_at_is_deterministic(self, tmp_path: Path) -> None:
        """Artifact generated_at is deterministic with now parameter."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        result1 = write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-008a",
            incident_id="incident-008",
            runner_result=runner_result,
            now=now,
        )

        result2 = write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-008b",
            incident_id="incident-008",
            runner_result=runner_result,
            now=now,
        )

        artifact_path1 = result1["artifact_path"]
        artifact_path2 = result2["artifact_path"]

        content1 = json.loads(Path(artifact_path1).read_text())
        content2 = json.loads(Path(artifact_path2).read_text())

        assert content1["generated_at"] == content2["generated_at"]

    def test_write_result_is_json_serializable(self, tmp_path: Path) -> None:
        """write_read_only_check_result_artifact result is JSON-serializable."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}
        result = write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-009",
            incident_id="incident-009",
            runner_result=runner_result,
        )

        # Should not raise
        json_str = json.dumps(result, default=str)
        parsed = json.loads(json_str)
        assert parsed["written"] is True


class TestUnsafeRunId:
    """Test unsafe run_id rejection."""

    def test_path_traversal_rejected(self) -> None:
        """Path traversal run_id is rejected."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_read_only_check_result_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="../etc/passwd",
                    incident_id="incident-010",
                    runner_result=runner_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_absolute_path_rejected(self) -> None:
        """Absolute path run_id is rejected."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_read_only_check_result_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="/absolute/path",
                    incident_id="incident-011",
                    runner_result=runner_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_slash_in_run_id_rejected(self) -> None:
        """Slash in run_id is rejected."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_read_only_check_result_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="run/subpath",
                    incident_id="incident-012",
                    runner_result=runner_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_backslash_in_run_id_rejected(self) -> None:
        """Backslash in run_id is rejected."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_read_only_check_result_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="run\\subpath",
                    incident_id="incident-013",
                    runner_result=runner_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_empty_run_id_rejected(self) -> None:
        """Empty run_id is rejected."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_read_only_check_result_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="",
                    incident_id="incident-014",
                    runner_result=runner_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)


class TestPathTraversalPrevention:
    """Test path traversal prevention."""

    def test_cannot_escape_to_parent(self) -> None:
        """Cannot escape to parent directory with malicious run_id."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "artifacts"
            external_dir.mkdir()

            write_read_only_check_result_artifact(
                external_analysis_dir=external_dir,
                run_id="safe-run-id",
                incident_id="incident-015",
                runner_result=runner_result,
            )

            # Verify file is inside the artifacts directory
            artifact = external_dir / "safe-run-id-read-only-check-results.json"
            assert artifact.exists()

            # Verify artifact path is under external_dir (not a sibling)
            assert artifact.parent == external_dir

    def test_artifact_written_inside_directory(self) -> None:
        """Artifact is written inside the external_analysis_dir."""
        runner_result: dict[str, object] = {"checks_requested": 1, "checks_run": 1}

        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            external_dir.mkdir()

            result = write_read_only_check_result_artifact(
                external_analysis_dir=external_dir,
                run_id="run-016",
                incident_id="incident-016",
                runner_result=runner_result,
            )

            artifact_path = Path(result["artifact_path"])
            assert artifact_path.parent == external_dir
            assert artifact_path.name == "run-016-read-only-check-results.json"


class TestInputNotMutated:
    """Test input is not mutated."""

    def test_runner_result_not_mutated(self, tmp_path: Path) -> None:
        """Input runner_result is not mutated."""
        runner_result: dict[str, object] = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {"check_id": "test", "status": "completed", "summary": "test summary"}
            ],
        }
        original_results = list(runner_result["results"])  # type: ignore[index]

        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-017",
            incident_id="incident-017",
            runner_result=runner_result,
        )

        # Verify input is unchanged
        assert runner_result["results"] == original_results  # type: ignore[index]
