"""Tests for write_diagnosis_loop_pass_artifact function - basic artifact properties.

Tests prove:
1. Valid orchestrator result writes {run_id}-diagnosis-loop-pass.json
2. Artifact contains schema_version and artifact_type
3. Artifact contains run_id and incident_id
4. Artifact preserves read_only: True
5. Artifact preserves allowed_actions: []
6. Write result is JSON-serializable
7. Deterministic timestamps remain deterministic
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    write_diagnosis_loop_pass_artifact,
)


class TestWriteArtifactBasics:
    """Test basic artifact writing."""

    def test_valid_orchestrator_result_writes_file(self, tmp_path: Path) -> None:
        """Valid orchestrator result produces a JSON artifact file."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-001",
            "run_id": "run-001",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        result = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-001",
            incident_id="incident-001",
            orchestrator_result=orchestrator_result,
        )

        assert result["written"] is True
        assert result["run_id"] == "run-001"
        assert result["incident_id"] == "incident-001"

    def test_artifact_contains_schema_version_and_type(self, tmp_path: Path) -> None:
        """Artifact contains schema_version and artifact_type."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-002",
            "run_id": "run-002",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-002",
            incident_id="incident-002",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-002-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["schema_version"] == ARTIFACT_SCHEMA_VERSION
        assert content["artifact_type"] == "diagnosis-loop-pass"

    def test_artifact_contains_run_id_and_incident_id(self, tmp_path: Path) -> None:
        """Artifact contains run_id and incident_id."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-003",
            "run_id": "run-003",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-003",
            incident_id="incident-003",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-003-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["run_id"] == "run-003"
        assert content["incident_id"] == "incident-003"

    def test_artifact_preserves_read_only_true(self, tmp_path: Path) -> None:
        """Artifact preserves read_only=True."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-004",
            "run_id": "run-004",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-004",
            incident_id="incident-004",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-004-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["read_only"] is True

    def test_artifact_preserves_allowed_actions_empty(self, tmp_path: Path) -> None:
        """Artifact preserves allowed_actions=[]."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-005",
            "run_id": "run-005",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-005",
            incident_id="incident-005",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-005-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["allowed_actions"] == []


class TestWriteResultSerializable:
    """Test write result is JSON-serializable."""

    def test_write_result_is_json_serializable(self, tmp_path: Path) -> None:
        """write_diagnosis_loop_pass_artifact result is JSON-serializable."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-070",
            "run_id": "run-070",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        result = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-070",
            incident_id="incident-070",
            orchestrator_result=orchestrator_result,
        )

        # Should not raise
        json_str = json.dumps(result, default=str)
        parsed = json.loads(json_str)
        assert parsed["written"] is True

    def test_deterministic_timestamps(self, tmp_path: Path) -> None:
        """Deterministic now produces identical timestamps."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-080",
            "run_id": "run-080",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        result1 = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-080a",
            incident_id="incident-080",
            orchestrator_result=orchestrator_result,
            now=now,
        )

        result2 = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-080b",
            incident_id="incident-080",
            orchestrator_result=orchestrator_result,
            now=now,
        )

        artifact_path1 = Path(result1["artifact_path"])
        artifact_path2 = Path(result2["artifact_path"])

        content1 = json.loads(artifact_path1.read_text())
        content2 = json.loads(artifact_path2.read_text())

        assert content1["generated_at"] == content2["generated_at"]
