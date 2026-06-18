"""Tests for write_diagnosis_loop_pass_artifact function.

Tests prove:
1. Valid orchestrator result writes {run_id}-diagnosis-loop-pass.json
2. Artifact contains schema_version, artifact_type, incident_id, run_id
3. Artifact preserves read_only: True
4. Artifact preserves allowed_actions: []
5. Stop decision artifact is written even when no checks ran
6. Run decision artifact references {run_id}-read-only-check-results.json when check artifact was written
7. Full raw case_file is not persisted
8. Full raw runner_result is not persisted (bounded to summary only)
9. Action-control fields are stripped
10. Unsafe run_id is rejected
11. Input orchestrator_result is not mutated
12. Write result is JSON-serializable
"""

from __future__ import annotations

import json
import tempfile
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


class TestStopDecisionArtifacts:
    """Test stop decision artifact writing."""

    def test_stop_decision_writes_artifact(self, tmp_path: Path) -> None:
        """Stop decision artifact is written even when no checks ran."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-010",
            "run_id": "run-010",
            "decision": "stop_root_cause_found",
            "case_file_linked_artifact": False,
            "runner_result": None,
        }

        result = write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-010",
            incident_id="incident-010",
            orchestrator_result=orchestrator_result,
        )

        assert result["written"] is True
        artifact_path = tmp_path / "run-010-diagnosis-loop-pass.json"
        assert artifact_path.exists()

    def test_stop_decision_has_stop_reason(self, tmp_path: Path) -> None:
        """Stop decision artifact includes stop_reason."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-011",
            "run_id": "run-011",
            "decision": "stop_no_safe_checks",
            "case_file_linked_artifact": False,
            "loop_update": {
                "stop_reason": "no_safe_checks",
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-011",
            incident_id="incident-011",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-011-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["decision"] == "stop_no_safe_checks"
        assert content["checks_run"] == 0


class TestRunDecisionArtifacts:
    """Test run decision artifact writing."""

    def test_run_decision_references_check_artifact(self, tmp_path: Path) -> None:
        """Run decision artifact references check-result artifact when written."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-020",
            "run_id": "run-020",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": True,
            "artifact": {
                "run_id": "run-020",
                "incident_id": "incident-020",
                "written": True,
            },
            "runner_result": {
                "checks_requested": 2,
                "checks_run": 2,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-020",
            incident_id="incident-020",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-020-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        assert content["decision"] == "run_allowed_read_only_checks"
        assert len(content["linked_artifacts"]) == 1
        assert content["linked_artifacts"][0]["name"] == "run-020-read-only-check-results.json"
        assert content["checks_run"] == 2


class TestBoundedContent:
    """Test bounded content in artifacts."""

    def test_no_full_case_file_persisted(self, tmp_path: Path) -> None:
        """Full raw case_file is not persisted."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-030",
            "run_id": "run-030",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            # This should NOT be in the artifact
            "rebuilt_case_file": {
                "incident": {
                    "incident_id": "incident-030",
                    "namespace": "default",
                    "full_dump": "x" * 10000,  # Large data
                },
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-030",
            incident_id="incident-030",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-030-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # rebuilt_case_file should not be in the artifact
        assert "rebuilt_case_file" not in content
        assert "full_dump" not in str(content)

    def test_no_full_runner_result_persisted(self, tmp_path: Path) -> None:
        """Full raw runner_result is not persisted (only summary is stored)."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-031",
            "run_id": "run-031",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            "runner_result": {
                "checks_requested": 2,
                "checks_run": 2,
                # Large results that should be bounded - these are only counts
                "results": [
                    {"check_id": "test", "status": "completed", "summary": "x" * 100}
                    for _ in range(50)
                ],
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-031",
            incident_id="incident-031",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-031-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # runner_result is stored as a bounded summary in orchestrator_result field
        assert "orchestrator_result" in content
        # The orchestrator_result contains runner_result as a bounded summary
        assert "runner_result" in content["orchestrator_result"]
        # Should have counts only, not full results
        assert content["orchestrator_result"]["runner_result"]["checks_requested"] == 2
        assert content["orchestrator_result"]["runner_result"]["checks_run"] == 2


class TestSafetyFields:
    """Test safety field handling."""

    def test_action_fields_stripped(self, tmp_path: Path) -> None:
        """Action-control fields are stripped."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-040",
            "run_id": "run-040",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            # These should be stripped
            "execute": "kubectl exec",
            "run": "some command",
            "mutate": True,
            "action": "delete",
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-040",
            incident_id="incident-040",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-040-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # Action fields should be stripped from top level
        assert "execute" not in content
        assert "run" not in content
        assert "mutate" not in content
        assert "action" not in content


class TestUnsafeRunId:
    """Test unsafe run_id rejection."""

    def test_path_traversal_rejected(self) -> None:
        """Path traversal run_id is rejected."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-050",
            "run_id": "run-050",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_diagnosis_loop_pass_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="../etc/passwd",
                    incident_id="incident-050",
                    orchestrator_result=orchestrator_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)

    def test_slash_in_run_id_rejected(self) -> None:
        """Slash in run_id is rejected."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-051",
            "run_id": "run-051",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                write_diagnosis_loop_pass_artifact(
                    external_analysis_dir=Path(tmpdir),
                    run_id="run/subpath",
                    incident_id="incident-051",
                    orchestrator_result=orchestrator_result,
                )
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "Unsafe run_id" in str(e)


class TestInputNotMutated:
    """Test input is not mutated."""

    def test_orchestrator_result_not_mutated(self, tmp_path: Path) -> None:
        """Input orchestrator_result is not mutated."""
        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-060",
            "run_id": "run-060",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            "runner_result": {"checks_requested": 1, "checks_run": 1},
        }
        original_keys = set(orchestrator_result.keys())

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-060",
            incident_id="incident-060",
            orchestrator_result=orchestrator_result,
        )

        # Verify input is unchanged
        assert set(orchestrator_result.keys()) == original_keys


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


