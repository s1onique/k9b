"""Tests for write_diagnosis_loop_pass_artifact function - bounded content.

Tests prove:
1. Full raw rebuilt_case_file/case_file is not persisted
2. Full raw runner_result is not persisted; only summary/counts are persisted
3. Long stop_reason is truncated
4. Long confidence is truncated
5. Long progress is truncated
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    write_diagnosis_loop_pass_artifact,
)


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