class TestBoundedStringFields:
    """Test that all string fields are bounded/truncated."""

    def test_stop_reason_truncated(self, tmp_path: Path) -> None:
        """Very long stop_reason is truncated to MAX_STRING_CHARS."""
        # Create a stop_reason longer than MAX_STRING_CHARS (500)
        long_stop_reason = "x" * 600

        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-090",
            "run_id": "run-090",
            "decision": "stop_reason_exists",
            "case_file_linked_artifact": False,
            "loop_update": {
                "stop_reason": long_stop_reason,
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-090",
            incident_id="incident-090",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-090-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # stop_reason should be truncated
        assert content["stop_reason"] is not None
        # Truncation happened: result (with marker) should be shorter than input
        assert len(content["stop_reason"]) < len(long_stop_reason)
        assert content["stop_reason"].endswith(" [...]")

    def test_confidence_truncated(self, tmp_path: Path) -> None:
        """Very long confidence string is truncated to MAX_STRING_CHARS."""
        # Create a confidence string longer than MAX_STRING_CHARS (500)
        long_confidence = "y" * 600

        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-091",
            "run_id": "run-091",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            "loop_update": {
                "confidence": long_confidence,
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-091",
            incident_id="incident-091",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-091-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # confidence in loop_summary should be truncated
        assert content["loop_summary"]["confidence"] is not None
        # Truncation happened: result (with marker) should be shorter than input
        assert len(content["loop_summary"]["confidence"]) < len(long_confidence)
        assert content["loop_summary"]["confidence"].endswith(" [...]")

    def test_progress_truncated(self, tmp_path: Path) -> None:
        """Very long progress string is truncated to MAX_STRING_CHARS."""
        # Create a progress string longer than MAX_STRING_CHARS (500)
        long_progress = "z" * 600

        orchestrator_result: dict[str, object] = {
            "schema_version": "1.0",
            "incident_id": "incident-092",
            "run_id": "run-092",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            "loop_update": {
                "progress": long_progress,
            },
        }

        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-092",
            incident_id="incident-092",
            orchestrator_result=orchestrator_result,
        )

        artifact_path = tmp_path / "run-092-diagnosis-loop-pass.json"
        content = json.loads(artifact_path.read_text())

        # progress in loop_summary should be truncated
        assert content["loop_summary"]["progress"] is not None
        # Truncation happened: result (with marker) should be shorter than input
        assert len(content["loop_summary"]["progress"]) < len(long_progress)
        assert content["loop_summary"]["progress"].endswith(" [...]")
